"""FastAPI 애플리케이션 진입점."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import health, ingest, auth, chats, upload
from app.routes import chat as chat_qa  # qa.py → chat.py 로 리네임


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 1. DB 환경 준비 ──
    from app.db.init_db import create_tables
    create_tables()

    # ── 2. 데이터 파싱 파이프라인 자동 실행 (Raw -> Processed) ──
    # data/processed 디렉토리가 없거나 비어있는 경우를 위해 기동 시 자동 파싱 시도
    try:
        # config.py 에서 이미 sys.path 에 app/ingest/src 를 추가했으므로 직접 import 가능
        from pipeline import main as run_ingest_pipeline
        print("🚀 Starting auto-ingest pipeline (Raw -> Processed)...")
        run_ingest_pipeline()
        print("✅ Auto-ingest pipeline completed.")
    except Exception as e:
        print(f"⚠️ Failed to run auto-ingest pipeline: {e}")

    # ── 3. 검색 엔진 인덱싱 (Processed -> DB) ──
    from app.services import indexing, vector_store
    from app.core.config import settings as _cfg

    for year in range(2014, 2025):
        # (1) 인메모리 구조화 데이터 적재 (전체 모드 공통)
        try:
            indexing.ingest_year(year)
        except Exception:
            pass
        
        # (2) ChromaDB 벡터 데이터 적재 (Mock 모드 아닐 때만)
        if not _cfg.mock_mode:
            try:
                # 이미 적재된 연도는 함수 내부에서 자동으로 스킵함
                res = vector_store.index_year(year)
                if res.get("indexed", 0) > 0:
                    print(f"📦 Indexed ChromaDB text for year {year}: {res['indexed']} chunks added.")
            except Exception as e:
                # 인덱싱 실패가 서버 구동을 막지 않도록 로그만 출력
                if "Enriched data" not in str(e): # 파일 없는 경우는 흔하므로 스킵
                    print(f"⚠️ Failed to index ChromaDB text for year {year}: {e}")
                    
    # (3) 테이블 데이터 자동 적재
    if not _cfg.mock_mode:
        try:
            import subprocess
            import sys
            from pathlib import Path
            from app.services.vector_store import _COLLECTION_TABLE
            
            health_data = vector_store.health_check()
            stats = health_data.get("collection_stats", {})
            
            # 테이블 데이터가 0건이면 자동으로 적재 스크립트 실행
            if stats.get(_COLLECTION_TABLE, 0) == 0:
                print("🚀 Auto-indexing Table collection...")
                project_root = Path(__file__).resolve().parents[3]
                script_path = project_root / "chroma" / "load_table_to_chroma.py"
                
                if script_path.exists():
                    subprocess.run([sys.executable, str(script_path)], check=True)
                    print("✅ Auto-indexing Table collection completed.")
                else:
                    print(f"⚠️ Table loading script not found at {script_path}")
            else:
                table_cnt = stats.get(_COLLECTION_TABLE)
                print(f"🔄 Table collection already has {table_cnt} chunks. Skipping auto-load.")
        except Exception as e:
            print(f"⚠️ Failed to auto-index Table collection: {e}")

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

# ── 라우터 등록 (원본 상태로 완전 복구) ──────────────────────────────────────────────────

app.include_router(health.router, tags=["system"])

# vector 라우터는 chromadb 설치 시에만 등록
try:
    from app.routes import vector
    app.include_router(vector.router, tags=["vector"])
except ImportError:
    pass  # chromadb 미설치 환경에서는 스킵

# Frontend 연동용 API 엔드포인트
app.include_router(ingest.router, tags=["ingest"])
app.include_router(chat_qa.router, prefix="/api", tags=["chat"])
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(chats.router, prefix="/api", tags=["chats"])
app.include_router(upload.router, prefix="/api", tags=["upload"])
