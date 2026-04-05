"""사용자/OAuth 관련 Pydantic 응답 스키마."""
from datetime import datetime

from pydantic import BaseModel


class UserRead(BaseModel):
    id: int
    email: str
    name: str | None
    profile_image: str | None
    created_at: datetime

    model_config = {"from_attributes": True}  # SQLAlchemy ORM 객체에서 직접 변환 가능


class OAuthAccountRead(BaseModel):
    id: int
    provider: str
    provider_user_id: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}
