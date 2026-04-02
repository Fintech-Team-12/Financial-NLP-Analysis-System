"""API 응답 스키마."""
from typing import Optional

from pydantic import BaseModel


class Citation(BaseModel):
    """개별 인용 출처."""
    doc_id: str
    year: int
    section: str
    excerpt: str                           # content 앞 200자
    numeric_value: Optional[dict] = None   # 숫자형 질문일 때 구조화 값 포함


class QAResponse(BaseModel):
    answer: str
    citations: list[Citation]
    question_type: str                     # "numeric" | "note_linked" | "descriptive"
    used_documents: list[str]              # doc_id 리스트


class IngestResponse(BaseModel):
    year: int
    indexed_count: int
    message: str


class HealthResponse(BaseModel):
    status: str
    indexed_years: list[int]
    total_documents: int
