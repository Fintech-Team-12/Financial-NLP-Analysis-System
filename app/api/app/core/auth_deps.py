"""
인증 관련 의존성(Dependencies).
"""
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jwt.exceptions import InvalidTokenError

from app.core.config import settings
from app.db.models import User
from app.db.session import SessionLocal

security = HTTPBearer()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    JWT 토큰을 검증하고 현재 사용자를 반환.

    검증 항목:
      - 서명 (jwt_secret_key + HS256 고정)
      - iss: 우리 서버가 발급한 토큰인지
      - aud: 프론트엔드용 토큰인지
      - exp: 만료되지 않았는지
      - nbf: 유효 시작 시각이 지났는지
    """
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="토큰이 유효하지 않습니다",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],  # 알고리즘 고정 (none 공격 방어)
            issuer=settings.jwt_issuer,            # iss 검증
            audience=settings.jwt_audience,        # aud 검증
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception

    # sub(내부 ID)로 유저 조회 — email을 JWT에 넣지 않으므로
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    return user
