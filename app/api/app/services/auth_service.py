"""
사용자 인증/관리 서비스.

Google OAuth flow:
    1. 프론트가 Google 로그인 후 id_token 을 backend 로 전달
    2. backend 는 id_token 에서 sub(provider_user_id), email, name 추출
    3. get_or_create_user() 로 users 테이블에 upsert
    4. link_oauth_account() 로 oauth_accounts 테이블에 연결

현재는 실제 토큰 검증 없이 DB CRUD 계층만 구현.
토큰 검증 추가 시: google-auth 라이브러리로 id_token 을 verify 하고
추출한 값을 이 함수에 넘기면 된다.
"""
from sqlalchemy.orm import Session

from app.db.models import OAuthAccount, User


def get_user_by_email(session: Session, email: str) -> User | None:
    """이메일로 사용자 조회. 없으면 None 반환."""
    return session.query(User).filter(User.email == email).first()


def get_user_by_id(session: Session, user_id: int) -> User | None:
    """PK 로 사용자 조회."""
    return session.get(User, user_id)


def get_or_create_user(
    session: Session,
    email: str,
    name: str | None = None,
    profile_image: str | None = None,
) -> tuple[User, bool]:
    """
    이메일 기준으로 사용자를 조회하거나 새로 생성한다.

    반환: (user, created)
        created=True  → 새로 생성됨
        created=False → 기존 사용자
    """
    user = get_user_by_email(session, email)
    if user:
        return user, False

    user = User(email=email, name=name, profile_image=profile_image)
    session.add(user)
    session.flush()  # id 를 바로 얻기 위해 flush (commit 은 호출자가 담당)
    return user, True


def get_oauth_account(
    session: Session,
    provider: str,
    provider_user_id: str,
) -> OAuthAccount | None:
    """공급자 + 공급자 계정 ID 로 oauth_accounts 조회."""
    return (
        session.query(OAuthAccount)
        .filter(
            OAuthAccount.provider == provider,
            OAuthAccount.provider_user_id == provider_user_id,
        )
        .first()
    )


def link_oauth_account(
    session: Session,
    user: User,
    provider: str,
    provider_user_id: str,
    email: str,
) -> OAuthAccount:
    """
    사용자에게 OAuth 계정을 연결한다.

    이미 연결된 경우 기존 레코드를 반환 (upsert 느낌).
    Google 로그인 시: provider="google", provider_user_id=id_token["sub"]
    """
    existing = get_oauth_account(session, provider, provider_user_id)
    if existing:
        return existing

    account = OAuthAccount(
        user_id=user.id,
        provider=provider,
        provider_user_id=provider_user_id,
        email=email,
    )
    session.add(account)
    session.flush()
    return account
