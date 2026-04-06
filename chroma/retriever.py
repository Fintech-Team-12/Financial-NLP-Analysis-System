from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import chromadb


BASE_DIR = Path(__file__).resolve().parent
CHROMA_PATH = BASE_DIR.parent / "chroma_store"

TEXT_COLLECTION_NAME = "audit_reports_10years_text_minilm"
TABLE_COLLECTION_NAME = "audit_reports_10years_table_minilm"

CollectionType = Literal["text", "table", "mixed"]
QuestionType = Literal["default", "numeric", "year_comparison"]


ACCOUNT_KEYWORDS = [
    "매출채권", "재고자산", "현금및현금성자산", "매출액",
    "영업이익", "당기순이익", "자산", "부채", "자본"
]

COMPARISON_KEYWORDS = [
    "비교", "차이", "증감", "대비", "변화", "얼마나 늘", "얼마나 줄"
]


def get_client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(
        path=str(CHROMA_PATH),
        settings=chromadb.Settings(anonymized_telemetry=False),
    )


def get_collection(collection_type: Literal["text", "table"]):
    client = get_client()

    if collection_type == "text":
        return client.get_collection(name=TEXT_COLLECTION_NAME)
    if collection_type == "table":
        return client.get_collection(name=TABLE_COLLECTION_NAME)

    raise ValueError(f"Unsupported collection_type: {collection_type}")


def build_where_filter(
    *,
    year: int | None = None,
    company: str | None = None,
    report_type: str | None = None,
    top_section: str | None = None,
    note_number: str | None = None,
    section_title: str | None = None,
    section_type: str | None = None,
) -> dict[str, Any] | None:
    where: dict[str, Any] = {}

    if year is not None:
        where["year"] = year
    if company:
        where["company"] = company
    if report_type:
        where["report_type"] = report_type
    if top_section:
        where["top_section"] = top_section
    if note_number:
        where["note_number"] = note_number
    if section_title:
        where["section_title"] = section_title
    if section_type:
        where["section_type"] = section_type

    return where if where else None


def normalize_query_result(
    result: dict[str, Any],
    *,
    collection_type: Literal["text", "table"],
) -> list[dict[str, Any]]:
    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0] if result.get("distances") else []

    normalized: list[dict[str, Any]] = []

    for i in range(len(ids)):
        normalized.append(
            {
                "collection_type": collection_type,
                "id": ids[i],
                "document": documents[i] if i < len(documents) else "",
                "metadata": metadatas[i] if i < len(metadatas) else {},
                "distance": distances[i] if i < len(distances) else None,
            }
        )

    return normalized


