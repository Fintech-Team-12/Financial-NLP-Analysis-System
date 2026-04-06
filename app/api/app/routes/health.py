"""GET /health — 서비스 상태 및 색인 현황."""
from fastapi import APIRouter

from app.schemas.response import HealthResponse
from app.services import indexing

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        indexed_years=indexing.get_indexed_years(),
        total_documents=indexing.get_document_count(),
    )
