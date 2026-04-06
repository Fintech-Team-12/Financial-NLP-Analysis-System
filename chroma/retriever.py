from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import chromadb


BASE_DIR = Path(__file__).resolve().parent
# chroma_store 는 프로젝트 루트에 있음 (chroma/ 하위가 아님)
CHROMA_PATH = BASE_DIR.parent / "chroma_store"

TEXT_COLLECTION_NAME = "audit_reports_10years_text_minilm"
TABLE_COLLECTION_NAME = "audit_reports_10years_table_minilm"


CollectionType = Literal["text", "table", "mixed"]


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
    """
    Chroma metadata filter 생성.
    비어 있으면 None 반환.
    """
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
    """
    Chroma query 결과를 다루기 쉬운 list[dict] 형태로 정규화.
    """
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
    """
    단일 컬렉션(text 또는 table) 검색
    """
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


def merge_results(
    text_results: list[dict[str, Any]],
    table_results: list[dict[str, Any]],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """
    mixed 검색 시 간단 병합.
    현재는 distance 기준 오름차순 정렬.
    distance가 없으면 뒤로 보냄.
    """
    combined = text_results + table_results

    combined.sort(
        key=lambda x: x["distance"] if x["distance"] is not None else float("inf")
    )

    return combined[:top_k]


def retrieve(
    *,
    query: str,
    preferred_content_type: CollectionType = "mixed",
    top_k: int = 5,
    where: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    질문 의도에 따라 text / table / mixed retrieval 수행.
    """
    if preferred_content_type == "text":
        return search_text_collection(
            query=query,
            n_results=top_k,
            where=where,
        )

    if preferred_content_type == "table":
        return search_table_collection(
            query=query,
            n_results=top_k,
            where=where,
        )

    if preferred_content_type == "mixed":
        # mixed는 두 컬렉션에서 각각 top_k씩 가져온 뒤 병합
        text_results = search_text_collection(
            query=query,
            n_results=top_k,
            where=where,
        )
        table_results = search_table_collection(
            query=query,
            n_results=top_k,
            where=where,
        )
        return merge_results(text_results, table_results, top_k=top_k)

    raise ValueError(f"Unsupported preferred_content_type: {preferred_content_type}")


if __name__ == "__main__":
    sample_cases = [
        {
            "query": "재무제표에 대한 경영진의 책임",
            "preferred_content_type": "text",
            "where": {"year": 2014},
        },
        {
            "query": "현금및현금성자산",
            "preferred_content_type": "table",
            "where": {"year": 2014},
        },
        {
            "query": "법인세비용",
            "preferred_content_type": "mixed",
            "where": {"year": 2014},
        },
    ]

    for case in sample_cases:
        print("=" * 100)
        print(f"query: {case['query']}")
        print(f"preferred_content_type: {case['preferred_content_type']}")
        print(f"where: {case['where']}")

        results = retrieve(
            query=case["query"],
            preferred_content_type=case["preferred_content_type"],
            top_k=3,
            where=case["where"],
        )

        for i, item in enumerate(results, start=1):
            print(f"\n[{i}] collection_type={item['collection_type']}")
            print("id:", item["id"])
            print("distance:", item["distance"])
            print("metadata:", item["metadata"])
            print("document:", item["document"][:300], "...")