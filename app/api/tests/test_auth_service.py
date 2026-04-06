"""
auth_service 단위 테스트.

- SQLite :memory: DB 사용 → 파일 생성 없음, 테스트 간 격리
- HTTP 레이어 없이 service 함수만 직접 테스트
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
import app.db.models  # noqa: F401 — Base.metadata 에 테이블 등록
from app.services.auth_service import (
    get_or_create_user,
    get_user_by_email,
    get_user_by_id,
    get_oauth_account,
    link_oauth_account,
)


# ── fixture: 테스트용 인메모리 DB ─────────────────────────────────────────────

@pytest.fixture
def db_session():
    """각 테스트마다 깨끗한 :memory: DB 세션을 제공한다."""
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


# ── 사용자 생성/조회 테스트 ───────────────────────────────────────────────────

def test_create_user(db_session):
    """새 사용자가 정상적으로 생성된다."""
    user, created = get_or_create_user(db_session, email="test@example.com", name="홍길동")
    assert created is True
    assert user.id is not None
    assert user.email == "test@example.com"
    assert user.name == "홍길동"


def test_get_existing_user(db_session):
    """이미 존재하는 이메일로 조회하면 created=False 를 반환한다."""
    get_or_create_user(db_session, email="test@example.com")
    db_session.commit()

    user, created = get_or_create_user(db_session, email="test@example.com")
    assert created is False
    assert user.email == "test@example.com"


def test_get_user_by_email_found(db_session):
    user, _ = get_or_create_user(db_session, email="find@example.com")
    db_session.commit()

    found = get_user_by_email(db_session, "find@example.com")
    assert found is not None
    assert found.id == user.id


def test_get_user_by_email_not_found(db_session):
    result = get_user_by_email(db_session, "nobody@example.com")
    assert result is None


def test_get_user_by_id(db_session):
    user, _ = get_or_create_user(db_session, email="byid@example.com")
    db_session.commit()

    found = get_user_by_id(db_session, user.id)
    assert found is not None
    assert found.email == "byid@example.com"


def test_email_uniqueness(db_session):
    """동일 이메일로 두 번 생성해도 레코드는 하나여야 한다."""
    _, c1 = get_or_create_user(db_session, email="dup@example.com")
    db_session.commit()
    _, c2 = get_or_create_user(db_session, email="dup@example.com")

    assert c1 is True
    assert c2 is False


# ── OAuth 계정 연결 테스트 ────────────────────────────────────────────────────

def test_link_oauth_account(db_session):
    """OAuth 계정을 사용자에게 연결한다."""
    user, _ = get_or_create_user(db_session, email="oauth@example.com")
    db_session.commit()

    account = link_oauth_account(
        db_session,
        user=user,
        provider="google",
        provider_user_id="google-sub-12345",
        email="oauth@example.com",
    )
    db_session.commit()

    assert account.id is not None
    assert account.user_id == user.id
    assert account.provider == "google"
    assert account.provider_user_id == "google-sub-12345"


def test_link_oauth_account_idempotent(db_session):
    """같은 OAuth 계정을 두 번 연결해도 레코드는 하나여야 한다."""
    user, _ = get_or_create_user(db_session, email="oauth2@example.com")
    db_session.commit()

    a1 = link_oauth_account(db_session, user, "google", "sub-abc", "oauth2@example.com")
    db_session.commit()
    a2 = link_oauth_account(db_session, user, "google", "sub-abc", "oauth2@example.com")
    db_session.commit()

    assert a1.id == a2.id  # 동일 레코드


def test_get_oauth_account_not_found(db_session):
    result = get_oauth_account(db_session, "google", "nonexistent-sub")
    assert result is None


def test_multiple_oauth_providers(db_session):
    """한 사용자가 여러 공급자 계정을 가질 수 있다."""
    user, _ = get_or_create_user(db_session, email="multi@example.com")
    db_session.commit()

    link_oauth_account(db_session, user, "google", "google-sub", "multi@example.com")
    # 나중에 kakao 등 추가 가능한 구조인지 확인
    link_oauth_account(db_session, user, "kakao", "kakao-sub", "multi@example.com")
    db_session.commit()

    assert len(user.oauth_accounts) == 2
