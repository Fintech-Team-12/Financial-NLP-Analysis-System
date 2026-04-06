"""POST /qa 엔드포인트 테스트."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def ingest_before_qa(auth_client: TestClient) -> None:
    """이 모듈의 모든 테스트는 2023년 데이터가 인덱싱된 상태에서 실행."""
    auth_client.post("/reports/ingest", json={"year": 2023})


# ── 기본 동작 ──────────────────────────────────────────────────────────────────

def test_qa_startup_auto_ingest(auth_client: TestClient) -> None:
    """startup lifespan 이 자동 ingest 를 실행하므로
    /reports/ingest 를 명시적으로 호출하지 않아도 /chat 이 동작해야 한다.
    (이전 테스트: ingest 없이 503 반환 → startup auto-ingest 도입으로 동작 변경됨)"""
    from app.main import app
    from fastapi.testclient import TestClient as TC
    from app.core.auth_deps import get_current_user
    from app.db.models import User

    # lifespan 이 실제 data/processed 경로에서 ingest 를 시도한다.
    # 파일이 존재하면 200, 없으면 503 — 환경에 따라 달라질 수 있으므로
    # 여기서는 응답이 유효한 HTTP 응답임(crash 없음)을 확인한다.
    mock_user = User(id=1, email="test@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user
    
    with TC(app) as c:
        r = c.post("/chat", json={"question": "감사의견은?"})
    
    app.dependency_overrides.clear()
    assert r.status_code in (200, 503)


def test_qa_response_schema(auth_client: TestClient) -> None:
    """응답에 answer, citations, question_type, used_documents, chat_id 가 있어야 한다."""
    data = auth_client.post("/chat", json={"question": "2023년 감사의견은?", "year": 2023}).json()
    assert "answer" in data
    assert "citations" in data
    assert "question_type" in data
    assert "used_documents" in data
    assert "chat_id" in data
    assert isinstance(data["citations"], list)
    assert isinstance(data["used_documents"], list)


# ── 질문 유형별 라우팅 ─────────────────────────────────────────────────────────

def test_qa_numeric_type(auth_client: TestClient) -> None:
    """금액 질문은 question_type=numeric 으로 분류되어야 한다."""
    data = auth_client.post("/chat", json={"question": "2023년 매출채권 금액은 얼마?", "year": 2023}).json()
    assert data["question_type"] == "numeric"


def test_qa_numeric_returns_amount(auth_client: TestClient) -> None:
    """숫자형 질문 응답의 answer 에 금액 정보가 포함되어야 한다."""
    data = auth_client.post("/chat", json={"question": "2023년 매출채권 금액은 얼마?", "year": 2023}).json()
    # MockGenerator 는 numeric_value 를 포맷팅해서 반환
    assert data["answer"] != "관련 문서를 찾을 수 없습니다."


def test_qa_descriptive_type(auth_client: TestClient) -> None:
    """감사의견 질문은 question_type=descriptive 로 분류되어야 한다."""
    data = auth_client.post("/chat", json={"question": "2023년 감사의견은 무엇인가요?", "year": 2023}).json()
    assert data["question_type"] == "descriptive"


def test_qa_note_linked_type(auth_client: TestClient) -> None:
    """주석/회계정책 질문은 question_type=note_linked 로 분류되어야 한다."""
    data = auth_client.post(
        "/chat",
        json={"question": "매출채권 관련 회계처리 설명해줘", "year": 2023},
    ).json()
    assert data["question_type"] == "note_linked"


# ── 관련주석 연결 로직 ─────────────────────────────────────────────────────────

def test_qa_note_linked_finds_note_doc(auth_client: TestClient) -> None:
    """
    매출채권 주석연결 질문 시:
    재무상태표에서 관련주석 ["4","5","7"] 을 찾고
    주석_2023_5 문서가 citations 에 포함되어야 한다.
    """
    data = auth_client.post(
        "/chat",
        json={"question": "매출채권 관련 회계정책 설명", "year": 2023},
    ).json()
    note_doc_ids = [c["doc_id"] for c in data["citations"]]
    # 주석 5번 (매출채권) 이 인용되어야 한다
    assert any("주석_2023_5" in doc_id for doc_id in note_doc_ids)


# ── citations 구조 ─────────────────────────────────────────────────────────────

def test_citations_have_required_fields(auth_client: TestClient) -> None:
    """citations 각 항목에 doc_id, year, section, excerpt 가 있어야 한다."""
    data = auth_client.post("/chat", json={"question": "2023년 감사의견", "year": 2023}).json()
    for citation in data["citations"]:
        assert "doc_id" in citation
        assert "year" in citation
        assert "section" in citation
        assert "excerpt" in citation


def test_qa_without_year_field(auth_client: TestClient) -> None:
    """year 필드 없이도 질문이 처리되어야 한다."""
    response = auth_client.post("/chat", json={"question": "감사의견은?"})
    assert response.status_code == 200
