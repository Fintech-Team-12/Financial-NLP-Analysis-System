"""FastAPI 애플리케이션 진입점."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routes import health, ingest, qa, vector


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: 필요 시 특정 연도 자동 인덱싱 추가 가능
    # 예) from app.services.indexing import ingest_year; ingest_year(2023)
    yield
    # shutdown: 정리 작업 추가 가능


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
