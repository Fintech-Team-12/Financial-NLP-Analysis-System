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
    data_dir: str = os.getenv("DATA_DIR", "data/processed")

    # ── 동작 모드 ─────────────────────────────────────────────────────────────
    # True  → MockRetriever + MockGenerator (Chroma/Ollama 불필요)
    # False → ChromaRetriever + OllamaGenerator (담당자 구현 후 교체)
    mock_mode: bool = os.getenv("MOCK_MODE", "true").lower() == "true"

    # ── ChromaDB 연결 (mock_mode=False 일 때 사용) ────────────────────────────
    # docker-compose.yml: chroma 서비스가 CHROMA_HOST=chroma, CHROMA_PORT=8000
    chroma_host: str = os.getenv("CHROMA_HOST", "localhost")
    chroma_port: int = int(os.getenv("CHROMA_PORT", "8000"))
    chroma_collection: str = os.getenv("CHROMA_COLLECTION", "audit_reports")

    # ── Ollama 연결 (mock_mode=False 일 때 사용) ─────────────────────────────
    # docker-compose.yml: OLLAMA_BASE_URL=http://host.docker.internal:11434
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3")

    # ── 사용자/채팅 이력용 SQLite (RAG 벡터 데이터와 분리) ────────────────────
    # Docker: /workspace/data/app.db (data 볼륨에 마운트)
    # 로컬:   data/app.db
    # 테스트: conftest 에서 "sqlite:///:memory:" 로 덮어씀
    db_url: str = os.getenv("APP_DB_URL", "sqlite:///data/app.db")

    def get_data_path(self, year: int) -> Path:
        """연도별 processed JSON 파일 경로 반환."""
        return Path(self.data_dir) / f"audit_report_{year}_structured.json"


# 모듈 수준 싱글턴 — 테스트에서 settings.data_dir = "..." 으로 직접 덮어쓰기 가능
settings = Settings()
