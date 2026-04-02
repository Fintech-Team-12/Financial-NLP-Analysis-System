"""
답변 생성(Answering) 레이어.

GeneratorBase: 공통 인터페이스
MockGenerator: 검색 문서를 포맷팅해서 반환 (LLM 없이 동작)

교체 포인트:
  OllamaGenerator(GeneratorBase) 를 구현하고
  get_generator() 에서 반환하면 됨.
  프롬프트 엔지니어링 / 멀티턴 히스토리도 이 레이어에서 관리.
"""
from abc import ABC, abstractmethod

from app.models.document import NormalizedDocument
from app.schemas.response import Citation, QAResponse
from app.services.router import QuestionType


class GeneratorBase(ABC):
    """답변 생성 인터페이스. LLM 담당자가 이 클래스를 상속해 구현."""

    @abstractmethod
    def generate(
        self,
        question: str,
        docs: list[NormalizedDocument],
        question_type: QuestionType,
    ) -> QAResponse:
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
    ) -> QAResponse:
        if not docs:
            return QAResponse(
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

        return QAResponse(
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


# ── OllamaGenerator 구현 템플릿 (LLM 담당자 작업 공간) ──────────────────────
#
# class OllamaGenerator(GeneratorBase):
#     def __init__(self, base_url: str, model: str):
#         self._base_url = base_url
#         self._model = model
#
#     def generate(self, question, docs, question_type):
#         context = "\n\n".join(doc.content for doc in docs)
#         prompt = f"Context:\n{context}\n\nQuestion: {question}\nAnswer:"
#         # httpx.post(f"{self._base_url}/api/generate", json={"model": self._model, "prompt": prompt})
#         ...


def get_generator() -> GeneratorBase:
    """
    Factory: config.mock_mode 에 따라 구현체 선택.
    mock_mode=False 로 전환하면 OllamaGenerator 로 교체.
    """
    from app.core.config import settings
    if settings.mock_mode:
        return MockGenerator()
    # TODO: LLM 담당자 구현 완료 후 아래 주석 해제
    # return OllamaGenerator(settings.ollama_base_url, settings.ollama_model)
    return MockGenerator()
