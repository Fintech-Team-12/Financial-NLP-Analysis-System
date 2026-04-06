"""채팅 세션/메시지 관련 Pydantic 스키마."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ── 요청 스키마 ───────────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    title: str | None = Field(None, max_length=255, description="세션 제목 (없으면 자동 생성)")

    model_config = {"json_schema_extra": {"example": {"title": "2023년 재무 분석"}}}


class AddMessageRequest(BaseModel):
    role: Literal["user", "assistant"] = Field(..., description="'user' 또는 'assistant'")
    content: str = Field(..., min_length=1, description="메시지 내용")

    model_config = {
        "json_schema_extra": {"example": {"role": "user", "content": "2023년 매출채권 금액은?"}}
    }


# ── 응답 스키마 ───────────────────────────────────────────────────────────────

class ChatMessageRead(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionRead(BaseModel):
    id: int
    user_id: int
    title: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionDetail(ChatSessionRead):
    """메시지 목록까지 포함한 세션 상세."""
    messages: list[ChatMessageRead] = []
