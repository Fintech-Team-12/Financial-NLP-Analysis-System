"""
답변 생성(Answering) 레이어.

GeneratorBase    : 공통 인터페이스
MockGenerator    : 검색 문서를 포맷팅해서 반환 (LLM 없이 동작, 기본/폴백)
ExternalGenerator: llm_service.generate_answer() 를 호출하는 어댑터.
                   llm_service.py 배치 + USE_EXTERNAL_LLM=true 로 활성화.
"""
import logging
from abc import ABC, abstractmethod

from app.models.document import NormalizedDocument
from app.schemas.response import Citation, ChatResponse
from app.services.router import QuestionType

_log = logging.getLogger(__name__)


class GeneratorBase(ABC):
    """답변 생성 인터페이스. LLM 담당자가 이 클래스를 상속해 구현."""

    @abstractmethod
    def generate(
        self,
        question: str,
        docs: list[NormalizedDocument],
        question_type: QuestionType,
    ) -> ChatResponse:
        ...


class MockGenerator(GeneratorBase):
    """
    LLM 없이 검색된 문서를 포맷팅해 반환.
    로컬 개발 및 CI 에서 사용. Ollama 없이도 전체 파이프라인 검증 가능.
    """

    def generate(
        self,
        question: str,
        docs: list[NormalizedDocument],
        question_type: QuestionType,
    ) -> ChatResponse:
        if not docs:
            return ChatResponse(
                answer="관련 문서를 찾을 수 없습니다.",
                citations=[],
                question_type=question_type,
                used_documents=[],
            )

        answer = (
            self._format_numeric(docs)
            if question_type == QuestionType.NUMERIC
            else self._format_text(docs)
        )

        citations = [
            Citation(
                doc_id=doc.doc_id,
                year=doc.year,
                section=doc.section,
                excerpt=doc.content[:200],
                numeric_value=doc.numeric_value,
            )
            for doc in docs
        ]

        return ChatResponse(
            answer=answer,
            citations=citations,
            question_type=question_type,
            used_documents=[doc.doc_id for doc in docs],
        )

    def _format_numeric(self, docs: list[NormalizedDocument]) -> str:
        parts: list[str] = []
        for doc in docs:
            if doc.numeric_value:
                vals = ", ".join(f"{k}: {v:,}원" for k, v in doc.numeric_value.items())
                parts.append(f"{doc.year}년 {doc.section}: {vals}")
            else:
                parts.append(doc.content[:150])
        return "\n".join(parts) if parts else "금액 정보를 찾을 수 없습니다."

    def _format_text(self, docs: list[NormalizedDocument]) -> str:
        return "\n\n---\n\n".join(doc.content[:300] for doc in docs[:3])


# ── ExternalGenerator ─────────────────────────────────────────────────────────

def _to_llm_service_format(doc: NormalizedDocument) -> dict:
    """NormalizedDocument → llm_service.generate_answer() 가 기대하는 dict 형식 변환."""
    return {
        "document": doc.content,
        "retrieval_source": "vector_search",
        "collection_type": doc.doc_type,
        "metadata": {
            "section_title": doc.section,
            "section_path": doc.parent_section or "",
            "year": doc.year,
            "content_type": doc.doc_type,
            "report_type": doc.doc_type,
        },
    }


class ExternalGenerator(GeneratorBase):
    """
    llm_service.generate_answer() 를 호출하는 어댑터.

    활성화: USE_EXTERNAL_LLM=true 환경변수 설정
    llm_service.py 가 없으면 MockGenerator 로 자동 폴백.
    """

    def __init__(self) -> None:
        self._fallback = MockGenerator()
        self._llm_generate = self._load_llm_service()

    def _load_llm_service(self):
        try:
            from app.services.llm_service import generate_answer  # type: ignore[import]
            return generate_answer
        except ImportError:
            _log.warning("llm_service.py 를 찾을 수 없습니다. MockGenerator 로 폴백합니다.")
            return None

    def generate(
        self,
        question: str,
        docs: list[NormalizedDocument],
        question_type: QuestionType,
    ) -> ChatResponse:
        if self._llm_generate is None:
            return self._fallback.generate(question, docs, question_type)

        if not docs:
            return ChatResponse(
                answer="관련 문서를 찾을 수 없습니다.",
                citations=[],
                question_type=question_type,
                used_documents=[],
            )

        raw_results = [_to_llm_service_format(doc) for doc in docs]

        try:
            llm_output = self._llm_generate(question, raw_results)
            answer: str = llm_output.get("answer", "")
            if not answer:
                raise ValueError("llm_service 에서 빈 answer 반환")
        except Exception as exc:
            _log.warning("ExternalGenerator 실패 (%s), MockGenerator 로 폴백", exc)
            return self._fallback.generate(question, docs, question_type)

        citations = [
            Citation(
                doc_id=doc.doc_id,
                year=doc.year,
                section=doc.section,
                excerpt=doc.content[:200],
                numeric_value=doc.numeric_value,
            )
            for doc in docs
        ]

        return ChatResponse(
            answer=answer,
            citations=citations,
            question_type=question_type,
            used_documents=[doc.doc_id for doc in docs],
        )


def get_generator() -> GeneratorBase:
    """
    환경변수에 따라 Generator 구현체 선택.

    우선순위:
      1. MOCK_MODE=true        → MockGenerator  (테스트/CI)
      2. USE_EXTERNAL_LLM=true → ExternalGenerator (llm_service 사용)
      3. 그 외                 → MockGenerator  (기본값)
    """
    import os
    from app.core.config import settings

    if settings.mock_mode:
        return MockGenerator()

    if os.getenv("USE_EXTERNAL_LLM", "false").lower() == "true":
        return ExternalGenerator()

    return MockGenerator()
