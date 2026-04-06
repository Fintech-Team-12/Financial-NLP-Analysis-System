"""POST /chat — 감사보고서 기반 질의응답."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.schemas.request import ChatRequest
from app.schemas.response import ChatResponse
from app.services import indexing, chat_history_service
from app.services.answering import get_generator
from app.services.retrieval import get_retriever
from app.services.router import QuestionType, classify_question
from app.core.auth_deps import get_current_user, get_db
from app.db.models import User

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def ask(
    req: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> ChatResponse:
    """
    질문 유형을 분류한 뒤 각 전략으로 문서를 검색하고 답변을 생성한다.
    생성 과정 중 사용자와 AI의 메시지는 DB에 저장된다.
    """
    # 1. 채팅 세션 확보 및 질문 저장
    chat_id = req.chat_id
    if not chat_id:
        title = req.question[:30] + "..." if len(req.question) > 30 else req.question
        new_session = chat_history_service.create_chat_session(db, current_user.id, title=title)
        chat_id = new_session.id
    
    # 세션 소유권 검증
    session_obj = chat_history_service.get_session_by_id(db, chat_id)
    if not session_obj or session_obj.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="해당 채팅방에 접근 권한이 없습니다.")

    chat_history_service.add_message(db, chat_id, "user", req.question)

    # 인덱싱된 문서가 없으면 안내 메시지 반환 (503 에러 대신)
    if not indexing.get_document_count():
        fallback_answer = (
            "현재 인덱싱된 감사보고서 문서가 없습니다. "
            "data/processed/ 경로에 JSON 데이터를 추가하거나 "
            "POST /reports/ingest 를 호출하여 문서를 먼저 적재해 주세요."
        )
        chat_history_service.add_message(db, chat_id, "assistant", fallback_answer)
        db.commit()
        return ChatResponse(
            answer=fallback_answer,
            citations=[],
            question_type="descriptive",
            used_documents=[],
            chat_id=chat_id,
        )

    routing = classify_question(req.question, default_year=req.year)
    year = routing.extracted_year or req.year
    retriever = get_retriever()
    generator = get_generator()

    if routing.question_type == QuestionType.NUMERIC:
        docs = _handle_numeric(routing.extracted_item, year, req.question, req.top_k, retriever)
    elif routing.question_type == QuestionType.NOTE_LINKED:
        docs = _handle_note_linked(routing.extracted_item, year, req.question, req.top_k, retriever)
    else:
        docs = _handle_descriptive(req.question, year, req.top_k, retriever)

    # 답변 생성
    response = generator.generate(req.question, docs, routing.question_type)
    
    # 2. 답변 저장 및 response 객체 조립
    chat_history_service.add_message(db, chat_id, "assistant", response.answer)
    response.chat_id = chat_id
    db.commit()

    return response


# ── 유형별 검색 전략 ──────────────────────────────────────────────────────────

def _handle_numeric(item, year, question, top_k, retriever):
    """structured_lookup 우선 → 없으면 retrieval fallback."""
    if item and year:
        doc = indexing.structured_lookup(year, item)
        if doc:
            return [doc]
    return retriever.search(question, year=year, doc_type="financial_statement", top_k=top_k)


def _handle_note_linked(item, year, question, top_k, retriever):
    """재무제표 관련주석 번호 → 주석 섹션 우선 검색 → fallback."""
    docs = []
    if item and year:
        fs_doc = indexing.structured_lookup(year, item)
        if fs_doc and fs_doc.related_notes:
            docs = retriever.search_by_note_ids(fs_doc.related_notes, year)
    if not docs:
        docs = retriever.search(question, year=year, doc_type="note", top_k=top_k)
    return docs[:top_k]


def _handle_descriptive(question, year, top_k, retriever):
    """감사보고서 + 주석 텍스트 혼합 검색."""
    half = max(top_k // 2, 1)
    audit = retriever.search(question, year=year, doc_type="audit_report", top_k=half + 1)
    notes = retriever.search(question, year=year, doc_type="note", top_k=half)
    return (audit + notes)[:top_k]
