"""
chat_history_service 단위 테스트.

- SQLite :memory: DB 사용
- 세션 생성 → 메시지 저장 → 조회의 전체 흐름을 검증
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
import app.db.models  # noqa: F401
from app.db.models import User
from app.services.chat_history_service import (
    add_message,
    create_chat_session,
    delete_session,
    get_session_by_id,
    list_session_messages,
    list_user_sessions,
)


# ── fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def test_user(db_session):
    """테스트용 사용자 1명을 미리 생성한다."""
    user = User(email="user@example.com", name="테스트유저")
    db_session.add(user)
    db_session.commit()
    return user


# ── 세션 생성 테스트 ──────────────────────────────────────────────────────────

def test_create_chat_session(db_session, test_user):
    """세션이 정상적으로 생성된다."""
    session = create_chat_session(db_session, user_id=test_user.id, title="첫 번째 대화")
    db_session.commit()

    assert session.id is not None
    assert session.user_id == test_user.id
    assert session.title == "첫 번째 대화"
    assert session.created_at is not None


def test_create_session_without_title(db_session, test_user):
    """제목 없이도 세션이 생성된다."""
    session = create_chat_session(db_session, user_id=test_user.id)
    db_session.commit()

    assert session.id is not None
    assert session.title is None


def test_user_can_have_multiple_sessions(db_session, test_user):
    """한 사용자가 여러 세션을 가질 수 있다."""
    s1 = create_chat_session(db_session, test_user.id, "세션1")
    s2 = create_chat_session(db_session, test_user.id, "세션2")
    db_session.commit()

    sessions = list_user_sessions(db_session, test_user.id)
    assert len(sessions) == 2


# ── 메시지 저장 테스트 ────────────────────────────────────────────────────────

def test_add_user_message(db_session, test_user):
    """사용자 메시지가 저장된다."""
    chat = create_chat_session(db_session, test_user.id)
    db_session.commit()

    msg = add_message(db_session, chat.id, role="user", content="2023년 매출채권 금액은?")
    db_session.commit()

    assert msg.id is not None
    assert msg.role == "user"
    assert msg.content == "2023년 매출채권 금액은?"


def test_add_assistant_message(db_session, test_user):
    """assistant 메시지가 저장된다."""
    chat = create_chat_session(db_session, test_user.id)
    db_session.commit()

    add_message(db_session, chat.id, "user", "질문")
    answer = add_message(db_session, chat.id, "assistant", "답변입니다.")
    db_session.commit()

    assert answer.role == "assistant"


def test_invalid_role_raises(db_session, test_user):
    """잘못된 role 은 ValueError 를 발생시킨다."""
    chat = create_chat_session(db_session, test_user.id)
    db_session.commit()

    with pytest.raises(ValueError, match="role"):
        add_message(db_session, chat.id, role="system", content="테스트")


# ── 메시지 조회 테스트 ────────────────────────────────────────────────────────

def test_list_session_messages_order(db_session, test_user):
    """메시지가 시간순(오래된 것부터)으로 반환된다."""
    chat = create_chat_session(db_session, test_user.id)
    db_session.commit()

    add_message(db_session, chat.id, "user", "첫 번째 질문")
    add_message(db_session, chat.id, "assistant", "첫 번째 답변")
    add_message(db_session, chat.id, "user", "두 번째 질문")
    db_session.commit()

    messages = list_session_messages(db_session, chat.id)
    assert len(messages) == 3
    assert messages[0].role == "user"
    assert messages[0].content == "첫 번째 질문"
    assert messages[2].content == "두 번째 질문"


def test_list_user_sessions_latest_first(db_session, test_user):
    """세션 목록은 최신순으로 반환된다."""
    s1 = create_chat_session(db_session, test_user.id, "오래된 세션")
    db_session.commit()

    # s2 에 메시지를 추가해서 updated_at 을 갱신
    s2 = create_chat_session(db_session, test_user.id, "최신 세션")
    add_message(db_session, s2.id, "user", "질문")
    db_session.commit()

    sessions = list_user_sessions(db_session, test_user.id)
    # updated_at 기준 내림차순 → s2 가 먼저
    assert sessions[0].id == s2.id


def test_list_user_sessions_empty(db_session, test_user):
    """세션이 없으면 빈 리스트를 반환한다."""
    sessions = list_user_sessions(db_session, test_user.id)
    assert sessions == []


def test_get_session_by_id(db_session, test_user):
    chat = create_chat_session(db_session, test_user.id, "조회 테스트")
    db_session.commit()

    found = get_session_by_id(db_session, chat.id)
    assert found is not None
    assert found.title == "조회 테스트"


def test_get_session_by_id_not_found(db_session):
    assert get_session_by_id(db_session, 9999) is None


# ── 삭제 테스트 ───────────────────────────────────────────────────────────────

def test_delete_session_cascade(db_session, test_user):
    """세션 삭제 시 하위 메시지도 함께 삭제된다."""
    chat = create_chat_session(db_session, test_user.id)
    db_session.commit()
    add_message(db_session, chat.id, "user", "삭제될 메시지")
    db_session.commit()

    result = delete_session(db_session, chat.id)
    db_session.commit()

    assert result is True
    assert get_session_by_id(db_session, chat.id) is None
    assert list_session_messages(db_session, chat.id) == []


def test_delete_nonexistent_session(db_session):
    """존재하지 않는 세션 삭제는 False 를 반환한다."""
    result = delete_session(db_session, 9999)
    assert result is False
