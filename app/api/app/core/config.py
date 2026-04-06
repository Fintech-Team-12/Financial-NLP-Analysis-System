"""
애플리케이션 설정.
환경변수로 주입 — Docker / 로컬 / 테스트 환경 모두 동일 코드로 동작.

.env 파일 로딩:
  app/api/.env 또는 프로젝트 루트 .env 중 존재하는 파일을 자동으로 읽는다.
  이미 설정된 환경변수는 .env 로 덮어쓰지 않는다 (override=False).
"""
import os
import sys
from pathlib import Path

# config.py 위치: {project_root}/app/api/app/core/config.py
# parents[4]    = {project_root}
_PROJECT_ROOT = Path(__file__).resolve().parents[4]

# 프로젝트 루트를 sys.path 에 추가 (app.ingest 등 상위 패키지 접근용)
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# .env 자동 로딩 — app/api/app/.env 우선, 없으면 프로젝트 루트 .env
try:
    from dotenv import load_dotenv
    _env_file = _PROJECT_ROOT / "app" / "api" / "app" / ".env"
    if not _env_file.exists():
        _env_file = _PROJECT_ROOT / ".env"
    if _env_file.exists():
        load_dotenv(_env_file, override=False)
except ImportError:
    pass


class Settings:
    # ── 프로젝트 루트 경로 ──────────────────────────────────────────────────────
    _project_root: Path = _PROJECT_ROOT

    # ── 데이터 경로 ────────────────────────────────────────────────────────────
    # 기본값을 config.py 위치 기준 절대경로로 고정하여 CWD 에 무관하게 동작.
    data_dir: str = os.getenv("DATA_DIR", str(_PROJECT_ROOT / "data" / "processed"))

    # 업로드된 HTML 파일 임시 저장 경로
    upload_temp_dir: str = os.getenv("UPLOAD_TEMP_DIR", str(_PROJECT_ROOT / "data" / "uploads_temp"))

    # pipeline.py 출력 디렉토리 (data/processed/)
    processed_dir: str = os.getenv("PROCESSED_DIR", str(_PROJECT_ROOT / "data" / "processed"))

    # ── 동작 모드 ─────────────────────────────────────────────────────────────
    # True  → MockRetriever + MockGenerator (Chroma 불필요)
    # False → ChromaRetriever + ClaudeGenerator (기본값)
    mock_mode: bool = os.getenv("MOCK_MODE", "false").lower() == "true"

    # ── ChromaDB — PersistentClient 경로 ──────────────────────────────────────
    # 절대경로로 고정하여 실행 디렉토리(CWD)와 무관하게 동작.
    # Docker: CHROMA_PERSIST_PATH=/workspace/chroma_store 를 주입.
    chroma_persist_path: str = os.getenv(
        "CHROMA_PERSIST_PATH", str(_PROJECT_ROOT / "chroma_store")
    )

    # enriched JSON 위치 — POST /vector/index (비상 재적재 용도) 에서만 사용
    chroma_enriched_data_dir: str = os.getenv(
        "CHROMA_ENRICHED_DATA_DIR", str(_PROJECT_ROOT / "chroma" / "data_process" / "enriched_data")
    )

    # ── ChromaDB — HTTP 클라이언트 (미래 확장, 현재 미사용) ─────────────────
    chroma_host: str = os.getenv("CHROMA_HOST", "localhost")
    chroma_port: int = int(os.getenv("CHROMA_PORT", "8000"))

    # ── Ollama 연결 ──────────────────────────────────────────────────────────
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3")

    # ── Anthropic Claude API ─────────────────────────────────────────────────
    # ANTHROPIC_API_KEY 설정 시 ClaudeGenerator 활성화, 미설정 시 MockGenerator 폴백.
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

    # ── 사용자/채팅 이력용 SQLite ─────────────────────────────────────────────
    db_url: str = os.getenv("APP_DB_URL", "sqlite:///data/app.db")

    # ── JWT & Google OAuth ────────────────────────────────────────────────────
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "my_super_secret_jwt_key")
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "financial-nlp-api"
    jwt_audience: str = "financial-nlp-frontend"
    jwt_expiry_seconds: int = 3600
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "YOUR_GOOGLE_CLIENT_ID_HERE.apps.googleusercontent.com")

    def get_all_processed_files(self, year: int = None) -> list[Path]:
        pattern = f"*_audit_report_{year if year else '*'}_structured.json"
        files = list(Path(self.data_dir).glob(pattern))
        return sorted(files, key=lambda p: p.name)


# 모듈 수준 싱글턴
settings = Settings()
