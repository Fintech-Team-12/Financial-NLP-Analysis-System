"""FastAPI 애플리케이션 진입점."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import health, ingest, auth, chats, upload
from app.routes import chat as chat_qa  # qa.py → chat.py 로 리네임


@asynccontextmanager
async def lifespan(app: FastAPI):
    # DB 테이블 자동 생성
    from app.db.init_db import create_tables
    create_tables()

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["system"])
# app.include_router(ingest.router, tags=["ingest"]) # Moved below

# vector 라우터는 chromadb 설치 시에만 등록
try:
    from app.routes import vector
    app.include_router(vector.router, tags=["vector"])
except ImportError:
    pass  # chromadb 미설치 환경에서는 스킵

# Frontend 연동용 API 엔드포인트
app.include_router(ingest.router, prefix="/api", tags=["ingest"])
app.include_router(chat_qa.router, prefix="/api", tags=["chat"])
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(chats.router, prefix="/api", tags=["chats"])
app.include_router(upload.router, prefix="/api", tags=["upload"])
