# 검색 계획 생성기 만드는 것

from typing import Any
from query_parser import parse_query


def build_metadata_filter(parsed: dict[str, Any]) -> dict[str, Any] | None:
    filters = {}

    if parsed.get("year") is not None:
        filters["year"] = parsed["year"]

    # 현재 metadata에 content_type이 들어가 있으므로
    # text/table 의도에 따라 우선 필터를 만들 수 있음
    if parsed.get("want_table") and not parsed.get("want_text"):
        filters["content_type"] = "table"
    elif parsed.get("want_text") and not parsed.get("want_table"):
        filters["content_type"] = "text"

    return filters if filters else None


def build_search_plan(user_query: str) -> dict[str, Any]:
    parsed = parse_query(user_query)
    metadata_filter = build_metadata_filter(parsed)

    search_plan = {
        "raw_query": parsed["raw_query"],
        "clean_query": parsed["clean_query"],
        "intent": parsed["intent"],
        "preferred_content_type": (
            "table" if parsed["want_table"] and not parsed["want_text"]
            else "text" if parsed["want_text"] and not parsed["want_table"]
            else "mixed"
        ),
        "metadata_filter": metadata_filter,
        "top_k": 5,
        "use_reranker": False,   # 나중에 True로 바꿔 확장 가능
    }

    return search_plan


if __name__ == "__main__":
    sample_queries = [
        "2014년 현금및현금성자산 알려줘",
        "유형자산 표 보여줘",
        "재무제표에 대한 경영진의 책임이 뭐야?",
        "법인세비용 수치 알려줘",
        "포괄손익계산서 관련 내용 설명해줘",
    ]

    for q in sample_queries:
        print("=" * 80)
        plan = build_search_plan(q)
        for k, v in plan.items():
            print(f"{k}: {v}")