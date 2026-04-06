"""
사용자/OAuth/채팅 이력 ORM 모델.

RAG 문서 데이터(ChromaDB, processed JSON)와 완전히 분리된
relational DB 계층이다.

테이블 구조:
    users            사용자 기본 정보 (Google 계정 기준)
    oauth_accounts   OAuth 공급자별 계정 연결 (확장성 위해 분리)
    chat_sessions    대화 세션 묶음
    chat_messages    세션 내 개별 메시지
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _now() -> datetime:
    """UTC 현재 시각 반환 (timezone-aware)."""
    return datetime.now(timezone.utc)


# ── 1. users ──────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile_image: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    # relationships
    oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(
        "OAuthAccount", back_populates="user", cascade="all, delete-orphan"
    )
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        "ChatSession", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"


# ── 2. oauth_accounts ─────────────────────────────────────────────────────────

class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"
    __table_args__ = (
        # 같은 공급자에서 같은 계정이 중복 연결되지 않도록
        UniqueConstraint("provider", "provider_user_id", name="uq_provider_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)          # "google"
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False) # Google sub
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    # relationship
    user: Mapped["User"] = relationship("User", back_populates="oauth_accounts")

    def __repr__(self) -> str:
        return f"<OAuthAccount provider={self.provider} user_id={self.user_id}>"


# ── 3. chat_sessions ──────────────────────────────────────────────────────────

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 제목은 첫 질문 내용을 잘라서 자동 생성하거나 프론트에서 입력
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    # relationships
    user: Mapped["User"] = relationship("User", back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    def __repr__(self) -> str:
        return f"<ChatSession id={self.id} user_id={self.user_id}>"


# ── 4. chat_messages ──────────────────────────────────────────────────────────

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # "user" = 사람이 보낸 질문, "assistant" = LLM 이 생성한 답변
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    # relationship
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")

    def __repr__(self) -> str:
        return f"<ChatMessage id={self.id} role={self.role} session_id={self.session_id}>"


# ── 5. uploaded_reports ───────────────────────────────────────────────────────

class UploadedReport(Base):
    """
    업로드된 감사보고서 HTML 파일 추적.
    파싱 결과 JSON 경로와 업로더 정보를 보존한다.
    """
    __tablename__ = "uploaded_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(100), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    structured_json_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    jobs: Mapped[list["IngestionJob"]] = relationship(
        "IngestionJob", back_populates="report", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<UploadedReport id={self.id} company={self.company} year={self.year}>"


# ── 6. ingestion_jobs ─────────────────────────────────────────────────────────

class IngestionJob(Base):
    """
    ChromaDB 색인 작업 상태 추적.
    status: pending → running → done | failed
    """
    __tablename__ = "ingestion_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("uploaded_reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    indexed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    report: Mapped["UploadedReport"] = relationship("UploadedReport", back_populates="jobs")

    def __repr__(self) -> str:
        return f"<IngestionJob id={self.id} status={self.status} report_id={self.report_id}>"
