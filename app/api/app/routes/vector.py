"""벡터 DB (ChromaDB) 관련 엔드포인트."""
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import vector_store

router = APIRouter(prefix="/vector", tags=["vector"])


# ── 응답 스키마 ───────────────────────────────────────────────────────────────

class VectorHealthResponse(BaseModel):
    """GET /vector/health 응답. 연도별 인덱싱 상태를 반환."""
    store: str                          # "ok" | "unavailable"
    indexed_years: list[int]            # 컬렉션 존재 + 1건 이상
    empty_years: list[int]              # 컬렉션 존재 + 0건
    missing_years: list[int]            # 컬렉션 자체 없음
    collection_stats: dict[str, int]    # {"2014": 1523, ...}
    error: str | None = None            # store="unavailable" 일 때만


class ChunkResult(BaseModel):
    """검색 결과 1건."""
    id: str
    document: str
    metadata: dict[str, Any]
    distance: float | None
    collection: str


class VectorSearchResponse(BaseModel):
    """POST /vector/search 응답."""
    query: str
    year: int | None
    results: list[ChunkResult]
    count: int
    warnings: list[str]                 # 미인덱싱 연도 등 운영 경고


# ── GET /vector/health ───────────────────────────────────────────────────────

@router.get("/health", response_model=VectorHealthResponse)
def vector_health() -> VectorHealthResponse:
    """
    연도별 ChromaDB 인덱싱 상태 반환. LLM 없이 동작.

    indexed_years 가 비어 있으면 팀원 chroma/ 스크립트가 아직 실행되지 않은 것.
    """
    return VectorHealthResponse(**vector_store.health_check())


# ── POST /vector/index ───────────────────────────────────────────────────────

class IndexRequest(BaseModel):
    year: int = Field(..., ge=2014, le=2024, description="인덱싱할 연도")
    force: bool = Field(False, description="True면 기존 컬렉션 삭제 후 재적재")


@router.post("/index")
def index_year(req: IndexRequest) -> dict:
    """
    enriched JSON → ChromaDB 비상 재적재.

    **정규 인덱싱 경로는 팀원의 chroma/load_{year}_to_chroma.py 스크립트.**
    이 엔드포인트는 스크립트 실행이 불가능한 환경(CI, 테스트서버 등)에서만 사용.
    """
    try:
        return vector_store.index_year(req.year, req.force)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── POST /vector/search ──────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str = Field(..., description="검색 질의")
    year: int | None = Field(None, ge=2014, le=2024, description="연도 필터 (None=전체)")
    top_k: int = Field(5, ge=1, le=20, description="반환할 최대 결과 수")


@router.post("/search", response_model=VectorSearchResponse)
def search(req: SearchRequest) -> VectorSearchResponse:
    """
    의미 유사도 기반 청크 검색. LLM 생성 없이 검색 결과만 반환.

    요청한 연도 컬렉션이 없으면 results=[] + warnings 에 안내 메시지.
    warnings 필드를 확인해 인덱싱 미완료 여부를 판단할 것.
    """
    data = vector_store.search(req.query, req.year, req.top_k)
    return VectorSearchResponse(
        query=req.query,
        year=req.year,
        results=data["results"],
        count=len(data["results"]),
        warnings=data["warnings"],
    )
