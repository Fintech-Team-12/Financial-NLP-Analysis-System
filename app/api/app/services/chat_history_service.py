"""
채팅 이력 서비스.

대화 흐름:
    1. 사용자 로그인 → create_chat_session() 으로 세션 생성
    2. 사용자 질문 → add_message(role="user", content=질문)
    3. backend 답변 → add_message(role="assistant", content=답변)
    4. 이후 재방문 시 list_user_sessions() + list_session_messages() 로 복원

이 서비스는 RAG 문서 검색(retrieval.py, indexing.py)과 완전히 분리되어 있다.
QA 파이프라인의 답변을 저장하려면 routes/qa.py 에서
add_message() 를 호출하면 된다.
"""
from sqlalchemy.orm import Session

from app.db.models import ChatMessage, ChatSession


def create_chat_session(
    session: Session,
    user_id: int,
    title: str | None = None,
) -> ChatSession:
    """
    새 대화 세션을 생성한다.

    title 을 None 으로 두면 첫 메시지 내용으로 나중에 채워도 됨.
    """
    chat_session = ChatSession(user_id=user_id, title=title)
    session.add(chat_session)
    session.flush()  # id 즉시 확보
    return chat_session


def add_message(
    session: Session,
    session_id: int,
    role: str,
    content: str,
) -> ChatMessage:
    """
    세션에 메시지를 추가한다.

    role: "user" 또는 "assistant"
    content: 질문 또는 답변 텍스트
    """
    if role not in ("user", "assistant"):
        raise ValueError(f"role 은 'user' 또는 'assistant' 이어야 합니다. 받은 값: {role!r}")

    message = ChatMessage(session_id=session_id, role=role, content=content)
    session.add(message)

    # 세션의 updated_at 갱신 (마지막 활동 시각 추적)
    chat_session = session.get(ChatSession, session_id)
    if chat_session:
        from datetime import datetime, timezone
        chat_session.updated_at = datetime.now(timezone.utc)

    session.flush()
    return message


def get_session_by_id(session: Session, session_id: int) -> ChatSession | None:
    """세션 ID 로 단일 세션 조회."""
    return session.get(ChatSession, session_id)


def list_user_sessions(
    session: Session,
    user_id: int,
    limit: int = 50,
) -> list[ChatSession]:
    """
    사용자의 대화 세션 목록을 최신순으로 반환한다.

    limit: 최대 반환 개수 (기본 50)
    """
    return (
        session.query(ChatSession)
        .filter(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc())
        .limit(limit)
        .all()
    )


def list_session_messages(
    session: Session,
    session_id: int,
) -> list[ChatMessage]:
    """
    세션의 메시지를 시간순(오래된 것부터)으로 반환한다.
    대화 복원 시 이 순서대로 렌더링하면 된다.
    """
    return (
        session.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )


def delete_session(session: Session, session_id: int) -> bool:
    """
    세션과 하위 메시지를 삭제한다 (cascade).
    삭제 성공 시 True, 세션이 없으면 False.
    """
    chat_session = session.get(ChatSession, session_id)
    if not chat_session:
        return False
    session.delete(chat_session)
    session.flush()
    return True
