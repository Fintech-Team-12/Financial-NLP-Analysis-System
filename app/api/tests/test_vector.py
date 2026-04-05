"""
POST /vector/index, POST /vector/search, GET /vector/health 테스트.

chromadb.PersistentClient 및 임베딩 모델 로딩을 mock 으로 대체해
외부 의존성 없이 실행 가능.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _mock_col(count: int = 0, query_result: dict | None = None):
    col = MagicMock()
    col.count.return_value = count
    col.query.return_value = query_result or {
        "ids": [["chunk_abc"]],
        "documents": [["2014년 감사보고서 내용"]],
        "metadatas": [[{"year": 2014, "section_title": "감사의견", "company": "삼성전자",
                        "content_type": "text", "section_path": "감사의견", "report_type": "감사보고서"}]],
        "distances": [[0.05]],
    }
    return col


def _mock_client(collection_names: list[str] = (), collection: MagicMock | None = None):
    fc = MagicMock()
    mock_cols = []
    for name in collection_names:
        mc = MagicMock()
        mc.name = name
        mock_cols.append(mc)
    fc.list_collections.return_value = mock_cols
    if collection is not None:
        fc.get_or_create_collection.return_value = collection
        fc.get_collection.return_value = collection
    return fc


# ── GET /vector/health ────────────────────────────────────────────────────────

def test_vector_health_store_unavailable():
    with patch(
        "app.services.vector_store._get_client",
        side_effect=Exception("chroma_store not found"),
    ):
        resp = client.get("/vector/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["store"] == "unavailable"
    assert "error" in data
    assert data["indexed_years"] == []
    assert len(data["missing_years"]) == 11  # 2014–2024


def test_vector_health_store_empty_no_collections():
    fc = _mock_client(collection_names=[])
    with patch("app.services.vector_store._get_client", return_value=fc):
        resp = client.get("/vector/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["store"] == "ok"
    assert data["indexed_years"] == []
    assert len(data["missing_years"]) == 11  # 전부 미인덱싱


def test_vector_health_partial_indexing():
    """2014만 인덱싱된 경우 나머지 10개 연도는 missing_years 에 포함."""
    col_2014 = _mock_col(count=1523)
    fc = _mock_client(collection_names=["audit_reports_2014"])
    fc.get_collection.return_value = col_2014

    with patch("app.services.vector_store._get_client", return_value=fc):
        resp = client.get("/vector/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["store"] == "ok"
    assert data["indexed_years"] == [2014]
    assert len(data["missing_years"]) == 10
    assert data["collection_stats"]["2014"] == 1523


def test_vector_health_empty_collection():
    """컬렉션은 있지만 count=0 → empty_years 에 포함."""
    col_empty = _mock_col(count=0)
    fc = _mock_client(collection_names=["audit_reports_2018"])
    fc.get_collection.return_value = col_empty

    with patch("app.services.vector_store._get_client", return_value=fc):
        resp = client.get("/vector/health")

    data = resp.json()
    assert 2018 in data["empty_years"]
    assert 2018 not in data["indexed_years"]


def test_vector_health_response_schema():
    """응답 필드 구조 확인."""
    fc = _mock_client()
    with patch("app.services.vector_store._get_client", return_value=fc):
        resp = client.get("/vector/health")
    data = resp.json()
    for key in ("store", "indexed_years", "empty_years", "missing_years", "collection_stats"):
        assert key in data


# ── POST /vector/index ────────────────────────────────────────────────────────

def test_vector_index_missing_enriched_file(tmp_path, monkeypatch):
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "chroma_enriched_data_dir", str(tmp_path))
    fc = _mock_client()
    with patch("app.services.vector_store._get_client", return_value=fc):
        resp = client.post("/vector/index", json={"year": 2020})
    assert resp.status_code == 404
    assert "Enriched data not found" in resp.json()["detail"]


def test_vector_index_ok(tmp_path, monkeypatch):
    import app.core.config as cfg

    enriched = tmp_path / "audit_report_2014_enriched.json"
    enriched.write_text(
        json.dumps([{
            "chunk_id": "c1", "embedding_text": "삼성전자 2014년 감사의견",
            "year": 2014, "company": "삼성전자", "report_type": "감사보고서",
            "section_path": "감사의견", "section_title": "감사의견", "content_type": "text",
        }]),
        encoding="utf-8",
    )
    monkeypatch.setattr(cfg.settings, "chroma_enriched_data_dir", str(tmp_path))

    col = MagicMock()
    col.count.side_effect = [0, 1]  # pre-check=0, post-add=1
    fc = _mock_client(collection=col)
    with patch("app.services.vector_store._get_client", return_value=fc):
        with patch("app.services.vector_store._get_embedding_function"):
            resp = client.post("/vector/index", json={"year": 2014})

    assert resp.status_code == 200
    data = resp.json()
    assert data["collection"] == "audit_reports_2014"
    assert data["skipped"] is False
    assert data["indexed"] == 1


def test_vector_index_skipped_when_already_indexed(tmp_path, monkeypatch):
    import app.core.config as cfg

    enriched = tmp_path / "audit_report_2015_enriched.json"
    enriched.write_text(
        json.dumps([{"chunk_id": "x1", "embedding_text": "내용", "year": 2015}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(cfg.settings, "chroma_enriched_data_dir", str(tmp_path))

    col = MagicMock()
    col.count.return_value = 10  # 이미 10건 인덱싱됨
    fc = _mock_client(collection=col)
    with patch("app.services.vector_store._get_client", return_value=fc):
        with patch("app.services.vector_store._get_embedding_function"):
            resp = client.post("/vector/index", json={"year": 2015})

    assert resp.status_code == 200
    data = resp.json()
    assert data["skipped"] is True
    assert data["indexed"] == 0


def test_vector_index_force_reindex(tmp_path, monkeypatch):
    import app.core.config as cfg

    enriched = tmp_path / "audit_report_2016_enriched.json"
    enriched.write_text(
        json.dumps([{"chunk_id": "y1", "embedding_text": "재적재 내용", "year": 2016}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(cfg.settings, "chroma_enriched_data_dir", str(tmp_path))

    col = MagicMock()
    col.count.side_effect = [0, 1]
    fc = _mock_client(collection=col)
    with patch("app.services.vector_store._get_client", return_value=fc):
        with patch("app.services.vector_store._get_embedding_function"):
            resp = client.post("/vector/index", json={"year": 2016, "force": True})

    assert resp.status_code == 200
    assert resp.json()["skipped"] is False
    fc.delete_collection.assert_called_once_with(name="audit_reports_2016")


def test_vector_index_invalid_year():
    resp = client.post("/vector/index", json={"year": 2000})
    assert resp.status_code == 422


# ── POST /vector/search ───────────────────────────────────────────────────────

def test_vector_search_with_year():
    col = _mock_col(count=5)
    fc = _mock_client(collection_names=["audit_reports_2014"], collection=col)
    with patch("app.services.vector_store._get_client", return_value=fc):
        with patch("app.services.vector_store._get_embedding_function"):
            resp = client.post("/vector/search", json={"query": "감사의견", "year": 2014})

    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "감사의견"
    assert data["year"] == 2014
    assert data["count"] == 1
    assert data["results"][0]["id"] == "chunk_abc"
    assert data["results"][0]["distance"] == pytest.approx(0.05)
    assert data["warnings"] == []


def test_vector_search_missing_year_returns_warning():
    """요청 연도 컬렉션 미존재 → results=[], warnings 에 안내 메시지."""
    fc = _mock_client(collection_names=[])  # 아무 컬렉션도 없음
    with patch("app.services.vector_store._get_client", return_value=fc):
        resp = client.post("/vector/search", json={"query": "감사의견", "year": 2022})

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["results"] == []
    assert len(data["warnings"]) > 0
    assert "audit_reports_2022" in data["warnings"][0]


def test_vector_search_no_collections_returns_warning():
    """year=None 인데 컬렉션 자체가 없으면 warnings 포함."""
    fc = _mock_client(collection_names=[])
    with patch("app.services.vector_store._get_client", return_value=fc):
        resp = client.post("/vector/search", json={"query": "재고자산", "year": None})

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert len(data["warnings"]) > 0


def test_vector_search_all_years():
    col = _mock_col(count=3)
    mc14 = MagicMock(); mc14.name = "audit_reports_2014"
    mc15 = MagicMock(); mc15.name = "audit_reports_2015"
    fc = MagicMock()
    fc.list_collections.return_value = [mc14, mc15]
    fc.get_collection.return_value = col

    with patch("app.services.vector_store._get_client", return_value=fc):
        with patch("app.services.vector_store._get_embedding_function"):
            resp = client.post("/vector/search", json={"query": "재고자산", "year": None, "top_k": 3})

    assert resp.status_code == 200
    data = resp.json()
    assert data["year"] is None
    assert data["count"] == 2  # 컬렉션 2개 × 1건 = 2건


def test_vector_search_sorted_by_distance():
    col = MagicMock()
    col.count.return_value = 5
    col.query.return_value = {
        "ids": [["c1", "c2"]],
        "documents": [["doc1", "doc2"]],
        "metadatas": [[{"section_title": "A", "year": 2018}, {"section_title": "B", "year": 2018}]],
        "distances": [[0.8, 0.2]],  # c2 가 더 가깝다
    }
    fc = _mock_client(collection_names=["audit_reports_2018"], collection=col)
    with patch("app.services.vector_store._get_client", return_value=fc):
        with patch("app.services.vector_store._get_embedding_function"):
            resp = client.post("/vector/search", json={"query": "법인세", "year": 2018})

    results = resp.json()["results"]
    assert results[0]["id"] == "c2"
    assert results[1]["id"] == "c1"


def test_vector_search_chroma_error_returns_warning():
    """특정 컬렉션 조회 중 예외 → warnings 포함, 나머지 결과는 반환."""
    mc = MagicMock(); mc.name = "audit_reports_2019"
    fc = MagicMock()
    fc.list_collections.return_value = [mc]
    fc.get_collection.side_effect = Exception("connection reset")

    with patch("app.services.vector_store._get_client", return_value=fc):
        with patch("app.services.vector_store._get_embedding_function"):
            resp = client.post("/vector/search", json={"query": "감사", "year": None})

    data = resp.json()
    assert data["count"] == 0
    assert any("audit_reports_2019" in w for w in data["warnings"])


def test_vector_search_invalid_year():
    resp = client.post("/vector/search", json={"query": "손익", "year": 2030})
    assert resp.status_code == 422


def test_vector_search_top_k_limit():
    resp = client.post("/vector/search", json={"query": "test", "top_k": 25})
    assert resp.status_code == 422


# ── ChromaRetriever ───────────────────────────────────────────────────────────

def test_chroma_retriever_returns_normalized_documents():
    """ChromaRetriever.search() 가 NormalizedDocument 목록을 반환하는지 확인."""
    from app.services.retrieval import ChromaRetriever

    mock_search_result = {
        "results": [{
            "id": "chunk_001",
            "document": "삼성전자 2014년 감사의견: 적정",
            "metadata": {
                "year": 2014,
                "section_title": "감사의견",
                "content_type": "text",
                "section_path": "감사보고서 > 감사의견",  # → doc_type="audit_report"
            },
            "distance": 0.1,
            "collection": "audit_reports_2014",
        }],
        "warnings": [],
    }

    with patch("app.services.vector_store.search", return_value=mock_search_result):
        retriever = ChromaRetriever()
        docs = retriever.search("감사의견", year=2014, top_k=3)

    assert len(docs) == 1
    doc = docs[0]
    assert doc.doc_id == "chunk_001"
    assert doc.year == 2014
    assert doc.section == "감사의견"
    assert doc.doc_type == "audit_report"   # section_path 첫 세그먼트 "감사보고서" → audit_report
    assert "적정" in doc.content
    assert doc.numeric_value is None
    assert doc.related_notes == []


def test_chroma_retriever_doc_type_filter():
    """ChromaRetriever 가 section_path 기반 doc_type 후처리 필터를 적용하는지 확인."""
    from app.services.retrieval import ChromaRetriever

    mock_result = {
        "results": [
            # section_path "감사보고서 > ..." → doc_type="audit_report"
            {"id": "c1", "document": "감사의견 텍스트", "metadata": {"year": 2020, "section_title": "감사의견",
             "content_type": "text", "section_path": "감사보고서 > 감사의견"}, "distance": 0.1, "collection": "x"},
            # section_path "주석 > ..." → doc_type="note"
            {"id": "c2", "document": "주석 내용", "metadata": {"year": 2020, "section_title": "재고자산",
             "content_type": "text", "section_path": "주석 > 8"}, "distance": 0.2, "collection": "x"},
        ],
        "warnings": [],
    }

    with patch("app.services.vector_store.search", return_value=mock_result):
        retriever = ChromaRetriever()
        docs = retriever.search("쿼리", year=2020, doc_type="note")

    assert len(docs) == 1
    assert docs[0].doc_id == "c2"
    assert docs[0].doc_type == "note"
