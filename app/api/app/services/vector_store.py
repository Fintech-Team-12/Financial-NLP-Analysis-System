"""
ChromaDB PersistentClient 래퍼.

## 팀 워크플로우 (중요)

  인덱싱 소유권: 팀원의 chroma/ 파이프라인 스크립트
    chroma/load_2014_to_chroma.py ~ load_2024_to_chroma.py 를 실행해야
    ./chroma_store 에 "audit_reports_{year}" 컬렉션이 생성됨.

  백엔드 역할: 읽기 전용 검색 (search)
    vector_store.py 는 chroma_store 를 직접 수정하지 않는 것이 원칙.
    POST /vector/index 는 enriched JSON 으로부터 비상 재적재하는 용도이며,
    팀원 스크립트가 실행된 이후에는 사용하지 않는다.

## ChromaDB 규칙 (팀원 스크립트 기준)
  - store 경로  : settings.chroma_persist_path  (기본 "chroma_store")
  - 컬렉션 이름 : "audit_reports_{year}"  (2014–2024, 연도별 1개)
  - 임베딩 모델 : paraphrase-multilingual-MiniLM-L12-v2
  - ID 필드     : chunk_id
  - 문서 필드   : embedding_text
  - 메타데이터  : year, company, report_type, section_path, section_title, content_type
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils import embedding_functions

from app.core.config import settings

_EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
_COLLECTION_PREFIX = "audit_reports"
_ALL_YEARS = list(range(2014, 2025))
_BATCH_SIZE = 500


# ── 내부 팩토리 ─────────────────────────────────────────────────────────────
# 임베딩 모델은 최초 1회만 로딩. SentenceTransformer 초기화는 ~1–2초 소요.
# 테스트에서는 app.services.vector_store._get_embedding_function 을 patch.

@lru_cache(maxsize=1)
def _get_embedding_function() -> embedding_functions.SentenceTransformerEmbeddingFunction:
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=_EMBEDDING_MODEL
    )


def _get_client() -> chromadb.PersistentClient:
    """매 호출마다 새 클라이언트 생성. PersistentClient 는 SQLite 열기라 빠름."""
    return chromadb.PersistentClient(path=settings.chroma_persist_path)


# ── 공개 API ─────────────────────────────────────────────────────────────────

def health_check() -> dict[str, Any]:
    """
    chroma_store 상태를 연도별로 반환.

    store 접근 불가 → store="unavailable"
    접근 가능       → store="ok"
      indexed_years   : 컬렉션이 존재하고 1건 이상 적재된 연도
      empty_years     : 컬렉션은 있지만 0건 (적재 중 또는 오류)
      missing_years   : 컬렉션 자체가 없는 연도 (팀원 스크립트 미실행)
      collection_stats: {year_str: doc_count}
    """
    try:
        client = _get_client()
        existing_names = {c.name for c in client.list_collections()}
    except Exception as exc:
        return {
            "store": "unavailable",
            "error": str(exc),
            "indexed_years": [],
            "empty_years": [],
            "missing_years": _ALL_YEARS,
            "collection_stats": {},
        }

    indexed_years: list[int] = []
    empty_years: list[int] = []
    missing_years: list[int] = []
    stats: dict[str, int] = {}

    for year in _ALL_YEARS:
        cname = f"{_COLLECTION_PREFIX}_{year}"
        if cname not in existing_names:
            missing_years.append(year)
            continue
        try:
            count = client.get_collection(name=cname).count()
            stats[str(year)] = count
            if count > 0:
                indexed_years.append(year)
            else:
                empty_years.append(year)
        except Exception:
            missing_years.append(year)

    return {
        "store": "ok",
        "indexed_years": indexed_years,
        "empty_years": empty_years,
        "missing_years": missing_years,
        "collection_stats": stats,
    }


def collection_exists(year: int) -> bool:
    """해당 연도 컬렉션이 존재하고 1건 이상 적재됐는지 확인."""
    try:
        client = _get_client()
        existing = {c.name for c in client.list_collections()}
        cname = f"{_COLLECTION_PREFIX}_{year}"
        if cname not in existing:
            return False
        return client.get_collection(name=cname).count() > 0
    except Exception:
        return False


def index_year(year: int, force: bool = False) -> dict[str, Any]:
    """
    enriched JSON → ChromaDB 비상 재적재.

    경고: 팀원 load_*.py 스크립트가 정규 인덱싱 경로이며,
          이 함수는 스크립트 실행이 어려운 환경에서만 사용한다.
    force=True 이면 기존 컬렉션을 삭제 후 재적재.
    이미 적재됐고 force=False 이면 스킵.
    """
    enriched_path = (
        Path(settings.chroma_enriched_data_dir) / f"audit_report_{year}_enriched.json"
    )
    if not enriched_path.exists():
        raise FileNotFoundError(f"Enriched data not found: {enriched_path}")

    with enriched_path.open("r", encoding="utf-8") as f:
        records: list[dict] = json.load(f)

    valid = [r for r in records if str(r.get("embedding_text", "")).strip()]
    collection_name = f"{_COLLECTION_PREFIX}_{year}"
    client = _get_client()
    ef = _get_embedding_function()

    if force:
        try:
            client.delete_collection(name=collection_name)
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=ef,
    )

    if collection.count() > 0 and not force:
        return {
            "collection": collection_name,
            "indexed": 0,
            "total": collection.count(),
            "skipped": True,
            "message": "Already indexed. Use force=true to re-index.",
        }

    for i in range(0, len(valid), _BATCH_SIZE):
        batch = valid[i : i + _BATCH_SIZE]
        collection.add(
            ids=[r["chunk_id"] for r in batch],
            documents=[r["embedding_text"] for r in batch],
            metadatas=[
                {
                    "year": r.get("year", year),
                    "company": str(r.get("company", "")),
                    "report_type": str(r.get("report_type", "")),
                    "section_path": str(r.get("section_path", "")),
                    "section_title": str(r.get("section_title", "")),
                    "content_type": str(r.get("content_type", "")),
                }
                for r in batch
            ],
        )

    return {
        "collection": collection_name,
        "indexed": len(valid),
        "total": collection.count(),
        "skipped": False,
    }


def search(
    query: str,
    year: int | None,
    top_k: int = 5,
) -> dict[str, Any]:
    """
    의미 유사도 기반 청크 검색.

    반환값:
      results  : 거리 오름차순 정렬된 청크 목록 (상위 top_k)
      warnings : 요청된 연도 컬렉션 미존재 등 운영 경고 메시지

    year 지정 시 해당 연도 컬렉션만, None 이면 전체 연도 합산 후 상위 top_k.
    요청 연도의 컬렉션이 없으면 results=[] + warnings 에 안내 메시지 포함.
    """
    warnings: list[str] = []

    try:
        client = _get_client()
        ef = _get_embedding_function()
    except Exception as exc:
        return {
            "results": [],
            "warnings": [f"ChromaDB 연결 실패: {exc}"],
        }

    existing_names = {c.name for c in client.list_collections()}

    if year is not None:
        cname = f"{_COLLECTION_PREFIX}_{year}"
        if cname not in existing_names:
            return {
                "results": [],
                "warnings": [
                    f"'{cname}' 컬렉션이 존재하지 않습니다. "
                    f"팀원 chroma/load_{year}_to_chroma.py 를 실행하거나 "
                    f"POST /vector/index 를 호출하세요."
                ],
            }
        collection_names = [cname]
    else:
        collection_names = [
            c for c in existing_names if c.startswith(_COLLECTION_PREFIX)
        ]
        if not collection_names:
            return {
                "results": [],
                "warnings": ["인덱싱된 컬렉션이 없습니다. 팀원 chroma/ 스크립트를 먼저 실행하세요."],
            }

    results: list[dict[str, Any]] = []
    for cname in collection_names:
        try:
            collection = client.get_collection(name=cname, embedding_function=ef)
            doc_count = collection.count()
            if doc_count == 0:
                warnings.append(f"'{cname}' 컬렉션이 비어 있습니다.")
                continue
            res = collection.query(query_texts=[query], n_results=min(top_k, doc_count))
        except Exception as exc:
            warnings.append(f"'{cname}' 검색 실패: {exc}")
            continue

        ids = res["ids"][0]
        docs = res["documents"][0]
        metas = res["metadatas"][0]
        distances = res.get("distances", [[None] * len(ids)])[0]

        for doc_id, doc, meta, dist in zip(ids, docs, metas, distances):
            results.append(
                {
                    "id": doc_id,
                    "document": doc,
                    "metadata": meta,
                    "distance": dist,
                    "collection": cname,
                }
            )

    results.sort(
        key=lambda x: x["distance"] if x["distance"] is not None else float("inf")
    )
    return {"results": results[:top_k], "warnings": warnings}
