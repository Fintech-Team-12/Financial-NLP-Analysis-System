"""
/ask 엔드포인트는 /qa 를 거쳐 현재 /chat 으로 이전되었습니다.
이 파일은 하위호환 확인용으로 유지합니다.
실제 채팅 테스트는 test_qa.py 를 참고하세요.
"""
from fastapi.testclient import TestClient


def test_chat_replaces_qa(auth_client: TestClient) -> None:
    """/qa 대신 /chat 이 정상 동작한다."""
    auth_client.post("/api/reports/reports/ingest", json={"year": 2023})
    response = auth_client.post("/api/chat/chat", json={"question": "2023년 감사의견은?", "year": 2023})
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert "question_type" in data
    assert "chat_id" in data
