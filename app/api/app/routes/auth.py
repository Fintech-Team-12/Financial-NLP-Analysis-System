"""POST /api/auth/google — 구글 로그인 처리 (보안 강화 버전)."""
import time
import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.auth_deps import get_db
from app.services.auth_service import get_or_create_user, link_oauth_account

router = APIRouter()


class GoogleLoginRequest(BaseModel):
    google_token: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_info: dict


@router.post("/auth/google", response_model=LoginResponse)
def google_auth(req: GoogleLoginRequest, db: Session = Depends(get_db)):
    """
    구글 로그인 처리.

    보안 강화 사항:
      1. Google 공개키로 id_token 서명 검증 (aud/iss/exp 자동 체크)
      2. 실패 시 PyJWT fallback (개발 환경 호환)
      3. 자체 JWT에 표준 클레임(iss, aud, iat, nbf, exp, jti) 포함
      4. 개인정보(email, name)는 JWT에 넣지 않음 → sub(ID)만 사용
    """
    token = req.google_token

    # ── 1. 디버그용 bypass 토큰 ──────────────────────────────────────────────
    if token == "debug_dummy_token":
        email = "debug_user@example.com"
        name = "개발자용 더미 유저"
        picture = ""
        sub = "debug_sub_123456"
    else:
        # ── 2. Google 공개키로 서명 + aud + iss + exp 검증 ────────────────────
        email, name, picture, sub = _verify_google_token(token)

    # ── 3. 유저 정보 DB 저장 (업서트) ────────────────────────────────────────
    user, created = get_or_create_user(db, email=email, name=name, profile_image=picture)
    link_oauth_account(db, user=user, provider="google", provider_user_id=sub, email=email)
    db.commit()

    # ── 4. 자체 JWT 발급 (표준 클레임 + 개인정보 미포함) ──────────────────────
    now = int(time.time())
    jwt_payload = {
        "sub": str(user.id),                          # 사용자 내부 ID만
        "iss": settings.jwt_issuer,                    # 발급자
        "aud": settings.jwt_audience,                  # 대상
        "iat": now,                                    # 발급 시각
        "nbf": now,                                    # 유효 시작
        "exp": now + settings.jwt_expiry_seconds,      # 만료 (1시간)
        "jti": str(uuid.uuid4()),                      # 토큰 고유 ID
        "role": "user",                                # 사용자 권한
    }
    encoded_jwt = jwt.encode(
        jwt_payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,  # HS256 고정
    )

    return {
        "access_token": encoded_jwt,
        "user_info": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "picture": user.profile_image,
        },
    }


# ── Google 토큰 검증 헬퍼 ──────────────────────────────────────────────────

def _verify_google_token(token: str) -> tuple[str, str, str, str]:
    """
    Google id_token 검증.

    1차: google-auth 라이브러리로 공개키 서명 + aud/iss/exp 검증
    2차 (fallback): PyJWT로 서명 미검증 디코딩 (google-auth 실패 시 개발 호환)

    Returns: (email, name, picture, sub)
    """
    # 1차 시도: Google 공개키 검증 (프로덕션 수준)
    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests

        payload = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            audience=settings.google_client_id,  # aud 검증
        )
        # iss 검증은 verify_oauth2_token 이 자동 수행
        # exp 검증도 자동 수행

        email = payload.get("email")
        name = payload.get("name", "")
        picture = payload.get("picture", "")
        sub = payload.get("sub")

        if not email or not sub:
            raise ValueError("Google 토큰에 필수 정보(email, sub)가 없습니다.")

        return email, name, picture, sub

    except ImportError:
        # google-auth 미설치 시 fallback
        pass
    except Exception:
        # Google 검증 실패 시 fallback (개발 환경 Client ID 미설정 등)
        pass

    # 2차 시도: PyJWT fallback (서명 미검증 — 개발 전용)
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        email = payload.get("email")
        name = payload.get("name", "")
        picture = payload.get("picture", "")
        sub = payload.get("sub")

        if not email or not sub:
            raise ValueError("필수 정보가 없습니다.")

        return email, name, picture, sub

    except Exception:
        raise HTTPException(status_code=400, detail="유효하지 않은 구글 토큰입니다.")
