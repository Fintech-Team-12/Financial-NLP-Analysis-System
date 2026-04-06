"""
애플리케이션 설정.
환경변수로 주입 — Docker / 로컬 / 테스트 환경 모두 동일 코드로 동작.

.env 파일 로딩:
  app/api/.env 또는 프로젝트 루트 .env 중 존재하는 파일을 자동으로 읽는다.
  이미 설정된 환경변수는 .env 로 덮어쓰지 않는다 (override=False).
"""
import os
from pathlib import Path

# config.py 위치: {project_root}/app/api/app/core/config.py
# parents[4]    = {project_root}
_PROJECT_ROOT = Path(__file__).resolve().parents[4]

# .env 자동 로딩 — app/api/.env 우선, 없으면 프로젝트 루트 .env
try:
    from dotenv import load_dotenv
    _env_file = _PROJECT_ROOT / "app" / "api" / ".env"
    if not _env_file.exists():
        _env_file = _PROJECT_ROOT / ".env"
    if _env_file.exists():
        load_dotenv(_env_file, override=False)
except ImportError:
    pass


class Settings:
    # ── 프로젝트 루트 경로 (config.py 위치로부터 역산) ─────────────────────────
    _project_root: Path = _PROJECT_ROOT

    # ── 데이터 경로 ────────────────────────────────────────────────────────────
    data_dir: str = os.getenv("DATA_DIR", str(_PROJECT_ROOT / "data" / "processed"))

    # 업로드된 HTML 파일 임시 저장 경로
    upload_temp_dir: str = os.getenv("UPLOAD_TEMP_DIR", str(_project_root / "data" / "uploads_temp"))

    # pipeline.py 출력 디렉토리 (data/processed/)
    processed_dir: str = os.getenv("PROCESSED_DIR", str(_project_root / "data" / "processed"))

    # ── 동작 모드 ─────────────────────────────────────────────────────────────
    # True  → MockRetriever + MockGenerator (Chroma/Ollama 불필요)
    # False → ChromaRetriever + OllamaGenerator (담당자 구현 후 교체)
    mock_mode: bool = os.getenv("MOCK_MODE", "true").lower() == "true"

    # ── ChromaDB — PersistentClient 경로 (현재 사용) ──────────────────────────
    # 팀원 chroma/load_*.py 가 프로젝트 루트/chroma_store 에 적재.
    # 절대경로로 고정하여 실행 디렉토리(CWD)와 무관하게 동작.
    # Docker: CHROMA_PERSIST_PATH=/workspace/chroma_store 를 주입.
    chroma_persist_path: str = os.getenv(
        "CHROMA_PERSIST_PATH", str(_PROJECT_ROOT / "chroma_store")
    )

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
    jwt_issuer: str = "financial-nlp-api"          # iss 클레임
    jwt_audience: str = "financial-nlp-frontend"    # aud 클레임
    jwt_expiry_seconds: int = 3600                  # 1시간 (기존 7일에서 단축)
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "YOUR_GOOGLE_CLIENT_ID_HERE.apps.googleusercontent.com")

    def get_all_processed_files(self, year: int = None) -> list[Path]:
        """
        processed 디렉토리에서 감사보고서 JSON 파일들을 찾아 리스트로 반환합니다.
        가장 최근 파일이 우선순위를 가질 수 있게 파일명 순으로 정렬합니다.

        Args:
            year: 특정 연도만 찾을 경우 연도(int), 전체라면 None

        Returns:
            list[Path]: 검색된 JSON 파일 경로 리스트
        """
        pattern = f"*_audit_report_{year if year else '*'}_structured.json"
        files = list(Path(self.data_dir).glob(pattern))
        return sorted(files, key=lambda p: p.name)


# 모듈 수준 싱글턴 — 테스트에서 settings.data_dir = "..." 으로 직접 덮어쓰기 가능
settings = Settings()
