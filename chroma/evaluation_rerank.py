from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

try:
    from search_pipeline import run_search
    from reranker import CrossEncoderReranker
except ImportError:
    from chroma.search_pipeline import run_search
    from chroma.reranker import CrossEncoderReranker


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

OUTPUT_CSV = OUTPUT_DIR / "retrieval_eval_rerank.csv"


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


def rerank_results_for_case(
    query: str,
    candidates: list[dict[str, Any]],
    reranker: CrossEncoderReranker,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    return reranker.rerank(query=query, candidates=candidates, top_k=top_k)


def evaluate_case(
    query: str,
    expected_keyword: str,
    reranker: CrossEncoderReranker,
) -> dict[str, Any]:
    output = run_search(query)

    baseline_results = output.get("results", [])
    reranked_results = rerank_results_for_case(
        query=query,
        candidates=baseline_results,
        reranker=reranker,
        top_k=5,
    )

    baseline_top1_hit = False
    baseline_top3_hit = False
    rerank_top1_hit = False
    rerank_top3_hit = False

    baseline_top1_id = ""
    baseline_top1_title = ""
    baseline_top1_source = ""
    baseline_top1_pipeline_score = ""

    rerank_top1_id = ""
    rerank_top1_title = ""
    rerank_top1_source = ""
    rerank_top1_score = ""

    if baseline_results:
        first = baseline_results[0]
        baseline_top1_hit = contains_expected(first, expected_keyword)
        baseline_top1_id = first.get("id", "")
        baseline_top1_title = str((first.get("metadata", {}) or {}).get("section_title", ""))
        baseline_top1_source = first.get("retrieval_source", "")
        baseline_top1_pipeline_score = first.get("pipeline_score", "")

    if reranked_results:
        first = reranked_results[0]
        rerank_top1_hit = contains_expected(first, expected_keyword)
        rerank_top1_id = first.get("id", "")
        rerank_top1_title = str((first.get("metadata", {}) or {}).get("section_title", ""))
        rerank_top1_source = first.get("retrieval_source", "")
        rerank_top1_score = first.get("rerank_score", "")

    baseline_top3_hit = any(
        contains_expected(item, expected_keyword) for item in baseline_results[:3]
    )
    rerank_top3_hit = any(
        contains_expected(item, expected_keyword) for item in reranked_results[:3]
    )

    return {
        "query": query,
        "expected_keyword": expected_keyword,
        "clean_query": output["search_plan"]["clean_query"],
        "preferred_content_type": output["search_plan"]["preferred_content_type"],
        "section_title_hint": output["search_plan"].get("section_title_hint"),
        "top_section_hint": output["search_plan"].get("top_section_hint"),
        "baseline_top1_hit": baseline_top1_hit,
        "baseline_top3_hit": baseline_top3_hit,
        "baseline_top1_id": baseline_top1_id,
        "baseline_top1_section_title": baseline_top1_title,
        "baseline_top1_retrieval_source": baseline_top1_source,
        "baseline_top1_pipeline_score": baseline_top1_pipeline_score,
        "rerank_top1_hit": rerank_top1_hit,
        "rerank_top3_hit": rerank_top3_hit,
        "rerank_top1_id": rerank_top1_id,
        "rerank_top1_section_title": rerank_top1_title,
        "rerank_top1_retrieval_source": rerank_top1_source,
        "rerank_top1_score": rerank_top1_score,
    }


def save_csv(rows: list[dict[str, Any]], output_csv: Path) -> None:
    fieldnames = [
        "query",
        "expected_keyword",
        "clean_query",
        "preferred_content_type",
        "section_title_hint",
        "top_section_hint",
        "baseline_top1_hit",
        "baseline_top3_hit",
        "baseline_top1_id",
        "baseline_top1_section_title",
        "baseline_top1_retrieval_source",
        "baseline_top1_pipeline_score",
        "rerank_top1_hit",
        "rerank_top3_hit",
        "rerank_top1_id",
        "rerank_top1_section_title",
        "rerank_top1_retrieval_source",
        "rerank_top1_score",
    ]

    with open(output_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows: list[dict[str, Any]]) -> None:
    total = len(rows)

    baseline_top1 = sum(1 for row in rows if row["baseline_top1_hit"])
    baseline_top3 = sum(1 for row in rows if row["baseline_top3_hit"])
    rerank_top1 = sum(1 for row in rows if row["rerank_top1_hit"])
    rerank_top3 = sum(1 for row in rows if row["rerank_top3_hit"])

    print("=" * 80)
    print("Rerank Evaluation Summary")
    print("=" * 80)
    print(f"Total queries         : {total}")
    print(f"Baseline Top1 hit     : {baseline_top1}/{total} = {baseline_top1 / total:.2%}")
    print(f"Baseline Top3 hit     : {baseline_top3}/{total} = {baseline_top3 / total:.2%}")
    print(f"Rerank Top1 hit       : {rerank_top1}/{total} = {rerank_top1 / total:.2%}")
    print(f"Rerank Top3 hit       : {rerank_top3}/{total} = {rerank_top3 / total:.2%}")
    print(f"Saved to              : {OUTPUT_CSV}")


def main() -> None:
    reranker = CrossEncoderReranker()

    rows: list[dict[str, Any]] = []
    for case in TEST_CASES:
        row = evaluate_case(
            query=case["query"],
            expected_keyword=case["expected_keyword"],
            reranker=reranker,
        )
        rows.append(row)

    save_csv(rows, OUTPUT_CSV)
    print_summary(rows)


if __name__ == "__main__":
    main()