from __future__ import annotations

import os
from typing import Any


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


def build_answer_prompt(question: str, results: list[dict[str, Any]]) -> str:
    context_block = format_contexts(results)

    return f"""
당신은 감사보고서 질의응답 보조 시스템입니다.

아래 검색 문맥만을 근거로 사용자 질문에 답변하세요.
문맥에 없는 내용을 단정해서 지어내지 마세요.
답변은 한국어로 작성하세요.
가능하면 핵심 답변을 먼저 짧게 제시하고,
이후 근거가 되는 section_title 또는 section_path를 함께 요약하세요.
표/수치 질문이라면 수치를 우선적으로 정리하세요.
문맥이 불충분하면 "검색 결과만으로는 확실히 확인되지 않습니다."라고 말하세요.

[사용자 질문]
{question}

[검색 문맥]
{context_block}

[출력 형식]
1. 답변
2. 근거 요약
3. 참고 section
""".strip()


def generate_mock_answer(question: str, results: list[dict[str, Any]]) -> dict[str, Any]:
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


def generate_answer(question: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    """
    현재는 mock 기반.
    나중에 실제 LLM API / 로컬 모델 호출로 쉽게 교체 가능.
    """
    llm_mode = os.getenv("LLM_MODE", "mock").lower()

    prompt = build_answer_prompt(question, results)

    if llm_mode == "mock":
        response = generate_mock_answer(question, results)
        response["prompt_preview"] = truncate_text(prompt, 1000)
        return response

    # 실제 LLM 연결 전 placeholder
    return {
        "answer": "LLM_MODE가 mock이 아니지만 실제 모델 호출은 아직 연결되지 않았습니다.",
        "evidence_summary": [],
        "used_context_count": min(len(results), MAX_CONTEXTS),
        "model_name": "not-connected",
        "prompt_preview": truncate_text(prompt, 1000),
    }


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