from __future__ import annotations

import logging
import os
from typing import Any

import httpx

_log = logging.getLogger(__name__)

try:
    import anthropic as _anthropic_sdk
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


MAX_CONTEXTS = 5
MAX_DOC_CHARS = 1200


def truncate_text(text: str, max_chars: int = MAX_DOC_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + " ..."


def format_contexts(results: list[dict[str, Any]], max_contexts: int = MAX_CONTEXTS) -> str:
    if not results:
        return "검색된 문맥이 없습니다."

    lines: list[str] = []

    for i, item in enumerate(results[:max_contexts], start=1):
        metadata = item.get("metadata", {}) or {}
        document = truncate_text(item.get("document", "") or "")

        section_title = metadata.get("section_title", "")
        section_path = metadata.get("section_path", "")
        year = metadata.get("year", "")
        report_type = metadata.get("report_type", "")
        content_type = metadata.get("content_type", "")
        retrieval_source = item.get("retrieval_source", "")
        collection_type = item.get("collection_type", "")

        lines.append(
            f"[문맥 {i}]\n"
            f"- year: {year}\n"
            f"- report_type: {report_type}\n"
            f"- content_type: {content_type}\n"
            f"- collection_type: {collection_type}\n"
            f"- retrieval_source: {retrieval_source}\n"
            f"- section_title: {section_title}\n"
            f"- section_path: {section_path}\n"
            f"- document: {document}\n"
        )

    return "\n".join(lines)


def build_answer_prompt(question: str, results: list[dict[str, Any]], chat_history: list[dict] | None = None) -> str:
    context_block = format_contexts(results)

    history_text = ""
    if chat_history:
        history_text = "[이전 대화 기록]\n"
        for msg in chat_history:
            role = "사용자" if msg["role"] == "user" else "시스템"
            content = msg["content"][:300] + ("..." if len(msg["content"]) > 300 else "")
            history_text += f"- {role}: {content}\n"
        history_text += "\n"

    return f"""
당신은 감사보고서 질의응답 보조 시스템입니다.

아래 검색 문맥만을 근거로 사용자 질문에 답변하세요.
검색 문맥에 포함된 정보만 사용하고, 문맥에 없는 내용을 추측하여 덧붙이지 마세요.
답변은 한국어로 작성하세요.
가능하면 핵심 답변을 먼저 짧게 제시하고,
이후 근거가 되는 section_title 또는 section_path를 함께 요약하세요.
표나 수치에 대한 질문이라면 관련 수치를 우선적으로 정리하세요.

질문에 직접적으로 대응하는 근거가 검색 문맥에 없는 경우에만
"검색 결과만으로는 확실히 확인되지 않습니다."라고 답하세요.
단, 검색 문맥에 질문과 관련된 정보가 일부라도 있으면,
확인 가능한 범위까지만 답변하고 부족한 부분만 한정적으로 설명하세요.

{history_text}[사용자 질문]
{question}

[검색 문맥]
{context_block}

[출력 형식]
1. 답변
2. 근거 요약
3. 참고 section
""".strip()


def generate_mock_answer(question: str, results: list[dict[str, Any]], chat_history: list[dict] | None = None) -> dict[str, Any]:
    """
    실제 LLM 호출 전, 파이프라인 확인용 mock 응답
    """
    if not results:
        return {
            "answer": "검색 결과가 없어 답변을 생성할 수 없습니다.",
            "evidence_summary": [],
            "used_context_count": 0,
            "model_name": "mock-llm",
        }

    evidence_summary = []
    for item in results[:3]:
        metadata = item.get("metadata", {}) or {}
        evidence_summary.append(
            {
                "section_title": metadata.get("section_title", ""),
                "section_path": metadata.get("section_path", ""),
                "year": metadata.get("year", ""),
                "content_type": metadata.get("content_type", ""),
            }
        )

    top = results[0]
    top_meta = top.get("metadata", {}) or {}
    top_doc = top.get("document", "") or ""

    answer = (
        f"질문: {question}\n\n"
        f"현재 검색 결과 기준으로 가장 관련성이 높은 문서는 "
        f"'{top_meta.get('section_title', '')}' 섹션입니다. "
        f"아직 실제 LLM 생성은 연결하지 않았고, 현재는 retrieval 기반 mock 응답입니다.\n\n"
        f"문서 일부:\n{truncate_text(top_doc, 500)}"
    )

    return {
        "answer": answer,
        "evidence_summary": evidence_summary,
        "used_context_count": min(len(results), 3),
        "model_name": "mock-llm",
    }


def _call_claude(prompt: str, model: str | None = None) -> str:
    """
    Anthropic Claude API 호출.
    model 미지정 시 CLAUDE_MODEL 환경변수 또는 기본값 사용.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    model = model or os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
    client = _anthropic_sdk.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


def _call_ollama(prompt: str, model: str | None = None) -> str:
    """
    Ollama API 호출 (POST /api/generate).
    OLLAMA_BASE_URL / OLLAMA_MODEL 환경변수 사용.
    model 인자로 런타임 오버라이드 가능.
    """
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = model or os.getenv("OLLAMA_MODEL", "llama3")

    resp = httpx.post(
        f"{base_url}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["response"]


def _build_evidence(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "section_title": (item.get("metadata") or {}).get("section_title", ""),
            "year": (item.get("metadata") or {}).get("year", ""),
        }
        for item in results[:MAX_CONTEXTS]
    ]


def generate_answer(
    question: str,
    results: list[dict[str, Any]],
    *,
    provider: str | None = None,
    model: str | None = None,
    chat_history: list[dict] | None = None,
) -> dict[str, Any]:
    """
    retrieval 결과 → 최종 답변 생성.

    provider 우선순위:
      1. LLM_MODE=mock env       → 항상 mock (테스트/개발용)
      2. provider='mock'         → mock
      3. provider='ollama'       → Ollama (OLLAMA_BASE_URL 서버)
      4. provider='claude'       → Claude Sonnet API
      5. provider 미지정         → ANTHROPIC_API_KEY 있으면 claude, 없으면 mock

    model 인자는 해당 provider 안에서 사용할 모델명 오버라이드.
    """
    # LLM_MODE=mock → 강제 mock / 미설정 → API 키 유무로 자동 판단
    llm_mode = os.getenv("LLM_MODE", "").lower()
    api_key = os.getenv("ANTHROPIC_API_KEY", "")

    prompt = build_answer_prompt(question, results, chat_history=chat_history)

    if os.getenv("LLM_MODE", "").lower() == "mock":
        response = generate_mock_answer(question, results, chat_history=chat_history)
        response["prompt_preview"] = truncate_text(prompt, 1000)
        return response

    # ── 2. mock provider ───────────────────────────────────────────────────
    if provider == "mock":
        resp = generate_mock_answer(question, results)
        resp["prompt_preview"] = truncate_text(prompt, 1000)
        return resp

    # ── 3. Ollama ──────────────────────────────────────────────────────────
    if provider == "ollama":
        effective_model = model or os.getenv("OLLAMA_MODEL", "llama3")
        try:
            answer = _call_ollama(prompt, model=effective_model)
            return {
                "answer": answer,
                "evidence_summary": _build_evidence(results),
                "used_context_count": min(len(results), MAX_CONTEXTS),
                "model_name": f"ollama/{effective_model}",
            }
        except Exception as exc:
            _log.warning("Claude API 호출 실패 (%s), mock으로 폴백", exc)
            response = generate_mock_answer(question, results, chat_history=chat_history)
            response["model_name"] = "mock-llm (claude fallback)"
            return response

    # ── 4. Claude (명시 또는 API 키 있을 때 기본값) ────────────────────────
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if provider == "claude" or (provider is None and _ANTHROPIC_AVAILABLE and api_key):
        effective_model = model or os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
        try:
            answer = _call_claude(prompt, model=effective_model)
            return {
                "answer": answer,
                "evidence_summary": _build_evidence(results),
                "used_context_count": min(len(results), MAX_CONTEXTS),
                "model_name": f"claude/{effective_model}",
            }
        except Exception as exc:
            _log.warning("Claude 호출 실패 (%s), mock으로 폴백", exc)
            response = generate_mock_answer(question, results, chat_history=chat_history)
            response["prompt_preview"] = truncate_text(prompt, 1000)
            return response

    # ── 5. 키 없음 → mock 폴백 ────────────────────────────────────────────
    _log.warning("사용 가능한 LLM 없음 (provider=%s), mock 응답 사용", provider)
    resp = generate_mock_answer(question, results)
    resp["prompt_preview"] = truncate_text(prompt, 1000)
    return resp


if __name__ == "__main__":
    sample_results = [
        {
            "collection_type": "text",
            "retrieval_source": "section_title_hint",
            "document": "재무제표에 대한 경영진의 책임 | 경영진은 한국채택국제회계기준에 따라 이 재무제표를 작성하고 공정하게 표시할 책임이 있으며 ...",
            "metadata": {
                "section_title": "재무제표에 대한 경영진의 책임",
                "section_path": "감사보고서 > 재무제표에 대한 경영진의 책임",
                "year": 2014,
                "content_type": "text",
                "report_type": "감사보고서",
            },
        }
    ]

    output = generate_answer(
        question="재무제표에 대한 경영진의 책임이 뭐야?",
        results=sample_results,
    )

    print("=" * 80)
    print("LLM Service Demo")
    print("=" * 80)
    for k, v in output.items():
        print(f"{k}: {v}")