def search_collection(
    *,
    query: str,
    collection_type: Literal["text", "table"],
    n_results: int = 5,
    where: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    collection = get_collection(collection_type)

    query_kwargs: dict[str, Any] = {
        "query_texts": [query],
        "n_results": n_results,
        "include": ["documents", "metadatas", "distances"],
    }

    if where:
        query_kwargs["where"] = where

    result = collection.query(**query_kwargs)
    return normalize_query_result(result, collection_type=collection_type)


def rerank_results(
    results: list[dict[str, Any]],
    *,
    target_account: str | None = None,
    prefer_table: bool = False,
) -> list[dict[str, Any]]:
    reranked = []

    for item in results:
        score = item["distance"] if item["distance"] is not None else 999999.0
        metadata = item.get("metadata", {}) or {}
        doc = item.get("document", "")

        # 계정과목 직접 포함 시 보너스
        if target_account:
            if target_account in doc:
                score -= 0.20
            if target_account in str(metadata.get("section_title", "")):
                score -= 0.25
            if target_account in str(metadata.get("top_section", "")):
                score -= 0.15

        # table 우선
        if prefer_table and item["collection_type"] == "table":
            score -= 0.15

        # 재무제표/주석 쪽 우선
        section_title = str(metadata.get("section_title", ""))
        if any(keyword in section_title for keyword in ["재무상태표", "주석", "매출채권"]):
            score -= 0.10

        new_item = dict(item)
        new_item["reranked_score"] = score
        reranked.append(new_item)

    reranked.sort(key=lambda x: x["reranked_score"])
    return reranked


def merge_results(
    text_results: list[dict[str, Any]],
    table_results: list[dict[str, Any]],
    top_k: int = 5,
    *,
    target_account: str | None = None,
    prefer_table: bool = False,
) -> list[dict[str, Any]]:
    combined = text_results + table_results
    combined = rerank_results(
        combined,
        target_account=target_account,
        prefer_table=prefer_table,
    )
    return combined[:top_k]


def extract_years(query: str) -> list[int]:
    years = re.findall(r"\b(20\d{2}|19\d{2})\b", query)
    return [int(y) for y in years]


def extract_target_account(query: str) -> str | None:
    for keyword in ACCOUNT_KEYWORDS:
        if keyword in query:
            return keyword
    return None


def detect_question_type(query: str) -> QuestionType:
    years = extract_years(query)
    if len(years) >= 2 and any(keyword in query for keyword in COMPARISON_KEYWORDS):
        return "year_comparison"
    return "default"


def search_text_collection(
    *,
    query: str,
    n_results: int = 5,
    where: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return search_collection(
        query=query,
        collection_type="text",
        n_results=n_results,
        where=where,
    )


def search_table_collection(
    *,
    query: str,
    n_results: int = 5,
    where: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return search_collection(
        query=query,
        collection_type="table",
        n_results=n_results,
        where=where,
    )


def retrieve_single(
    *,
    query: str,
    preferred_content_type: CollectionType = "mixed",
    top_k: int = 5,
    where: dict[str, Any] | None = None,
    target_account: str | None = None,
    prefer_table: bool = False,
) -> list[dict[str, Any]]:
    if preferred_content_type == "text":
        results = search_text_collection(query=query, n_results=top_k, where=where)
        return rerank_results(results, target_account=target_account, prefer_table=False)[:top_k]

    if preferred_content_type == "table":
        results = search_table_collection(query=query, n_results=top_k, where=where)
        return rerank_results(results, target_account=target_account, prefer_table=True)[:top_k]

    if preferred_content_type == "mixed":
        text_results = search_text_collection(query=query, n_results=top_k, where=where)
        table_results = search_table_collection(query=query, n_results=top_k, where=where)
        return merge_results(
            text_results,
            table_results,
            top_k=top_k,
            target_account=target_account,
            prefer_table=prefer_table,
        )

    raise ValueError(f"Unsupported preferred_content_type: {preferred_content_type}")


def retrieve_year_comparison(
    *,
    query: str,
    years: list[int],
    target_account: str | None,
    top_k_per_year: int = 4,
) -> list[dict[str, Any]]:
    all_results: list[dict[str, Any]] = []

    prefer_table = target_account is not None

    for year in years[:2]:
        year_query = f"{year} {target_account or query}"
        where = build_where_filter(year=year)

        year_results = retrieve_single(
            query=year_query,
            preferred_content_type="mixed",
            top_k=top_k_per_year,
            where=where,
            target_account=target_account,
            prefer_table=prefer_table,
        )

        for item in year_results:
            item["comparison_year"] = year
        all_results.extend(year_results)

    # 최종 정렬
    all_results = rerank_results(
        all_results,
        target_account=target_account,
        prefer_table=prefer_table,
    )
    return all_results


def retrieve(
    *,
    query: str,
    preferred_content_type: CollectionType = "mixed",
    top_k: int = 5,
    where: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    question_type = detect_question_type(query)
    years = extract_years(query)
    target_account = extract_target_account(query)

    if question_type == "year_comparison" and len(years) >= 2:
        return retrieve_year_comparison(
            query=query,
            years=years,
            target_account=target_account,
            top_k_per_year=max(2, top_k // 2),
        )

    prefer_table = target_account is not None
    return retrieve_single(
        query=query,
        preferred_content_type=preferred_content_type,
        top_k=top_k,
        where=where,
        target_account=target_account,
        prefer_table=prefer_table,
    )