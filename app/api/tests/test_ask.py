"""
/ask 엔드포인트는 /qa 로 이전되었습니다.
이 파일은 하위호환 확인용으로 유지합니다.
실제 QA 테스트는 test_qa.py 를 참고하세요.
"""
from fastapi.testclient import TestClient


def test_qa_replaces_ask(client: TestClient) -> None:
    """/ask 대신 /qa 가 정상 동작한다."""
    client.post("/reports/ingest", json={"year": 2023})
    response = client.post("/qa", json={"question": "2023년 감사의견은?", "year": 2023})
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert "question_type" in data
