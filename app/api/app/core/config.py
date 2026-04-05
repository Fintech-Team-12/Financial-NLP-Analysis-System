"""
애플리케이션 설정.
환경변수로 주입 — Docker / 로컬 / 테스트 환경 모두 동일 코드로 동작.
"""
import os
from pathlib import Path

# config.py 위치: {project_root}/app/api/app/core/config.py
# parents[4]    = {project_root}
# 실행 디렉토리(CWD)에 무관하게 프로젝트 루트 기준 절대경로를 계산한다.
_PROJECT_ROOT = Path(__file__).resolve().parents[4]


class Settings:
    # ── 데이터 경로 ────────────────────────────────────────────────────────────
    # 기본값을 config.py 위치 기준 절대경로로 고정하여 CWD 에 무관하게 동작.
    # Docker: DATA_DIR 환경변수로 /workspace/data/processed 를 주입하면 됨.
    # 테스트: conftest.py 에서 settings.data_dir 을 임시 경로로 덮어씀.
    data_dir: str = os.getenv("DATA_DIR", str(_PROJECT_ROOT / "data" / "processed"))

    # ── 동작 모드 ─────────────────────────────────────────────────────────────
    # True  → MockRetriever + MockGenerator (Chroma 불필요)
    # False → ChromaRetriever + ClaudeGenerator (기본값)
    mock_mode: bool = os.getenv("MOCK_MODE", "false").lower() == "true"

    # ── ChromaDB — PersistentClient 경로 ──────────────────────────────────────
    # 기본값을 프로젝트 루트 기준 절대경로로 고정.
    # app/api 디렉토리에서 실행해도 프로젝트 루트의 chroma_store 를 읽는다.
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

    # ── Anthropic Claude API ─────────────────────────────────────────────────
    # ANTHROPIC_API_KEY 설정 시 ClaudeGenerator 활성화.
    # 미설정 시 MockGenerator 폴백.
    # 모델 기본값: claude-sonnet-4-6 (한국어 금융 QA 최적)
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

    # ── 사용자/채팅 이력용 SQLite (RAG 벡터 데이터와 분리) ────────────────────
    # Docker: /workspace/data/app.db (data 볼륨에 마운트)
    # 로컬:   data/app.db
    # 테스트: conftest 에서 "sqlite:///:memory:" 로 덮어씀
    db_url: str = os.getenv("APP_DB_URL", "sqlite:///data/app.db")

    def get_data_path(self, year: int) -> Path:
        """연도별 processed JSON 파일 경로 반환.
        parsing 브랜치 이후 파일명 접두사가 samsung_ → 삼성전자_ 로 변경됨.
        """
        return Path(self.data_dir) / f"삼성전자_audit_report_{year}_structured.json"


# 모듈 수준 싱글턴 — 테스트에서 settings.data_dir = "..." 으로 직접 덮어쓰기 가능
settings = Settings()
