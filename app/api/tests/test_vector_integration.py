"""
ChromaDB 실제 통합 테스트.

mock 을 사용하지 않고 로컬 chroma_store 에 직접 접속하여
/api/vector/health 와 /api/vector/search 엔드포인트가 실제 데이터를
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
from app.services.vector_store import _COLLECTION_TABLE, _COLLECTION_TEXT

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


# ── GET /api/vector/health ────────────────────────────────────────────────────────

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

    def test_collection_stats_has_collections(self, real_client):
        """collection_stats 키가 10년치 컬렉션명이어야 한다."""
        data = real_client.get("/vector/health").json()
        assert _COLLECTION_TEXT in data["collection_stats"], (
            f"collection_stats 에 '{_COLLECTION_TEXT}' 키가 없습니다: {list(data['collection_stats'].keys())}"
        )
        assert data["collection_stats"][_COLLECTION_TEXT] > 0

    def test_collection_doc_counts(self, real_client):
        """text / table 컬렉션 모두 1000건 이상 적재되어 있어야 한다.
        정확한 건수는 팀원 로딩 스크립트 재실행 시 변할 수 있으므로 하드코딩하지 않는다.
        (로컬 확인 기준: text=1643건, table=1436건)
        """
        data = real_client.get("/vector/health").json()
        stats = data["collection_stats"]
        assert stats.get(_COLLECTION_TEXT, 0) >= 1000, (
            f"text 컬렉션 1000건 미만: {stats.get(_COLLECTION_TEXT, 0)}"
        )
        assert stats.get(_COLLECTION_TABLE, 0) >= 1000, (
            f"table 컬렉션 1000건 미만: {stats.get(_COLLECTION_TABLE, 0)}"
        )


# ── POST /api/vector/search ───────────────────────────────────────────────────────

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
        """결과 컬렉션명이 10년치 통합 컬렉션 중 하나여야 한다."""
        data = real_client.post(
            "/vector/search", json={"query": "감사의견", "year": 2014}
        ).json()
        assert data["results"][0]["collection"] in (_COLLECTION_TEXT, _COLLECTION_TABLE)

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

    def test_all_indexed_years_in_valid_range(self, real_client):
        """
        10년치 컬렉션이 적재된 환경에서 indexed_years 가 모두
        2014-2024 범위 안에 있어야 한다.
        (구 테스트: year=2020 미적재 가정 → 10년치 컬렉션 도입으로 전 연도 적재됨)
        """
        data = real_client.get("/vector/health").json()
        for year in data["indexed_years"]:
            assert 2014 <= year <= 2024, f"indexed_years 에 범위 밖 연도 포함: {year}"

    def test_multiple_queries_consistent(self, real_client):
        """같은 질의를 두 번 호출하면 동일한 결과를 반환해야 한다."""
        payload = {"query": "재고자산", "year": 2014, "top_k": 3}
        r1 = real_client.post("/vector/search", json=payload).json()
        r2 = real_client.post("/vector/search", json=payload).json()
        assert r1["count"] == r2["count"]
        assert [r["id"] for r in r1["results"]] == [r["id"] for r in r2["results"]]
