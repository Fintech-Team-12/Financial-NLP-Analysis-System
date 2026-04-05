"""
검색(Retrieval) 레이어.

RetrieverBase  : 공통 인터페이스
MockRetriever  : in-memory 키워드 검색 (Chroma 없이 동작, MOCK_MODE=true)
ChromaRetriever: ChromaDB 의미 유사도 검색 (MOCK_MODE=false)

## MOCK_MODE 전환 방법
  환경변수 MOCK_MODE=false 설정 → get_retriever() 가 ChromaRetriever 반환.
  ChromaRetriever 는 vector_store.search() 에 위임하므로
  chroma_store 가 먼저 구축되어 있어야 한다.

## ChromaRetriever → NormalizedDocument 변환
  ChromaDB 메타데이터 필드 매핑:
    chunk_id (id)  → doc_id
    top_section    → doc_type (없으면 section_path 첫 세그먼트로 추론)
    year           → year
    section_title  → section
    embedding_text → content
    section_path   → parent_section
    numeric_value  → None  (ChromaDB 에 미저장)
    related_notes  → []    (ChromaDB 에 미저장)

## note_number 검색
  ChromaDB 메타데이터에 note_number 필드가 실제 저장됨.
  search_by_note_ids() 는 임베딩 유사도 검색 대신
  note_number + year exact filter 로 정확하게 조회한다.
"""
from abc import ABC, abstractmethod

from app.models.document import NormalizedDocument
from app.services import indexing


class RetrieverBase(ABC):
    """검색 서비스 인터페이스."""

    @abstractmethod
    def search(
        self,
        query: str,
        year: int | None = None,
        doc_type: str | None = None,
        top_k: int = 5,
    ) -> list[NormalizedDocument]:
        ...

    @abstractmethod
    def search_by_note_ids(
        self,
        note_ids: list[str],
        year: int,
    ) -> list[NormalizedDocument]:
        ...


# ── MockRetriever ────────────────────────────────────────────────────────────

class MockRetriever(RetrieverBase):
    """
    In-memory 키워드 매칭 검색.
    Chroma 없이 로컬 개발 및 CI 에서 사용.
    검색 품질은 낮지만 구조·흐름 검증에 충분.
    """

    def search(
        self,
        query: str,
        year: int | None = None,
        doc_type: str | None = None,
        top_k: int = 5,
    ) -> list[NormalizedDocument]:
        docs = indexing.get_all_documents()
        keywords = [w for w in query.replace("년", " ").split() if len(w) > 1]

        scored: list[tuple[float, NormalizedDocument]] = []
        for doc in docs:
            if year is not None and doc.year != year:
                continue
            if doc_type is not None and doc.doc_type != doc_type:
                continue
            score = sum(1.0 for kw in keywords if kw in doc.content)
            if score > 0:
                scored.append((score, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored[:top_k]]

    def search_by_note_ids(
        self,
        note_ids: list[str],
        year: int,
    ) -> list[NormalizedDocument]:
        return indexing.find_by_note_ids(year, note_ids)


# ── ChromaRetriever ──────────────────────────────────────────────────────────

_SECTION_PATH_TO_DOC_TYPE: dict[str, str] = {
    "감사보고서": "audit_report",
    "부록": "audit_report",
    "주석": "note",
    "재무상태표": "financial_statement",
    "손익계산서": "financial_statement",
    "포괄손익계산서": "financial_statement",
    "자본변동표": "financial_statement",
    "현금흐름표": "financial_statement",
}


def _infer_doc_type(meta: dict) -> str:
    """
    메타데이터에서 doc_type 결정.

    우선순위:
      1. top_section 필드 — 팀원 적재 스크립트가 직접 저장한 최상위 섹션명
      2. section_path 첫 세그먼트 — top_section 미존재 시 폴백 (레거시/mock 호환)
    """
    top = meta.get("top_section") or (
        meta.get("section_path", "").split(" > ")[0].strip()
    )
    return _SECTION_PATH_TO_DOC_TYPE.get(top, "other")


def _chunk_to_normalized(chunk: dict, default_year: int) -> NormalizedDocument:
    """
    vector_store.search() / chromadb get() 결과 1건 → NormalizedDocument 변환.

    doc_type : top_section 또는 section_path 첫 세그먼트로 결정.
    numeric_value, related_notes : ChromaDB 에 미저장 → None / [].
    """
    meta = chunk.get("metadata", {})
    return NormalizedDocument(
        doc_id=chunk["id"],
        doc_type=_infer_doc_type(meta),
        year=int(meta.get("year", default_year)),
        section=meta.get("section_title", ""),
        content=chunk.get("document", ""),
        numeric_value=None,
        related_notes=[],
        parent_section=meta.get("section_path", ""),
    )


class ChromaRetriever(RetrieverBase):
    """
    ChromaDB PersistentClient 기반 의미 유사도 검색.
    vector_store.search() 에 위임하여 중복 클라이언트 생성을 방지.

    MOCK_MODE=false + chroma_store 구축 완료 시 사용.
    """

    def search(
        self,
        query: str,
        year: int | None = None,
        doc_type: str | None = None,
        top_k: int = 5,
    ) -> list[NormalizedDocument]:
        from app.services import vector_store

        data = vector_store.search(query, year=year, top_k=top_k)
        docs = [
            _chunk_to_normalized(chunk, year or 0)
            for chunk in data["results"]
        ]

        if doc_type is not None:
            docs = [d for d in docs if d.doc_type == doc_type]

        return docs[:top_k]

    def search_by_note_ids(
        self,
        note_ids: list[str],
        year: int,
    ) -> list[NormalizedDocument]:
        """
        note_number 메타데이터 exact filter 로 주석 청크 직접 조회.

        팀원 적재 스크립트가 note_number 를 ChromaDB 메타데이터에 실제 저장하므로
        임베딩 유사도 검색 대신 정확한 메타데이터 필터를 사용한다.
        text / table 두 컬렉션 모두 조회하여 중복 제거 후 반환.
        """
        from app.services import vector_store

        try:
            chroma_client = vector_store._get_client()
            existing = {c.name for c in chroma_client.list_collections()}
        except Exception:
            return []

        seen_ids: set[str] = set()
        results: list[NormalizedDocument] = []

        for cname in [vector_store._COLLECTION_TEXT, vector_store._COLLECTION_TABLE]:
            if cname not in existing:
                continue
            try:
                col = chroma_client.get_collection(name=cname)
                for note_id in note_ids:
                    where = {
                        "$and": [
                            {"note_number": {"$eq": str(note_id)}},
                            {"year": {"$eq": year}},
                        ]
                    }
                    res = col.get(where=where, include=["documents", "metadatas"])
                    for chunk_id, doc, meta in zip(
                        res["ids"],
                        res.get("documents") or [],
                        res.get("metadatas") or [],
                    ):
                        if chunk_id not in seen_ids:
                            seen_ids.add(chunk_id)
                            results.append(
                                _chunk_to_normalized(
                                    {"id": chunk_id, "document": doc, "metadata": meta},
                                    year,
                                )
                            )
            except Exception:
                continue

        return results


# ── Factory ──────────────────────────────────────────────────────────────────

def get_retriever() -> RetrieverBase:
    """
    MOCK_MODE=true  → MockRetriever  (in-memory, Chroma 불필요)
    MOCK_MODE=false → ChromaRetriever (chroma_store 필요)
    """
    from app.core.config import settings

    if settings.mock_mode:
        return MockRetriever()
    return ChromaRetriever()
    print("MOCK_MODE:", settings.mock_mode)
    print("Using MockRetriever" if settings.mock_mode else "Using ChromaRetriever")

