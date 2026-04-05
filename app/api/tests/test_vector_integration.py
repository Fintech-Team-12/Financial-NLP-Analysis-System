"""
ChromaDB 실제 통합 테스트.

mock 을 사용하지 않고 로컬 chroma_store 에 직접 접속하여
/vector/health 와 /vector/search 엔드포인트가 실제 데이터를
정상적으로 반환하는지 검증한다.

## 실행 전제 조건
  chroma_store/chroma.sqlite3 가 존재해야 한다.
  (팀원의 chroma/load_{year}_to_chroma.py 를 먼저 실행)

## 실행 방법
  # 통합 테스트만 실행
  PYTHONPATH=app/api pytest app/api/tests/test_vector_integration.py -v

  # 전체 테스트에서 통합 테스트 제외 (CI 기본값)
  PYTHONPATH=app/api pytest app/api/tests/ --ignore=app/api/tests/test_vector_integration.py

## 주의사항
  - 처음 실행 시 SentenceTransformer 모델 다운로드/로딩으로 수 초 소요됨
  - 테스트 완료 후 chroma_store 는 변경되지 않음 (읽기 전용 검색만 수행)
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

# ── 경로 설정 ─────────────────────────────────────────────────────────────────
# 이 파일 기준으로 프로젝트 루트를 계산.
# tests/ → api/ → app/ → Financial-NLP-Analysis-System/
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CHROMA_STORE = _PROJECT_ROOT / "chroma_store"
_CHROMA_SQLITE = _CHROMA_STORE / "chroma.sqlite3"

# ── 전제 조건 확인 ────────────────────────────────────────────────────────────
# chroma.sqlite3 가 없으면 파일 내 모든 테스트를 skip
pytestmark = pytest.mark.skipif(
    not _CHROMA_SQLITE.exists(),
    reason=(
        f"chroma_store 가 {_CHROMA_STORE} 에 없습니다. "
        "팀원의 chroma/load_*_to_chroma.py 를 먼저 실행하세요."
    ),
)


# ── 픽스처 ────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def real_client():
    """
    실제 chroma_store 를 사용하는 TestClient.
    settings.chroma_persist_path 를 절대 경로로 고정해
    pytest 실행 디렉토리에 무관하게 동작하도록 한다.
    """
    import app.core.config as cfg

    original_path = cfg.settings.chroma_persist_path
    cfg.settings.chroma_persist_path = str(_CHROMA_STORE)
    try:
        yield TestClient(app)
    finally:
        cfg.settings.chroma_persist_path = original_path


# ── GET /vector/health ────────────────────────────────────────────────────────

class TestVectorHealthIntegration:
    def test_status_code(self, real_client):
        resp = real_client.get("/vector/health")
        assert resp.status_code == 200

    def test_store_is_ok(self, real_client):
        data = real_client.get("/vector/health").json()
        assert data["store"] == "ok", (
            f"store 가 'ok' 가 아닙니다: {data.get('error', data)}"
        )

    def test_response_schema(self, real_client):
        data = real_client.get("/vector/health").json()
        for key in ("store", "indexed_years", "empty_years", "missing_years", "collection_stats"):
            assert key in data, f"응답에 '{key}' 필드가 없습니다"

    def test_has_indexed_years(self, real_client):
        data = real_client.get("/vector/health").json()
        assert len(data["indexed_years"]) > 0, (
            "indexed_years 가 비어 있습니다. 컬렉션이 적재되지 않았습니다."
        )

    def test_2014_is_indexed(self, real_client):
        """현재 로컬에 audit_reports_2014 컬렉션이 적재되어 있어야 한다."""
        data = real_client.get("/vector/health").json()
        assert 2014 in data["indexed_years"], (
            f"2014 가 indexed_years 에 없습니다: {data['indexed_years']}"
        )
        assert 2014 not in data["missing_years"]

    def test_collection_stats_has_2014(self, real_client):
        data = real_client.get("/vector/health").json()
        assert "2014" in data["collection_stats"], "collection_stats 에 2014 키가 없습니다"
        doc_count = data["collection_stats"]["2014"]
        assert doc_count > 0, f"2014 컬렉션 문서 수가 0 입니다: {doc_count}"

    def test_2014_doc_count(self, real_client):
        """audit_reports_2014 에 285개의 청크가 적재되어 있어야 한다."""
        data = real_client.get("/vector/health").json()
        count = data["collection_stats"].get("2014", 0)
        assert count == 285, f"예상 문서 수 285, 실제: {count}"


# ── POST /vector/search ───────────────────────────────────────────────────────

class TestVectorSearchIntegration:
    def test_status_code(self, real_client):
        resp = real_client.post(
            "/vector/search", json={"query": "감사의견", "year": 2014}
        )
        assert resp.status_code == 200

    def test_returns_results(self, real_client):
        data = real_client.post(
            "/vector/search", json={"query": "감사의견", "year": 2014}
        ).json()
        assert data["count"] > 0, "결과가 0건입니다."
        assert len(data["results"]) > 0

    def test_no_warnings_for_indexed_year(self, real_client):
        data = real_client.post(
            "/vector/search", json={"query": "감사의견", "year": 2014}
        ).json()
        assert data["warnings"] == [], (
            f"인덱싱된 연도에서 warnings 가 발생했습니다: {data['warnings']}"
        )

    def test_result_fields(self, real_client):
        """검색 결과 1건에 필수 필드가 모두 포함되어야 한다."""
        data = real_client.post(
            "/vector/search", json={"query": "감사의견", "year": 2014}
        ).json()
        first = data["results"][0]
        for field in ("id", "document", "metadata", "distance", "collection"):
            assert field in first, f"결과에 '{field}' 필드가 없습니다"

    def test_result_id_is_nonempty_string(self, real_client):
        data = real_client.post(
            "/vector/search", json={"query": "감사의견", "year": 2014}
        ).json()
        first_id = data["results"][0]["id"]
        assert isinstance(first_id, str) and first_id, "id 가 비어 있습니다"

    def test_result_metadata_has_year(self, real_client):
        data = real_client.post(
            "/vector/search", json={"query": "감사의견", "year": 2014}
        ).json()
        meta = data["results"][0]["metadata"]
        assert "year" in meta, "metadata 에 year 필드가 없습니다"
        assert int(meta["year"]) == 2014

    def test_result_metadata_has_section_title(self, real_client):
        data = real_client.post(
            "/vector/search", json={"query": "감사의견", "year": 2014}
        ).json()
        meta = data["results"][0]["metadata"]
        assert "section_title" in meta

    def test_result_collection_name(self, real_client):
        data = real_client.post(
            "/vector/search", json={"query": "감사의견", "year": 2014}
        ).json()
        assert data["results"][0]["collection"] == "audit_reports_2014"

    def test_result_document_is_nonempty(self, real_client):
        data = real_client.post(
            "/vector/search", json={"query": "감사의견", "year": 2014}
        ).json()
        doc = data["results"][0]["document"]
        assert isinstance(doc, str) and len(doc) > 0

    def test_result_document_contains_samsung(self, real_client):
        """embedding_text 는 항상 회사명 '삼성전자' 를 포함한다."""
        data = real_client.post(
            "/vector/search", json={"query": "감사의견", "year": 2014}
        ).json()
        assert "삼성전자" in data["results"][0]["document"]

    def test_results_sorted_by_distance(self, real_client):
        """결과가 distance 오름차순 (가까운 것이 먼저) 으로 정렬되어야 한다."""
        data = real_client.post(
            "/vector/search", json={"query": "감사의견", "year": 2014, "top_k": 5}
        ).json()
        distances = [r["distance"] for r in data["results"] if r["distance"] is not None]
        assert distances == sorted(distances), f"결과가 distance 오름차순이 아닙니다: {distances}"

    def test_top_k_respected(self, real_client):
        data = real_client.post(
            "/vector/search", json={"query": "재무제표", "year": 2014, "top_k": 3}
        ).json()
        assert len(data["results"]) <= 3

    def test_warning_for_unindexed_year(self, real_client):
        """
        적재되지 않은 연도(2015~2024)를 요청하면
        results=[] 이고 warnings 에 안내 메시지가 포함되어야 한다.
        """
        data = real_client.post(
            "/vector/search", json={"query": "감사의견", "year": 2020}
        ).json()
        assert data["count"] == 0
        assert data["results"] == []
        assert len(data["warnings"]) > 0
        assert "audit_reports_2020" in data["warnings"][0]

    def test_multiple_queries_consistent(self, real_client):
        """같은 질의를 두 번 호출하면 동일한 결과를 반환해야 한다."""
        payload = {"query": "재고자산", "year": 2014, "top_k": 3}
        r1 = real_client.post("/vector/search", json=payload).json()
        r2 = real_client.post("/vector/search", json=payload).json()
        assert r1["count"] == r2["count"]
        assert [r["id"] for r in r1["results"]] == [r["id"] for r in r2["results"]]
