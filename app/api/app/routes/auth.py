"""POST /api/auth/google — 구글 로그인 처리."""
import time
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
    구글 로그인 처리. 현재는 id_token을 직접 검증하지 않고
    디코딩으로 정보만 추출하여 로그인 처리합니다.
    """
    token = req.google_token
    
    # 1. 디버그용 bypass 토큰
    if token == "debug_dummy_token":
        email = "debug_user@example.com"
        name = "개발자용 더미 유저"
        picture = ""
        sub = "debug_sub_123456"
    else:
        # 실제 구글 id_token에서 페이로드 파싱 (서명 검증 생략)
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            email = payload.get("email")
            name = payload.get("name")
            picture = payload.get("picture", "")
            sub = payload.get("sub")
            
            if not email or not sub:
                raise ValueError("필수 정보가 없습니다.")
        except Exception:
            raise HTTPException(status_code=400, detail="유효하지 않은 구글 토큰입니다.")

    # 2. 유저 정보 DB 저장 (업서트)
    user, created = get_or_create_user(db, email=email, name=name, profile_image=picture)
    
    # 3. OAuth 연결 정보 저장
    link_oauth_account(db, user=user, provider="google", provider_user_id=sub, email=email)
    
    # DB 커밋 적용 (get_or_create_user 에서 flush 만 했음)
    db.commit()

    # 4. 자체 JWT 발급
    jwt_payload = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "exp": int(time.time()) + 3600 * 24 * 7  # 7일
    }
    encoded_jwt = jwt.encode(jwt_payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    return {
        "access_token": encoded_jwt,
        "user_info": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "picture": user.profile_image
        }
    }
