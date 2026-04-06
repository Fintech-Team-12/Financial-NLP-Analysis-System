"""
업로드 인덱싱 파이프라인 단위 테스트.

load_table_chunks_from_file / index_uploaded_table_chunks 가
기존 enriched 파이프라인(structured_flatten + enrich_flattened_for_rag)을
올바르게 재사용하는지 검증한다.

ChromaDB 는 mock 하므로 실제 chroma_store 불필요.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_json_path(sample_data_dir: str) -> Path:
    """conftest 에서 생성된 샘플 structured JSON 파일 경로."""
    files = list(Path(sample_data_dir).glob("*_structured.json"))
    assert files, "sample_data_dir 에 structured JSON 파일이 없습니다"
    return files[0]


# ── load_table_chunks_from_file ───────────────────────────────────────────────

class TestLoadTableChunksFromFile:
    def test_returns_only_table_content_type(self, sample_json_path: Path):
        from app.services.indexing import load_table_chunks_from_file
        chunks = load_table_chunks_from_file(sample_json_path)
        assert all(c.get("content_type") == "table" for c in chunks)

    def test_nonempty_for_sample_with_table(self, sample_json_path: Path):
        """conftest SAMPLE_DATA 의 재무상태표에 tables 가 있으므로 최소 1건 이상이어야 한다."""
        from app.services.indexing import load_table_chunks_from_file
        chunks = load_table_chunks_from_file(sample_json_path)
        assert len(chunks) > 0

    def test_each_chunk_has_required_fields(self, sample_json_path: Path):
        from app.services.indexing import load_table_chunks_from_file
        chunks = load_table_chunks_from_file(sample_json_path)
        required = {"chunk_id", "doc_id", "year", "company", "embedding_text",
                    "section_title", "content_type", "order_index"}
        for chunk in chunks:
            missing = required - chunk.keys()
            assert not missing, f"chunk 에 필드 누락: {missing}"

    def test_chunk_id_nonempty(self, sample_json_path: Path):
        from app.services.indexing import load_table_chunks_from_file
        chunks = load_table_chunks_from_file(sample_json_path)
        assert all(c.get("chunk_id") for c in chunks)

    def test_embedding_text_nonempty(self, sample_json_path: Path):
        from app.services.indexing import load_table_chunks_from_file
        chunks = load_table_chunks_from_file(sample_json_path)
        assert all(c.get("embedding_text") for c in chunks)

    def test_year_is_correct(self, sample_json_path: Path):
        from app.services.indexing import load_table_chunks_from_file
        chunks = load_table_chunks_from_file(sample_json_path)
        # conftest SAMPLE_DATA 는 2023년
        assert all(c.get("year") == 2023 for c in chunks)

    def test_does_not_touch_store(self, sample_json_path: Path, reset_store):
        from app.services import indexing
        from app.services.indexing import load_table_chunks_from_file
        load_table_chunks_from_file(sample_json_path)
        assert len(indexing._store) == 0, "load_table_chunks_from_file 는 _store 를 건드리지 않아야 함"

    def test_file_not_found_raises(self, tmp_path: Path):
        from app.services.indexing import load_table_chunks_from_file
        with pytest.raises(FileNotFoundError):
            load_table_chunks_from_file(tmp_path / "nonexistent.json")


# ── index_uploaded_table_chunks ───────────────────────────────────────────────

class TestIndexUploadedTableChunks:
    """ChromaDB 클라이언트를 mock 하여 메타데이터 변환만 검증."""

    def _make_chunk(self, idx: int = 0) -> dict:
        return {
            "chunk_id":      f"chunk_{idx}",
            "doc_id":        f"doc_{idx}",
            "year":          2023,
            "company":       "테스트기업",
            "report_type":   "감사보고서",
            "top_section":   "재무상태표",
            "note_number":   "",
            "section_path":  "재무상태표",
            "section_level": 1,
            "section_title": "재무상태표",
            "section_type":  "table",
            "content_type":  "table",
            "order_index":   idx,
            "embedding_text": f"테이블 내용 {idx}",
        }

    def test_empty_chunks_returns_zero(self):
        from app.services.vector_store import index_uploaded_table_chunks
        with patch("app.services.vector_store._get_client"), \
             patch("app.services.vector_store._get_embedding_function"):
            result = index_uploaded_table_chunks([])
        assert result["indexed"] == 0

    def test_indexed_count_matches_chunk_count(self):
        from app.services.vector_store import index_uploaded_table_chunks
        chunks = [self._make_chunk(i) for i in range(3)]

        mock_col = MagicMock()
        mock_col.count.return_value = 3
        mock_col.get.return_value = {"ids": []}

        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_col

        with patch("app.services.vector_store._get_client", return_value=mock_client), \
             patch("app.services.vector_store._get_embedding_function", return_value=MagicMock()):
            result = index_uploaded_table_chunks(chunks, force=False)

        assert result["indexed"] == 3

    def test_metadata_content_type_is_table(self):
        from app.services.vector_store import index_uploaded_table_chunks
        chunks = [self._make_chunk(0)]

        mock_col = MagicMock()
        mock_col.count.return_value = 1
        mock_col.get.return_value = {"ids": []}

        captured_metadatas: list = []

        def fake_add(ids, documents, metadatas):
            captured_metadatas.extend(metadatas)

        mock_col.add.side_effect = fake_add
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_col

        with patch("app.services.vector_store._get_client", return_value=mock_client), \
             patch("app.services.vector_store._get_embedding_function", return_value=MagicMock()):
            index_uploaded_table_chunks(chunks)

        assert all(m["content_type"] == "table" for m in captured_metadatas)

    def test_collection_name_is_table_collection(self):
        from app.services.vector_store import index_uploaded_table_chunks, _COLLECTION_TABLE
        chunks = [self._make_chunk(0)]

        mock_col = MagicMock()
        mock_col.count.return_value = 1
        mock_col.get.return_value = {"ids": []}
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_col

        with patch("app.services.vector_store._get_client", return_value=mock_client), \
             patch("app.services.vector_store._get_embedding_function", return_value=MagicMock()):
            result = index_uploaded_table_chunks(chunks)

        call_kwargs = mock_client.get_or_create_collection.call_args
        assert call_kwargs[1]["name"] == _COLLECTION_TABLE or \
               call_kwargs[0][0] == _COLLECTION_TABLE
        assert result["collection"] == _COLLECTION_TABLE

    def test_force_deletes_existing_ids(self):
        from app.services.vector_store import index_uploaded_table_chunks
        chunks = [self._make_chunk(0)]

        mock_col = MagicMock()
        mock_col.count.return_value = 1
        mock_col.get.return_value = {"ids": ["chunk_0"]}
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_col

        with patch("app.services.vector_store._get_client", return_value=mock_client), \
             patch("app.services.vector_store._get_embedding_function", return_value=MagicMock()):
            index_uploaded_table_chunks(chunks, force=True)

        mock_col.delete.assert_called_once_with(ids=["chunk_0"])
