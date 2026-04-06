"""
pytest 공통 fixture.

sample_data_dir : 실제 데이터 포맷과 동일한 최소 JSON 을 임시 디렉토리에 생성
reset_store     : 각 테스트 전후 in-memory store 초기화
client          : DATA_DIR 을 sample_data_dir 로 덮어쓴 TestClient 반환
"""
import json
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

# ── 실제 processed JSON 과 동일한 포맷의 최소 샘플 ───────────────────────────
SAMPLE_DATA = {
    "2023": {
        "company": "삼성전자",
        "감사보고서": {
            "title": "감사보고서 본문",
            "content": "",
            "tables": [],
            "sub_sections": {
                "감사의견": {
                    "title": "감사의견",
                    "content": (
                        "우리의 의견으로는 별첨된 회사의 재무제표는 "
                        "한국채택국제회계기준에 따라 중요성의 관점에서 공정하게 표시하고 있습니다."
                    ),
                    "tables": [],
                    "sub_sections": {},
                },
                "핵심감사사항": {
                    "title": "핵심감사사항",
                    "content": "메모리 반도체 재고자산 순실현가치 평가를 핵심감사사항으로 결정하였습니다.",
                    "tables": [],
                    "sub_sections": {},
                },
            },
        },
        "재무상태표": {
            "title": "재무상태표",
            "content": "재무상태표입니다.",
            "tables": [
                {
                    "unit": "(단위: 원)",
                    "columns": ["과목명", "관련주석", "당기금액", "전기금액"],
                    "rows": [
                        ["매출채권", ["4", "5", "7"], 27363016000000, 20503223000000],
                        ["재고자산", ["8"], 29338151000000, 27990007000000],
                        ["유형자산", ["10"], 140579161000000, 123266986000000],
                    ],
                }
            ],
        },
        "주석": {
            "title": "주석",
            "content": "",
            "tables": [],
            "sub_sections": {
                "5": {
                    "title": "매출채권",
                    "content": (
                        "매출채권은 최초 인식 시 공정가치로 측정하며, "
                        "후속적으로 유효이자율법을 사용하여 상각후원가로 측정합니다."
                    ),
                    "tables": [],
                    "sub_sections": {},
                },
                "8": {
                    "title": "재고자산",
                    "content": "재고자산은 취득원가와 순실현가능가치 중 낮은 금액으로 측정합니다.",
                    "tables": [],
                    "sub_sections": {},
                },
            },
        },
    }
}


@pytest.fixture(scope="session")
def sample_data_dir(tmp_path_factory: pytest.TempPathFactory) -> str:
    """세션당 1회 생성되는 임시 JSON 파일 디렉토리."""
    data_dir: Path = tmp_path_factory.mktemp("data")
    file_path = data_dir / "삼성전자_audit_report_2023_structured.json"
    file_path.write_text(json.dumps(SAMPLE_DATA, ensure_ascii=False), encoding="utf-8")
    return str(data_dir)


@pytest.fixture
def reset_store() -> Generator[None, None, None]:
    """테스트 전후 in-memory store 초기화."""
    from app.services import indexing
    indexing._store.clear()
    indexing._indexed_files.clear()
    yield
    indexing._store.clear()
    indexing._indexed_files.clear()


@pytest.fixture
def client(sample_data_dir: str, reset_store: None) -> Generator[TestClient, None, None]:
    """
    단위 테스트용 TestClient.

    - DATA_DIR 을 임시 샘플 경로로 오버라이드
    - MOCK_MODE=True 강제: 단위 테스트는 항상 MockRetriever 사용
      (ChromaRetriever 는 실제 chroma_store 가 필요하므로 통합 테스트에서만 사용)
    - lifespan 자동 ingest 후 store 를 재초기화: "빈 상태" 가정을 보장
    """
    from app.core.config import settings
    from app.services import indexing

    original_dir = settings.data_dir
    original_mock = settings.mock_mode
    settings.data_dir = sample_data_dir
    settings.mock_mode = True  # 단위 테스트는 Chroma 불필요

    from app.main import app
    with TestClient(app) as c:
        # lifespan 자동 ingest 가 실행된 후이므로 store 를 비워 깨끗한 상태로 시작
        indexing._store.clear()
        indexing._indexed_files.clear()
        yield c

    settings.data_dir = original_dir
    settings.mock_mode = original_mock


@pytest.fixture
def auth_client(client: TestClient) -> Generator[TestClient, None, None]:
    """인증된 사용자로 요청을 보내는 TestClient."""
    from app.main import app
    from app.core.auth_deps import get_current_user
    from app.db.models import User

    # 가짜 사용자 객체 생성
    from app.db.session import get_session
    mock_user = User(
        id=1,
        email="test@example.com",
        name="테스트사용자"
    )
    
    # DB에 사용자 존재 여부 확인 및 생성 (IntegrityError 방지)
    with get_session() as db:
        db.merge(mock_user)
        db.commit()

    # get_current_user 의존성 오버라이드
    app.dependency_overrides[get_current_user] = lambda: mock_user
    
    yield client
    
    # 테스트 종료 후 오버라이드 제거
    app.dependency_overrides.clear()
