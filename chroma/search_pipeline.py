from __future__ import annotations

from typing import Any

try:
    # python chroma/search_pipeline.py 로 직접 실행할 때
    from query_parser import parse_query
    from retriever import retrieve
except ImportError:
    # 다른 모듈에서 import 할 때
    from chroma.query_parser import parse_query
    from chroma.retriever import retrieve


KNOWN_TOP_SECTIONS = [
    "감사보고서",
    "재무상태표",
    "손익계산서",
    "포괄손익계산서",
    "자본변동표",
    "현금흐름표",
    "주석",
]

KNOWN_SECTION_TITLES = [
    "감사의견",
    "재무제표에 대한 경영진의 책임",
    "재무제표에 대한 경영진과 지배기구의 책임",
    "감사인의 책임",
    "현금및현금성자산",
    "유형자산",
    "법인세비용",
    "재무상태표",
    "손익계산서",
    "포괄손익계산서",
    "자본변동표",
    "현금흐름표",
]


def extract_structured_hints(raw_query: str, clean_query: str) -> dict[str, Any]:
    section_title_hint = None
    top_section_hint = None

    for title in sorted(KNOWN_SECTION_TITLES, key=len, reverse=True):
        if title in raw_query or title == clean_query:
            section_title_hint = title
            break

    for top in sorted(KNOWN_TOP_SECTIONS, key=len, reverse=True):
        if top == clean_query or top in raw_query:
            top_section_hint = top
            break

    return {
        "section_title_hint": section_title_hint,
        "top_section_hint": top_section_hint,
    }


def build_metadata_filter(parsed: dict[str, Any]) -> dict[str, Any] | None:
    filters: dict[str, Any] = {}

    if parsed.get("year") is not None:
        filters["year"] = parsed["year"]

    return filters if filters else None


def infer_preferred_content_type(parsed: dict[str, Any]) -> str:
    if parsed.get("want_table") and not parsed.get("want_text"):
        return "table"
    if parsed.get("want_text") and not parsed.get("want_table"):
        return "text"
    return "mixed"


def build_search_plan(user_query: str) -> dict[str, Any]:
    parsed = parse_query(user_query)
    metadata_filter = build_metadata_filter(parsed)
    preferred_content_type = infer_preferred_content_type(parsed)
    hints = extract_structured_hints(parsed["raw_query"], parsed["clean_query"])

    return {
        "raw_query": parsed["raw_query"],
        "clean_query": parsed["clean_query"],
        "intent": parsed["intent"],
        "preferred_content_type": preferred_content_type,
        "metadata_filter": metadata_filter,
        "section_title_hint": hints["section_title_hint"],
        "top_section_hint": hints["top_section_hint"],
        "general_k": 12,
        "hint_k": 8,
        "top_k": 5,
        "use_reranker": False,
    }


def merge_where(
    base_where: dict[str, Any] | None,
    extra_where: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not base_where and not extra_where:
        return None

    if base_where and not extra_where:
        return base_where

    if extra_where and not base_where:
        return extra_where

    # 둘 다 있으면 Chroma where 문법에 맞게 $and 사용
    return {
        "$and": [
            base_where,
            extra_where,
        ]
    }

def dedupe_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}

    for item in results:
        item_id = item["id"]

        if item_id not in deduped:
            deduped[item_id] = item
            continue

        prev = deduped[item_id]
        prev_dist = prev.get("distance")
        new_dist = item.get("distance")

        if prev_dist is None:
            deduped[item_id] = item
        elif new_dist is not None and new_dist < prev_dist:
            deduped[item_id] = item

    return list(deduped.values())


