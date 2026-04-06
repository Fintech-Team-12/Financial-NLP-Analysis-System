"""POST /chat — 감사보고서 기반 질의응답.

파이프라인: run_rag() (chroma.search_pipeline + llm_service) 단일 경로.
DB 저장 / JWT 인증 / ChatResponse 스키마는 그대로 유지.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.schemas.request import ChatRequest
from app.schemas.response import Citation, ChatResponse
from app.services import chat_history_service
from app.services.rag_service import run_rag
from app.services.router import classify_question
from app.core.auth_deps import get_current_user, get_db
from app.db.models import User

_log = logging.getLogger(__name__)
router = APIRouter()


def _rag_output_to_response(
    rag_out: dict,
    question_type_str: str,
    chat_id: int | None,
) -> ChatResponse:
    """run_rag() 반환값 → ChatResponse 변환."""
    llm = rag_out.get("llm_output", {})
    results = rag_out.get("results", [])

    answer = llm.get("answer", "")
    if not answer:
        answer = "답변을 생성할 수 없습니다."

    citations = [
        Citation(
            doc_id=r.get("id", ""),
            year=int((r.get("metadata") or {}).get("year", 0)),
            section=(r.get("metadata") or {}).get("section_title", ""),
            excerpt=(r.get("document") or "")[:200],
        )
        for r in results[:5]
    ]

    return ChatResponse(
        answer=answer,
        citations=citations,
        question_type=question_type_str,
        used_documents=[r.get("id", "") for r in results],
        chat_id=chat_id,
    )


@router.post("/ask", response_model=ChatResponse, include_in_schema=False)
def ask_legacy(
    req: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    """하위호환 alias — /chat 과 동일."""
    return ask(req, db, current_user)


@router.post("/chat", response_model=ChatResponse)
def ask(
    req: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> ChatResponse:
    """
    rag_service.run_rag() → llm_service.generate_answer() 단일 경로.
    세션 생성 / 소유권 검증 / 메시지 DB 저장 / JWT 인증은 그대로 유지.
    """
    # ── 1. 채팅 세션 확보 및 질문 저장 ───────────────────────────────────────
    chat_id = req.chat_id
    if not chat_id:
        title = req.question[:30] + "..." if len(req.question) > 30 else req.question
        new_session = chat_history_service.create_chat_session(db, current_user.id, title=title)
        chat_id = new_session.id

    session_obj = chat_history_service.get_session_by_id(db, chat_id)
    if not session_obj or session_obj.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="해당 채팅방에 접근 권한이 없습니다.")

    past_messages = chat_history_service.list_session_messages(db, chat_id)
    chat_history = [{"role": m.role, "content": m.content} for m in past_messages]

    chat_history_service.add_message(db, chat_id, "user", req.question)

    # ── 2. question_type 분류 (응답 메타데이터용) ─────────────────────────────
    routing = classify_question(req.question, default_year=req.year)

    # ── 3. RAG 파이프라인 실행 ────────────────────────────────────────────────
    try:
        rag_out = run_rag(req.question, chat_history=chat_history)
    except Exception as exc:
        _log.error("run_rag() 실패: %s", exc)
        error_answer = "검색 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
        chat_history_service.add_message(db, chat_id, "assistant", error_answer)
        db.commit()
        return ChatResponse(
            answer=error_answer,
            citations=[],
            question_type=routing.question_type.value,
            used_documents=[],
            chat_id=chat_id,
        )

    # ── 4. 응답 변환 및 DB 저장 ───────────────────────────────────────────────
    response = _rag_output_to_response(rag_out, routing.question_type.value, chat_id)
    chat_history_service.add_message(db, chat_id, "assistant", response.answer)
    db.commit()

    return response
