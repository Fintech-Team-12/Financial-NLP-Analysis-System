"""GET /health 엔드포인트 테스트."""
from fastapi.testclient import TestClient


def test_health_status(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_health_schema(client: TestClient) -> None:
    """응답에 indexed_years, total_documents 필드가 있어야 한다."""
    data = client.get("/health").json()
    assert "indexed_years" in data
    assert "total_documents" in data
    assert isinstance(data["indexed_years"], list)
    assert isinstance(data["total_documents"], int)


def test_health_empty_before_ingest(client: TestClient) -> None:
    """인덱싱 전에는 문서 수 0."""
    data = client.get("/health").json()
    assert data["total_documents"] == 0
    assert data["indexed_years"] == []


def test_health_after_ingest(client: TestClient) -> None:
    """인덱싱 후 문서 수가 증가하고 연도가 등록된다."""
    client.post("/api/reports/ingest", json={"year": 2023})
    data = client.get("/health").json()
    assert data["total_documents"] > 0
    assert 2023 in data["indexed_years"]
