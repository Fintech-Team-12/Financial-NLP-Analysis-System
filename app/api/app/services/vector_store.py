"""
ChromaDB PersistentClient 래퍼.

## 팀 워크플로우 (중요)

  인덱싱 소유권: 팀원의 chroma/ 파이프라인 스크립트
    chroma/load_text_to_chroma.py  → audit_reports_10years_text_minilm  (텍스트 청크)
    chroma/load_table_to_chroma.py → audit_reports_10years_table_minilm (테이블 청크)

  백엔드 역할: 읽기 전용 검색 (search)
    컬렉션명으로 연도를 구분하지 않는다.
    연도 필터링은 metadata의 year 필드를 where 조건으로 사용한다.

## ChromaDB 규칙 (팀원 스크립트 기준)
  - store 경로  : settings.chroma_persist_path  (기본 "chroma_store")
  - 컬렉션     :
      audit_reports_10years_text_minilm   — content_type = "text"
      audit_reports_10years_table_minilm  — content_type = "table"
  - 임베딩 모델 : sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
  - ID 필드     : chunk_id
  - 문서 필드   : embedding_text
  - 메타데이터  : chunk_id, doc_id, year(int), company, report_type,
                  top_section, note_number, section_path, section_level,
                  section_title, section_type, content_type, order_index
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"
import chromadb
from chromadb.utils import embedding_functions

from app.core.config import settings

_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# 팀원 스크립트가 생성하는 실제 컬렉션 이름
_COLLECTION_TEXT  = "audit_reports_10years_text_minilm"
_COLLECTION_TABLE = "audit_reports_10years_table_minilm"
_ALL_COLLECTIONS  = [_COLLECTION_TEXT, _COLLECTION_TABLE]

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


def _get_client() -> chromadb.ClientAPI:
    """
    환경에 따라 ChromaDB 클라이언트 선택.

    로컬 개발 (CHROMA_HOST=localhost 또는 미설정):
      PersistentClient — chroma_store/ 디렉토리를 직접 읽음.

    Docker / 원격 (CHROMA_HOST=chroma 등 localhost 이외):
      HttpClient — docker-compose 의 chroma 컨테이너에 HTTP 접속.
      docker-compose 환경변수: CHROMA_HOST=chroma, CHROMA_PORT=8000
    """
    if settings.chroma_host and settings.chroma_host != "localhost":
        return chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
            settings=chromadb.Settings(anonymized_telemetry=False)
        )
    return chromadb.PersistentClient(
        path=settings.chroma_persist_path,
        settings=chromadb.Settings(anonymized_telemetry=False)
    )


# ── 공개 API ─────────────────────────────────────────────────────────────────

def health_check() -> dict[str, Any]:
    """
    chroma_store 상태 확인.

    store 접근 불가 → store="unavailable"
    접근 가능       → store="ok"
      collection_stats : {컬렉션명: doc_count}
      indexed_years    : text 컬렉션에 데이터가 있는 연도 목록
      empty_years      : 항상 [] (10year 구조에서 연도별 컬렉션이 없으므로 미사용)
      missing_years    : text 컬렉션에 데이터가 없는 연도 목록
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

    # 두 컬렉션 건수 확인
    stats: dict[str, int] = {}
    for cname in _ALL_COLLECTIONS:
        if cname in existing_names:
            try:
                stats[cname] = client.get_collection(name=cname).count()
            except Exception:
                stats[cname] = 0
        else:
            stats[cname] = 0

    # 연도별 인덱싱 여부: text 컬렉션에서 year 메타데이터로 확인
    # text 컬렉션이 없으면 전 연도 missing 처리
    indexed_years: list[int] = []
    missing_years: list[int] = []

    if _COLLECTION_TEXT not in existing_names or stats.get(_COLLECTION_TEXT, 0) == 0:
        return {
            "store": "ok",
            "indexed_years": [],
            "empty_years": [],
            "missing_years": list(_ALL_YEARS),
            "collection_stats": stats,
        }

    try:
        text_col = client.get_collection(name=_COLLECTION_TEXT)
        for year in _ALL_YEARS:
            result = text_col.get(where={"year": year}, limit=1, include=[])
            if result["ids"]:
                indexed_years.append(year)
            else:
                missing_years.append(year)
    except Exception:
        # where 필터 실패 시 컬렉션 존재만 확인
        indexed_years = []
        missing_years = list(_ALL_YEARS)

    return {
        "store": "ok",
        "indexed_years": indexed_years,
        "empty_years": [],
        "missing_years": missing_years,
        "collection_stats": stats,
    }


