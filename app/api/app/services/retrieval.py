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
    chunk_id (id)      → doc_id
    content_type       → doc_type
    year               → year
    section_title      → section
    embedding_text     → content
    section_path       → parent_section
    numeric_value      → None  (ChromaDB 에 미저장)
    related_notes      → []    (ChromaDB 에 미저장)
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

def _chunk_to_normalized(chunk: dict, default_year: int) -> NormalizedDocument:
    """
    vector_store.search() 결과 1건 → NormalizedDocument 변환.

    numeric_value 와 related_notes 는 ChromaDB 에 저장되지 않아 None/[].
    ChromaRetriever 를 통한 /qa 응답은 금액 직접 추출이 불가능하므로
    NUMERIC 유형 질문에서는 MockRetriever + in-memory 인덱스가 더 정확하다.
    """
    meta = chunk.get("metadata", {})
    return NormalizedDocument(
        doc_id=chunk["id"],
        doc_type=meta.get("content_type", "unknown"),
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

        # doc_type 필터: ChromaDB 메타데이터 content_type 으로 후처리
        if doc_type is not None:
            docs = [d for d in docs if d.doc_type == doc_type]

        return docs[:top_k]

    def search_by_note_ids(
        self,
        note_ids: list[str],
        year: int,
    ) -> list[NormalizedDocument]:
        """
        ChromaDB 에는 note_number 메타데이터가 없어 where 필터 불가.
        각 note ID 를 텍스트 쿼리로 변환하여 임베딩 검색으로 대체.

        한계: 동음이의 주석 번호에서 오검색 가능.
        정확한 주석 검색이 필요하면 팀원 스크립트에서
        note_number 를 ChromaDB 메타데이터로 추가해야 한다.
        """
        from app.services import vector_store

        seen_ids: set[str] = set()
        results: list[NormalizedDocument] = []

        for note_id in note_ids:
            data = vector_store.search(f"주석 {note_id}", year=year, top_k=2)
            for chunk in data["results"]:
                if chunk["id"] not in seen_ids:
                    seen_ids.add(chunk["id"])
                    results.append(_chunk_to_normalized(chunk, year))

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
