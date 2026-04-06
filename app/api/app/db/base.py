"""
SQLAlchemy DeclarativeBase.

모든 ORM 모델은 이 Base 를 상속한다.
별도 파일로 분리하는 이유: models.py 와 session.py 가 서로를 임포트하는
순환 참조를 방지하기 위해.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
