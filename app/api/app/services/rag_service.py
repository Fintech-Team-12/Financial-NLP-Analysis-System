from __future__ import annotations

from typing import Any

try:
    from chroma.search_pipeline import run_search
except ImportError:
    import sys
    from pathlib import Path

    ROOT_DIR = Path(__file__).resolve().parents[4]
    if str(ROOT_DIR) not in sys.path:
        sys.path.append(str(ROOT_DIR))

    from chroma.search_pipeline import run_search

try:
    from app.services.llm_service import generate_answer
except ImportError:
    from app.api.app.services.llm_service import generate_answer
    
def run_rag(
    question: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    chat_history: list[dict] | None = None,
) -> dict[str, Any]:
    """
    질문을 받아
    1) retrieval/search pipeline 수행
    2) retrieval 결과를 바탕으로 answer 생성 (chat_history 참조 포함)
    3) 최종 응답 dict 반환

    provider: 'ollama' | 'claude' | 'mock' | None (None이면 환경변수 기준 자동 선택)
    model: 해당 provider에서 사용할 모델명 (None이면 환경변수 기본값)
    """
    # 멀티턴 대응 (Query Augmentation Heuristic)
    # 현재 질문에 핵심 키워드가 없고 짧은 경우, 대화 문맥(이전 질문)을 검색어에 합칩니다.
    search_query = question
    if chat_history and len(question) < 40:
        financial_keywords = ["20", "재무", "손익", "주석", "자본", "현금", "감사", "삼성", "엘지", "LG", "카카오", "네이버"]
        if not any(k in question for k in financial_keywords):
            last_user_msg = next((m["content"] for m in reversed(chat_history) if m["role"] == "user"), None)
            if last_user_msg:
                search_query = f"{last_user_msg} {question}"

    search_output = run_search(search_query)
    results = search_output.get("results", [])

    llm_output = generate_answer(question, results, provider=provider, model=model, chat_history=chat_history)

    return {
        "question": question,
        "search_plan": search_output.get("search_plan", {}),
        "results": results,
        "llm_output": llm_output,
    }


if __name__ == "__main__":
    sample_question = "재무제표에 대한 경영진의 책임이 뭐야?"
    output = run_rag(sample_question)

    print("=" * 100)
    print("RAG Service Demo")
    print("=" * 100)
    print("question:", output["question"])

    print("\n[search_plan]")
    for k, v in output["search_plan"].items():
        print(f"{k}: {v}")

    print("\n[results]")
    for i, item in enumerate(output["results"], start=1):
        print("-" * 80)
        print(f"[{i}] id={item.get('id')}")
        print("collection_type:", item.get("collection_type"))
        print("retrieval_source:", item.get("retrieval_source"))
        print("pipeline_score:", item.get("pipeline_score"))
        print("section_title:", (item.get("metadata", {}) or {}).get("section_title"))

    print("\n[llm_output]")
    for k, v in output["llm_output"].items():
        print(f"{k}: {v}")