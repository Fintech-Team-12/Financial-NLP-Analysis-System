"""
SQLAlchemy engine + Session factory.

사용법:
    from app.db.session import get_session

    with get_session() as session:
        user = session.get(User, 1)

- engine 은 모듈 로드 시 settings.db_url 로 한 번만 생성된다.
- 테스트에서는 conftest 가 engine 을 덮어써서 :memory: DB 를 사용한다.
"""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# SQLite 에서 외래키 제약을 활성화 (기본값이 꺼져 있음)
@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _connection_record) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _make_engine(url: str):
    """
    URL 을 받아 engine 을 생성한다.
    connect_args 는 SQLite 전용 옵션 — 다른 DB 사용 시 제거.
    """
    return create_engine(
        url,
        connect_args={"check_same_thread": False},  # FastAPI 멀티스레드 환경 대응
        echo=False,  # SQL 로그 출력 여부 (디버그 시 True 로)
    )


# 모듈 수준 engine — 테스트 conftest 에서 교체 가능
engine = _make_engine(settings.db_url)

# Session 팩토리
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    context manager 방식 세션.

    with get_session() as session:
        ...  # commit / rollback 자동 처리
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
