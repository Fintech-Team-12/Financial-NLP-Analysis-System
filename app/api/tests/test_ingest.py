"""POST /reports/ingest 엔드포인트 테스트."""
from fastapi.testclient import TestClient


def test_ingest_valid_year(client: TestClient) -> None:
    """sample 데이터가 있는 2023년은 인덱싱 성공해야 한다."""
    response = client.post("/api/reports/ingest", json={"year": 2023})
    assert response.status_code == 200
    data = response.json()
    assert data["year"] == 2023
    assert data["indexed_count"] > 0
    assert "완료" in data["message"]


def test_ingest_creates_documents(client: TestClient) -> None:
    """인덱싱 후 /health 에서 문서 수가 증가해야 한다."""
    client.post("/api/reports/ingest", json={"year": 2023})
    health = client.get("/health").json()
    assert health["total_documents"] > 0


def test_ingest_missing_year(client: TestClient) -> None:
    """processed 파일이 없는 연도(샘플에는 2023만 있음)는 404 를 반환해야 한다."""
    response = client.post("/api/reports/ingest", json={"year": 2025})
    assert response.status_code == 404


def test_ingest_already_indexed_returns_zero(client: TestClient) -> None:
    """같은 연도를 두 번 요청하면 indexed_count=0 을 반환해야 한다."""
    client.post("/api/reports/ingest", json={"year": 2023})
    response = client.post("/api/reports/ingest", json={"year": 2023})
    assert response.status_code == 200
    assert response.json()["indexed_count"] == 0


def test_ingest_force_reindex(client: TestClient) -> None:
    """force=True 이면 이미 인덱싱된 연도도 재인덱싱해야 한다."""
    client.post("/api/reports/ingest", json={"year": 2023})
    first_count = client.get("/health").json()["total_documents"]

    response = client.post("/api/reports/ingest", json={"year": 2023, "force": True})
    assert response.status_code == 200
    assert response.json()["indexed_count"] > 0
    # 재인덱싱 후 문서 수는 동일해야 함 (중복 없이 교체)
    second_count = client.get("/health").json()["total_documents"]
    assert second_count == first_count


def test_ingest_response_schema(client: TestClient) -> None:
    """응답에 year, indexed_count, message 필드가 있어야 한다."""
    data = client.post("/api/reports/ingest", json={"year": 2023}).json()
    assert "year" in data
    assert "indexed_count" in data
    assert "message" in data
