"""API 요청 스키마."""
from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, description="질문 텍스트")
    year: Optional[int] = Field(None, ge=2014, le=2030, description="특정 연도 (없으면 전체)")
    top_k: int = Field(5, ge=1, le=20, description="검색 결과 수")
    chat_id: Optional[int] = Field(None, description="기존 대화 세션 ID (없으면 새 대화)")

    # LLM 선택 — 미지정 시 서버 기본값(환경변수) 사용
    provider: Optional[str] = Field(None, description="'ollama' | 'claude' | 'mock'")
    model: Optional[str] = Field(None, description="모델명 (Ollama: 'llama3', Claude: 'claude-sonnet-4-6' 등)")

    model_config = {"json_schema_extra": {"example": {
        "question": "2023년 매출채권 금액은?",
        "year": 2023,
        "provider": "ollama",
        "model": "llama3",
    }}}


class IngestRequest(BaseModel):
    year: int = Field(..., ge=2014, le=2030, description="인덱싱할 연도")
    force: bool = Field(False, description="이미 인덱싱된 연도도 재인덱싱")

    model_config = {"json_schema_extra": {"example": {"year": 2023, "force": False}}}