def score_result(item: dict[str, Any], search_plan: dict[str, Any]) -> float:
    metadata = item.get("metadata", {}) or {}
    document = item.get("document", "") or ""
    distance = item.get("distance")

    score = -float(distance) if distance is not None else -9999.0

    clean_query = search_plan["clean_query"]
    preferred_content_type = search_plan["preferred_content_type"]
    section_title_hint = search_plan.get("section_title_hint")
    top_section_hint = search_plan.get("top_section_hint")

    section_title = str(metadata.get("section_title", "") or "")
    top_section = str(metadata.get("top_section", "") or "")
    section_path = str(metadata.get("section_path", "") or "")
    content_type = str(metadata.get("content_type", "") or "")

    # preferred content type 보정
    if preferred_content_type in {"text", "table"} and content_type == preferred_content_type:
        score += 0.25

    # hint 검색에서 온 결과 보정
    retrieval_source = item.get("retrieval_source")
    if retrieval_source == "section_title_hint":
        score += 0.9
    elif retrieval_source == "top_section_hint":
        score += 0.7

    # section_title exact match / contains
    if section_title_hint and section_title == section_title_hint:
        score += 1.2
    elif clean_query and clean_query in section_title:
        score += 0.7

    # top_section exact match / contains
    if top_section_hint and top_section == top_section_hint:
        score += 1.0
    elif clean_query and clean_query in top_section:
        score += 0.45

    # section_path / document 포함 보정
    if clean_query and clean_query in section_path:
        score += 0.35

    if clean_query and clean_query in document:
        score += 0.35

    return score


def rerank_results(results: list[dict[str, Any]], search_plan: dict[str, Any]) -> list[dict[str, Any]]:
    rescored = []

    for item in results:
        new_item = dict(item)
        new_item["pipeline_score"] = score_result(item, search_plan)
        rescored.append(new_item)

    rescored.sort(key=lambda x: x["pipeline_score"], reverse=True)
    return rescored


def retrieve_general(search_plan: dict[str, Any]) -> list[dict[str, Any]]:
    results = retrieve(
        query=search_plan["clean_query"],
        preferred_content_type=search_plan["preferred_content_type"],
        top_k=search_plan["general_k"],
        where=search_plan["metadata_filter"],
    )

    for item in results:
        item["retrieval_source"] = "general"

    return results


def retrieve_by_section_title_hint(search_plan: dict[str, Any]) -> list[dict[str, Any]]:
    hint = search_plan.get("section_title_hint")
    if not hint:
        return []

    where = merge_where(
        search_plan["metadata_filter"],
        {"section_title": hint},
    )

    results = retrieve(
        query=hint,
        preferred_content_type=search_plan["preferred_content_type"],
        top_k=search_plan["hint_k"],
        where=where,
    )

    for item in results:
        item["retrieval_source"] = "section_title_hint"

    return results


def retrieve_by_top_section_hint(search_plan: dict[str, Any]) -> list[dict[str, Any]]:
    hint = search_plan.get("top_section_hint")
    if not hint:
        return []

    where = merge_where(
        search_plan["metadata_filter"],
        {"top_section": hint},
    )

    results = retrieve(
        query=hint,
        preferred_content_type=search_plan["preferred_content_type"],
        top_k=search_plan["hint_k"],
        where=where,
    )

    for item in results:
        item["retrieval_source"] = "top_section_hint"

    return results


def run_search(user_query: str) -> dict[str, Any]:
    search_plan = build_search_plan(user_query)

    general_results = retrieve_general(search_plan)
    section_title_results = retrieve_by_section_title_hint(search_plan)
    top_section_results = retrieve_by_top_section_hint(search_plan)

    merged_results = dedupe_results(
        general_results + section_title_results + top_section_results
    )

    reranked_results = rerank_results(merged_results, search_plan)
    final_results = reranked_results[: search_plan["top_k"]]

    return {
        "question": user_query,
        "search_plan": search_plan,
        "results": final_results,
    }


if __name__ == "__main__":
    sample_queries = [
        "2014년 현금및현금성자산 알려줘",
        "유형자산 표 보여줘",
        "재무제표에 대한 경영진의 책임이 뭐야?",
        "법인세비용 수치 알려줘",
        "포괄손익계산서 관련 내용 설명해줘",
    ]

    for q in sample_queries:
        print("=" * 100)
        output = run_search(q)

        print("[SEARCH PLAN]")
        for k, v in output["search_plan"].items():
            print(f"{k}: {v}")

        print("\n[TOP RESULTS]")
        for i, item in enumerate(output["results"], start=1):
            print("-" * 100)
            print(f"[{i}] collection_type={item['collection_type']}")
            print("retrieval_source:", item.get("retrieval_source"))
            print("id:", item["id"])
            print("distance:", item["distance"])
            print("pipeline_score:", item.get("pipeline_score"))
            print("metadata:", item["metadata"])
            print("document:", item["document"][:300], "...")