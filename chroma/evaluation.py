from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

try:
    # python chroma/evaluation.py 로 직접 실행할 때
    from search_pipeline import run_search
except ImportError:
    # 다른 모듈에서 import 할 때
    from chroma.search_pipeline import run_search


TEST_CASES = [
    {
        "query": "2014년 현금및현금성자산 알려줘",
        "expected_keyword": "현금및현금성자산",
    },
    {
        "query": "유형자산 표 보여줘",
        "expected_keyword": "유형자산",
    },
    {
        "query": "재무제표에 대한 경영진의 책임이 뭐야?",
        "expected_keyword": "재무제표에 대한 경영진의 책임",
    },
    {
        "query": "법인세비용 수치 알려줘",
        "expected_keyword": "법인세비용",
    },
    {
        "query": "포괄손익계산서 관련 내용 설명해줘",
        "expected_keyword": "포괄손익계산서",
    },
]

OUTPUT_DIR = Path("chroma/results")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_CSV = OUTPUT_DIR / "retrieval_eval_baseline.csv"


def contains_expected(item: dict[str, Any], expected_keyword: str) -> bool:
    metadata = item.get("metadata", {}) or {}
    document = item.get("document", "") or ""

    section_title = str(metadata.get("section_title", "") or "")
    top_section = str(metadata.get("top_section", "") or "")
    section_path = str(metadata.get("section_path", "") or "")

    return (
        expected_keyword in section_title
        or expected_keyword in top_section
        or expected_keyword in section_path
        or expected_keyword in document
    )


def evaluate_case(query: str, expected_keyword: str) -> dict[str, Any]:
    output = run_search(query)
    results = output.get("results", [])

    top1_hit = False
    top3_hit = False

    top1_id = ""
    top1_section_title = ""
    top1_collection_type = ""
    top1_retrieval_source = ""
    top1_score = ""

    if results:
        first = results[0]
        top1_hit = contains_expected(first, expected_keyword)
        top1_id = first.get("id", "")
        top1_collection_type = first.get("collection_type", "")
        top1_retrieval_source = first.get("retrieval_source", "")
        top1_score = first.get("pipeline_score", "")
        top1_section_title = str((first.get("metadata", {}) or {}).get("section_title", ""))

    top3_candidates = results[:3]
    top3_hit = any(contains_expected(item, expected_keyword) for item in top3_candidates)

    return {
        "query": query,
        "expected_keyword": expected_keyword,
        "clean_query": output["search_plan"]["clean_query"],
        "intent": output["search_plan"]["intent"],
        "preferred_content_type": output["search_plan"]["preferred_content_type"],
        "section_title_hint": output["search_plan"].get("section_title_hint"),
        "top_section_hint": output["search_plan"].get("top_section_hint"),
        "top1_hit": top1_hit,
        "top3_hit": top3_hit,
        "top1_id": top1_id,
        "top1_section_title": top1_section_title,
        "top1_collection_type": top1_collection_type,
        "top1_retrieval_source": top1_retrieval_source,
        "top1_pipeline_score": top1_score,
    }


def save_csv(rows: list[dict[str, Any]], output_csv: Path) -> None:
    fieldnames = [
        "query",
        "expected_keyword",
        "clean_query",
        "intent",
        "preferred_content_type",
        "section_title_hint",
        "top_section_hint",
        "top1_hit",
        "top3_hit",
        "top1_id",
        "top1_section_title",
        "top1_collection_type",
        "top1_retrieval_source",
        "top1_pipeline_score",
    ]

    with open(output_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows: list[dict[str, Any]]) -> None:
    total = len(rows)
    top1_count = sum(1 for row in rows if row["top1_hit"])
    top3_count = sum(1 for row in rows if row["top3_hit"])

    print("=" * 80)
    print("Evaluation Summary")
    print("=" * 80)
    print(f"Total queries : {total}")
    print(f"Top1 hit      : {top1_count}/{total} = {top1_count / total:.2%}")
    print(f"Top3 hit      : {top3_count}/{total} = {top3_count / total:.2%}")
    print(f"Saved to      : {OUTPUT_CSV}")


def main() -> None:
    rows: list[dict[str, Any]] = []

    for case in TEST_CASES:
        row = evaluate_case(
            query=case["query"],
            expected_keyword=case["expected_keyword"],
        )
        rows.append(row)

    save_csv(rows, OUTPUT_CSV)
    print_summary(rows)


if __name__ == "__main__":
    main()