"""
DB 초기화 유틸리티.

로컬 실행:
    python -m app.db.init_db

또는 코드에서:
    from app.db.init_db import create_tables
    create_tables()
"""
from pathlib import Path

from app.db.base import Base
from app.db.session import engine

# models 를 반드시 import 해야 Base.metadata 에 테이블 정보가 등록됨
import app.db.models  # noqa: F401


def create_tables() -> None:
    """
    Base.metadata 에 등록된 모든 테이블을 생성한다.
    이미 존재하는 테이블은 건드리지 않는다 (checkfirst=True).
    """
    # SQLite 의 경우 DB 파일이 있는 디렉토리가 없으면 미리 만들어준다
    if engine.url.drivername == "sqlite":
        db_path = str(engine.url).replace("sqlite:///", "")
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    Base.metadata.create_all(bind=engine, checkfirst=True)
    print(f"[init_db] 테이블 생성 완료 → {engine.url}")


def drop_tables() -> None:
    """
    모든 테이블을 삭제한다.
    테스트 teardown 또는 개발 초기화 용도로만 사용.
    """
    Base.metadata.drop_all(bind=engine)
    print(f"[init_db] 테이블 삭제 완료 → {engine.url}")


if __name__ == "__main__":
    create_tables()
