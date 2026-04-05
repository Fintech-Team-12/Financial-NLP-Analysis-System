"""FastAPI 애플리케이션 진입점."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routes import health, ingest, qa, vector


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: processed JSON → in-memory 인덱스 자동 적재
    # 파일이 없는 연도는 조용히 스킵 (FileNotFoundError 무시)
    from app.services.indexing import ingest_year
    for year in range(2014, 2025):
        try:
            ingest_year(year)
        except FileNotFoundError:
            pass
    yield


app = FastAPI(
    title="Financial Audit RAG API",
    description="감사보고서 기반 질의응답 API",
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(health.router, tags=["system"])
app.include_router(ingest.router, tags=["ingest"])
app.include_router(qa.router, tags=["qa"])
app.include_router(vector.router, tags=["vector"])
