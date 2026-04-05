"""POST /qa — 감사보고서 기반 질의응답."""
from fastapi import APIRouter, HTTPException

from app.schemas.request import QARequest
from app.schemas.response import QAResponse
from app.services import indexing
from app.services.answering import get_generator
from app.services.retrieval import get_retriever
from app.services.router import QuestionType, classify_question

router = APIRouter()


@router.post("/ask", response_model=QAResponse, include_in_schema=False)
def ask_legacy(req: QARequest) -> QAResponse:
    """프론트엔드 하위호환 alias — /qa 와 동일."""
    return ask(req)


@router.post("/qa", response_model=QAResponse)
def ask(req: QARequest) -> QAResponse:
    """
    질문 유형을 분류한 뒤 각 전략으로 문서를 검색하고 답변을 생성한다.

      numeric     → structured_lookup 우선, 실패 시 retrieval fallback
      note_linked → 재무제표에서 관련주석 추출 → 주석 섹션 우선 검색
      descriptive → 감사보고서 / 주석 텍스트 검색
    """
    if not indexing.get_document_count():
        raise HTTPException(
            status_code=503,
            detail="인덱싱된 문서가 없습니다. POST /reports/ingest 를 먼저 호출하세요.",
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

    return generator.generate(req.question, docs, routing.question_type)


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