def collection_exists(year: int) -> bool:
    """
    해당 연도 데이터가 text 컬렉션에 1건 이상 존재하는지 확인.
    연도별 컬렉션명이 아니라 metadata year 필드로 판단한다.
    """
    try:
        client = _get_client()
        existing = {c.name for c in client.list_collections()}
        if _COLLECTION_TEXT not in existing:
            return False
        col = client.get_collection(name=_COLLECTION_TEXT)
        result = col.get(where={"year": year}, limit=1, include=[])
        return len(result["ids"]) > 0
    except Exception:
        return False


def index_year(year: int, force: bool = False) -> dict[str, Any]:
    """
    enriched JSON → ChromaDB 비상 재적재.

    경고: 팀원 load_*.py 스크립트가 정규 인덱싱 경로이며,
          이 함수는 스크립트 실행이 어려운 환경에서만 사용한다.
    force=True 이면 해당 연도의 기존 데이터를 삭제 후 재적재.
    이미 적재됐고 force=False 이면 스킵.

    비상 재적재는 text 컬렉션에만 추가한다 (table 분리 파이프라인 미지원).
    """
    # 실제 파일명 패턴: 삼성전자_audit_report_2014_enriched.json
    pattern = f"*_audit_report_{year}_enriched.json"
    enriched_files = list(Path(settings.chroma_enriched_data_dir).glob(pattern))

    if not enriched_files:
        raise FileNotFoundError(f"Enriched data for year {year} not found in {settings.chroma_enriched_data_dir}")

    enriched_path = enriched_files[0]

    with enriched_path.open("r", encoding="utf-8") as f:
        records: list[dict] = json.load(f)

    valid = [r for r in records if str(r.get("embedding_text", "")).strip()]
    client = _get_client()
    ef = _get_embedding_function()

    collection = client.get_or_create_collection(
        name=_COLLECTION_TEXT,
        embedding_function=ef,
    )

    # force=True 이면 해당 연도 청크만 삭제 (컬렉션 전체 삭제 대신 year where 필터 사용)
    if force:
        try:
            existing_ids = collection.get(where={"year": year}, include=[])["ids"]
            if existing_ids:
                collection.delete(ids=existing_ids)
        except Exception:
            pass
    else:
        # 이미 해당 연도 데이터가 있으면 스킵
        try:
            existing = collection.get(where={"year": year}, limit=1, include=[])
            if existing["ids"]:
                return {
                    "collection": _COLLECTION_TEXT,
                    "indexed": 0,
                    "total": collection.count(),
                    "skipped": True,
                    "message": f"Year {year} already indexed. Use force=true to re-index.",
                }
        except Exception:
            pass

    for i in range(0, len(valid), _BATCH_SIZE):
        batch = valid[i : i + _BATCH_SIZE]
        collection.add(
            ids=[r["chunk_id"] for r in batch],
            documents=[r["embedding_text"] for r in batch],
            metadatas=[
                {
                    "year": int(r.get("year", year)),
                    "company": str(r.get("company", "")),
                    "report_type": str(r.get("report_type", "")),
                    "top_section": str(r.get("top_section", "")),
                    "note_number": str(r.get("note_number", "")),
                    "section_path": str(r.get("section_path", "")),
                    "section_level": int(r.get("section_level", 0)),
                    "section_title": str(r.get("section_title", "")),
                    "section_type": str(r.get("section_type", "")),
                    "content_type": str(r.get("content_type", "text")),
                    "order_index": int(r.get("order_index", 0)),
                }
                for r in batch
            ],
        )

    return {
        "collection": _COLLECTION_TEXT,
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

    text 컬렉션과 table 컬렉션을 모두 조회한 뒤 거리 기준으로 합산·정렬한다.
    year 지정 시 where={"year": year} 메타데이터 필터 적용.
    year=None 이면 전체 연도 대상.

    반환값:
      results  : 거리 오름차순 정렬된 청크 목록 (상위 top_k)
      warnings : 컬렉션 미존재·검색 실패 등 운영 경고 메시지
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

    # 조회 대상 컬렉션 결정
    target_collections = [c for c in _ALL_COLLECTIONS if c in existing_names]
    if not target_collections:
        return {
            "results": [],
            "warnings": [
                f"컬렉션이 존재하지 않습니다 ({', '.join(_ALL_COLLECTIONS)}). "
                "팀원 chroma/load_text_to_chroma.py 및 load_table_to_chroma.py 를 먼저 실행하세요."
            ],
        }

    where = {"year": year} if year is not None else None

    results: list[dict[str, Any]] = []
    for cname in target_collections:
        try:
            collection = client.get_collection(name=cname, embedding_function=ef)
            doc_count = collection.count()
            if doc_count == 0:
                warnings.append(f"'{cname}' 컬렉션이 비어 있습니다.")
                continue

            # year 필터 적용 시 해당 연도 데이터 존재 여부 사전 확인
            if where is not None:
                year_check = collection.get(where=where, limit=1, include=[])
                if not year_check["ids"]:
                    warnings.append(
                        f"'{cname}' 컬렉션에 {year}년 데이터가 없습니다."
                    )
                    continue

            query_kwargs: dict[str, Any] = {
                "query_texts": [query],
                "n_results": min(top_k, doc_count),
            }
            if where is not None:
                query_kwargs["where"] = where

            res = collection.query(**query_kwargs)

        except Exception as exc:
            warnings.append(f"'{cname}' 검색 실패: {exc}")
            continue

        ids       = res["ids"][0]
        docs      = res["documents"][0]
        metas     = res["metadatas"][0]
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


# ── upload 경로 전용: NormalizedDocument → ChromaDB upsert ───────────────────

# NormalizedDocument.doc_type → ChromaDB top_section 메타데이터 매핑
_DOC_TYPE_TO_TOP_SECTION: dict[str, str] = {
    "audit_report": "감사보고서",
    "financial_statement": "재무상태표",
    "note": "주석",
    "other": "",
}


def index_normalized_documents(
    docs: list,  # list[NormalizedDocument]
    force: bool = False,
) -> dict[str, Any]:
    """
    NormalizedDocument 리스트를 text ChromaDB 컬렉션에 upsert.

    upload 완료 후 background/chroma_indexer.py 에서 호출한다.
    기존 팀원 스크립트(load_text_to_chroma.py)와 동일한 컬렉션을 공유하되
    doc_id 형식이 다르므로 (팀 스크립트: UUID, 여기: 사람이 읽을 수 있는 키)
    force=True 시 동일 doc_id 만 삭제 후 재추가한다.

    Args:
        docs: indexing.get_documents_by_year() 결과
        force: True 이면 동일 doc_id 기존 항목 삭제 후 재추가

    Returns:
        {"collection": str, "indexed": int, "total": int}
    """
    if not docs:
        return {"indexed": 0, "collection": _COLLECTION_TEXT, "total": 0}

    client = _get_client()
    ef = _get_embedding_function()
    collection = client.get_or_create_collection(
        name=_COLLECTION_TEXT,
        embedding_function=ef,
    )

    if force:
        ids_to_check = [doc.doc_id for doc in docs]
        try:
            existing = collection.get(ids=ids_to_check, include=[])
            if existing["ids"]:
                collection.delete(ids=existing["ids"])
        except Exception:
            pass  # 존재하지 않는 ID 삭제 시도는 무시

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for i, doc in enumerate(docs):
        ids.append(doc.doc_id)
        documents.append(doc.content)
        metadatas.append({
            "year": doc.year,
            "company": doc.company or "삼성전자",
            "report_type": "감사보고서",
            "top_section": _DOC_TYPE_TO_TOP_SECTION.get(doc.doc_type, ""),
            "note_number": doc.section if doc.doc_type == "note" else "",
            "section_path": doc.parent_section or "",
            "section_level": 1,
            "section_title": doc.section or "",
            "section_type": doc.doc_type,
            "content_type": "text",
            "order_index": i,
        })

    for i in range(0, len(ids), _BATCH_SIZE):
        collection.add(
            ids=ids[i : i + _BATCH_SIZE],
            documents=documents[i : i + _BATCH_SIZE],
            metadatas=metadatas[i : i + _BATCH_SIZE],
        )

    return {
        "collection": _COLLECTION_TEXT,
        "indexed": len(ids),
        "total": collection.count(),
    }


def index_uploaded_table_chunks(
    chunks: list[dict],
    force: bool = False,
) -> dict[str, Any]:
    """
    enriched table chunk 리스트를 table ChromaDB 컬렉션에 upsert.

    upload 완료 후 background/chroma_indexer.py 에서 호출한다.
    팀원 load_table_to_chroma.py 와 동일한 컬렉션·메타데이터 스키마를 사용한다.

    Args:
        chunks: indexing.load_table_chunks_from_file() 의 반환값
                (content_type="table" 인 enriched 레코드)
        force:  True 이면 동일 chunk_id 기존 항목 삭제 후 재추가

    Returns:
        {"collection": str, "indexed": int, "total": int}
    """
    if not chunks:
        return {"indexed": 0, "collection": _COLLECTION_TABLE, "total": 0}

    client = _get_client()
    ef = _get_embedding_function()
    collection = client.get_or_create_collection(
        name=_COLLECTION_TABLE,
        embedding_function=ef,
    )

    if force:
        ids_to_check = [c["chunk_id"] for c in chunks]
        try:
            existing = collection.get(ids=ids_to_check, include=[])
            if existing["ids"]:
                collection.delete(ids=existing["ids"])
        except Exception:
            pass

    ids: list[str] = [c["chunk_id"] for c in chunks]
    # load_table_to_chroma.py 와 동일하게 2000자 truncation 적용
    documents: list[str] = [str(c.get("embedding_text", ""))[:2000] for c in chunks]
    metadatas: list[dict[str, Any]] = [
        {
            "chunk_id":     str(c.get("chunk_id", "")),
            "doc_id":       str(c.get("doc_id", "")),
            "year":         int(c.get("year", 0)),
            "company":      str(c.get("company", "")),
            "report_type":  str(c.get("report_type", "")),
            "top_section":  str(c.get("top_section", "")),
            "note_number":  str(c.get("note_number", "") or ""),
            "section_path": str(c.get("section_path", "")),
            "section_level":int(c.get("section_level", 0)),
            "section_title":str(c.get("section_title", "")),
            "section_type": str(c.get("section_type", "table")),
            "content_type": "table",
            "order_index":  int(c.get("order_index", 0)),
        }
        for c in chunks
    ]

    for i in range(0, len(ids), _BATCH_SIZE):
        collection.add(
            ids=ids[i : i + _BATCH_SIZE],
            documents=documents[i : i + _BATCH_SIZE],
            metadatas=metadatas[i : i + _BATCH_SIZE],
        )

    return {
        "collection": _COLLECTION_TABLE,
        "indexed": len(ids),
        "total": collection.count(),
    }
