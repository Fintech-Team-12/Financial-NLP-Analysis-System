from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)


def test_ask_stub() -> None:
    response = client.post("/ask", json={"question": "2024년 감사의견은?", "year": 2024})
    assert response.status_code == 200
    data = response.json()
    assert data["question"] == "2024년 감사의견은?"
    assert data["year"] == 2024
    assert "answer" in data
