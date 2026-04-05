"""POST /reports/ingest — 연도별 processed JSON 을 인덱싱."""
from fastapi import APIRouter, HTTPException

from app.schemas.request import IngestRequest
from app.schemas.response import IngestResponse
from app.services import indexing

router = APIRouter()


@router.post("/reports/ingest", response_model=IngestResponse)
def ingest_report(req: IngestRequest) -> IngestResponse:
    """
    data/processed/audit_report_{year}_structured.json 을 읽어
    NormalizedDocument 로 변환 후 in-memory 인덱스에 저장.

    나중에 ChromaDB 색인으로 교체 시: indexing.ingest_year() 내부만 수정.
    """
    try:
        count = indexing.ingest_year(req.year, force=req.force)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if count == 0 and req.year in indexing.get_indexed_years():
        return IngestResponse(
            year=req.year,
            indexed_count=0,
            message=f"{req.year}년은 이미 인덱싱되어 있습니다. force=true 로 재인덱싱 가능합니다.",
        )

    return IngestResponse(
        year=req.year,
        indexed_count=count,
        message=f"{req.year}년 감사보고서 {count}개 문서 인덱싱 완료.",
    )
