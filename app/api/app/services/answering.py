"""
답변 생성(Answering) 레이어.

GeneratorBase : 공통 인터페이스
MockGenerator : 검색 문서를 포맷팅해서 반환 (LLM 없이 동작, 테스트/폴백용)
ClaudeGenerator: Anthropic Claude API 기반 실제 답변 생성
  - ANTHROPIC_API_KEY 설정 시 자동 활성화
  - 미설정 시 MockGenerator 로 폴백

## 환경변수
  ANTHROPIC_API_KEY  Anthropic API 키 (설정 시 ClaudeGenerator 활성)
  CLAUDE_MODEL       사용할 모델 (기본: claude-sonnet-4-6)
  MOCK_MODE=true     항상 MockGenerator 사용 (테스트용)
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from app.models.document import NormalizedDocument
from app.schemas.response import Citation, ChatResponse
from app.services.router import QuestionType

_log = logging.getLogger(__name__)

# anthropic SDK는 선택적 의존성 — 미설치 시 ClaudeGenerator 비활성화
try:
    import anthropic as _anthropic_sdk
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


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


# ── MockGenerator ─────────────────────────────────────────────────────────────

class MockGenerator(GeneratorBase):
    """
    LLM 없이 검색된 문서를 포맷팅해 반환.
    로컬 개발, CI, ANTHROPIC_API_KEY 미설정 시 폴백.
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


# ── ClaudeGenerator ───────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
당신은 삼성전자 감사보고서 전문 QA 어시스턴트입니다.
사용자의 질문에 대해 아래 제공된 감사보고서 문서 컨텍스트만을 근거로 답변하세요.

규칙:
1. 컨텍스트에 없는 내용은 추측하지 마세요.
2. 금액은 정확히 인용하고 단위(원, 백만원 등)를 명시하세요.
3. 출처 섹션명을 답변 내에 자연스럽게 포함하세요.
4. 한국어로 명확하고 간결하게 답변하세요.
5. 컨텍스트가 충분하지 않으면 "제공된 문서에서 해당 정보를 찾을 수 없습니다."라고 답하세요.\
"""


def _build_context(docs: list[NormalizedDocument], question_type: QuestionType) -> str:
    """검색된 문서를 LLM 컨텍스트 텍스트로 변환."""
    parts: list[str] = []
    for i, doc in enumerate(docs, 1):
        header = f"[문서 {i}] {doc.year}년 {doc.section} ({doc.doc_type})"
        body = doc.content
        if doc.numeric_value and question_type == QuestionType.NUMERIC:
            vals = ", ".join(f"{k}: {v:,}원" for k, v in doc.numeric_value.items())
            body = f"{body}\n금액: {vals}"
        parts.append(f"{header}\n{body}")
    return "\n\n".join(parts)


class ClaudeGenerator(GeneratorBase):
    """
    Anthropic Claude API 기반 답변 생성기.

    ANTHROPIC_API_KEY 가 설정되어 있어야 한다.
    모델: config.claude_model (기본 claude-sonnet-4-6).

    API 오류 / 타임아웃 시 MockGenerator 로 폴백하여
    서비스가 완전히 중단되지 않도록 한다.
    """

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6") -> None:
        self._client = _anthropic_sdk.Anthropic(api_key=api_key)
        self._model = model
        self._fallback = MockGenerator()

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

        context = _build_context(docs, question_type)
        user_message = f"## 컨텍스트\n\n{context}\n\n## 질문\n\n{question}"

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            answer: str = response.content[0].text
        except Exception as exc:
            _log.warning(
                "ClaudeGenerator API call failed (%s), falling back to MockGenerator", exc
            )
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


# ── Factory ───────────────────────────────────────────────────────────────────

def get_generator() -> GeneratorBase:
    """
    환경에 따라 Generator 구현체 선택.

    우선순위:
      1. MOCK_MODE=true          → MockGenerator (테스트/개발용)
      2. ANTHROPIC_API_KEY 설정  → ClaudeGenerator (실제 답변 생성)
      3. 그 외                   → MockGenerator (폴백)

    ClaudeGenerator 활성화 방법:
      export ANTHROPIC_API_KEY="sk-ant-..."
      (또는 .env 파일에 추가 후 서버 재시작)
    """
    from app.core.config import settings

    print(f"[answering] mock_mode={settings.mock_mode}, _ANTHROPIC_AVAILABLE={_ANTHROPIC_AVAILABLE}, api_key={'SET' if settings.anthropic_api_key else 'EMPTY'}")

    if settings.mock_mode:
        return MockGenerator()

    if _ANTHROPIC_AVAILABLE and settings.anthropic_api_key:
        return ClaudeGenerator(settings.anthropic_api_key, settings.claude_model)

    _log.warning(
        "ANTHROPIC_API_KEY not set or anthropic package not installed. "
        "Using MockGenerator. Set ANTHROPIC_API_KEY to enable real answer generation."
    )
    return MockGenerator()
