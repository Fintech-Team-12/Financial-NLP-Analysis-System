"""
검색(Retrieval) 레이어.

RetrieverBase: 공통 인터페이스
MockRetriever: in-memory 키워드 검색 (Chroma 없이 동작)

교체 포인트:
  ChromaRetriever(RetrieverBase) 를 구현하고
  get_retriever() 에서 반환하면 됨.
  임베딩/리랭킹 모델 선정도 ChromaRetriever 내부에서 처리.
"""
from abc import ABC, abstractmethod

from app.models.document import NormalizedDocument
from app.services import indexing


class RetrieverBase(ABC):
    """검색 서비스 인터페이스. Chroma 담당자가 이 클래스를 상속해 구현."""

    @abstractmethod
    def search(
        self,
        query: str,
        year: int | None = None,
        doc_type: str | None = None,
        top_k: int = 5,
    ) -> list[NormalizedDocument]:
        """자연어 쿼리로 문서 검색."""
        ...

    @abstractmethod
    def search_by_note_ids(
        self,
        note_ids: list[str],
        year: int,
    ) -> list[NormalizedDocument]:
        """주석 번호 리스트로 해당 주석 문서 직접 검색."""
        ...


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


# ── ChromaRetriever 구현 템플릿 (Chroma 담당자 작업 공간) ────────────────────
#
# class ChromaRetriever(RetrieverBase):
#     def __init__(self, host: str, port: int, collection: str):
#         import chromadb
#         self._client = chromadb.HttpClient(host=host, port=port)
#         self._col = self._client.get_or_create_collection(collection)
#
#     def search(self, query, year=None, doc_type=None, top_k=5):
#         where = {}
#         if year:     where["year"] = year
#         if doc_type: where["doc_type"] = doc_type
#         results = self._col.query(query_texts=[query], n_results=top_k,
#                                   where=where or None)
#         ...  # results → list[NormalizedDocument]
#
#     def search_by_note_ids(self, note_ids, year):
#         results = self._col.get(where={"section": {"$in": note_ids}, "year": year})
#         ...


def get_retriever() -> RetrieverBase:
    """
    Factory: config.mock_mode 에 따라 구현체 선택.
    mock_mode=False 로 전환하면 ChromaRetriever 로 교체.
    """
    from app.core.config import settings
    if settings.mock_mode:
        return MockRetriever()
    # TODO: Chroma 담당자 구현 완료 후 아래 주석 해제
    # return ChromaRetriever(settings.chroma_host, settings.chroma_port, settings.chroma_collection)
    return MockRetriever()
