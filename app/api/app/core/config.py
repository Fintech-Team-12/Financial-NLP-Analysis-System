"""
애플리케이션 설정.
환경변수로 주입 — Docker / 로컬 / 테스트 환경 모두 동일 코드로 동작.
"""
import os
from pathlib import Path


class Settings:
    # ── 데이터 경로 ────────────────────────────────────────────────────────────
    # Docker: WORKDIR=/workspace, data 볼륨은 /workspace/data 로 마운트됨
    # 로컬:   프로젝트 루트 기준 data/processed (PYTHONPATH=app/api 로 실행 가정)
    # 테스트: conftest.py 에서 settings.data_dir 을 임시 경로로 덮어씀
    # 로컬 실행 시 app/api/ 디렉토리에서 실행되므로 프로젝트 루트 기준으로 경로 설정
    data_dir: str = os.getenv("DATA_DIR", str(Path(__file__).resolve().parents[4] / "data" / "processed"))

    # ── 동작 모드 ─────────────────────────────────────────────────────────────
    # True  → MockRetriever + MockGenerator (Chroma/Ollama 불필요)
    # False → ChromaRetriever + OllamaGenerator (담당자 구현 후 교체)
    mock_mode: bool = os.getenv("MOCK_MODE", "true").lower() == "true"

    # ── ChromaDB — PersistentClient 경로 (현재 사용) ──────────────────────────
    # 팀원 chroma/load_*.py 가 "./chroma_store" 에 적재.
    # 백엔드는 동일 경로를 읽기 전용으로 사용하는 것이 원칙.
    # Docker: WORKDIR=/workspace → /workspace/chroma_store
    chroma_persist_path: str = os.getenv("CHROMA_PERSIST_PATH", "chroma_store")

    # enriched JSON 위치 — POST /vector/index (비상 재적재 용도) 에서만 사용
    # 팀원 enrich_flattened_for_rag.py 출력 디렉토리와 동일
    chroma_enriched_data_dir: str = os.getenv(
        "CHROMA_ENRICHED_DATA_DIR", "chroma/enriched_data"
    )

    # ── ChromaDB — HTTP 클라이언트 (미래 확장, 현재 미사용) ─────────────────
    # docker-compose 에서 Chroma 를 별도 서비스로 분리할 때 사용 예정.
    # 현재 vector_store.py 는 PersistentClient 만 사용.
    chroma_host: str = os.getenv("CHROMA_HOST", "localhost")
    chroma_port: int = int(os.getenv("CHROMA_PORT", "8000"))
    # NOTE: 컬렉션은 연도별로 "audit_reports_{year}" 형식. 단일 컬렉션명 변수 없음.

    # ── Ollama 연결 (mock_mode=False 일 때 사용) ─────────────────────────────
    # docker-compose.yml: OLLAMA_BASE_URL=http://host.docker.internal:11434
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3")

    # ── 사용자/채팅 이력용 SQLite (RAG 벡터 데이터와 분리) ────────────────────
    # Docker: /workspace/data/app.db (data 볼륨에 마운트)
    # 로컬:   data/app.db
    # 테스트: conftest 에서 "sqlite:///:memory:" 로 덮어씀
    db_url: str = os.getenv("APP_DB_URL", "sqlite:///data/app.db")

    # ── JWT & Google OAuth ────────────────────────────────────────────────────────
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "my_super_secret_jwt_key")
    jwt_algorithm: str = "HS256"
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "YOUR_GOOGLE_CLIENT_ID_HERE.apps.googleusercontent.com")

    def get_data_path(self, year: int) -> Path:
        """연도별 processed JSON 파일 경로 반환."""
        return Path(self.data_dir) / f"삼성전자_audit_report_{year}_structured.json"


# 모듈 수준 싱글턴 — 테스트에서 settings.data_dir = "..." 으로 직접 덮어쓰기 가능
settings = Settings()
