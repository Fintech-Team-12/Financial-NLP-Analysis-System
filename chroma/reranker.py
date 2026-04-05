from __future__ import annotations

from typing import Any

from sentence_transformers import CrossEncoder


DEFAULT_RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class CrossEncoderReranker:
    def __init__(self, model_name: str = DEFAULT_RERANK_MODEL, max_length: int = 512):
        self.model_name = model_name
        self.max_length = max_length
        self.model = CrossEncoder(model_name, max_length=max_length)

    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []

        pairs = []
        for item in candidates:
            document = item.get("document", "") or ""
            pairs.append((query, document))

        scores = self.model.predict(pairs)

        rescored: list[dict[str, Any]] = []
        for item, score in zip(candidates, scores):
            new_item = dict(item)
            new_item["rerank_score"] = float(score)
            rescored.append(new_item)

        rescored.sort(key=lambda x: x["rerank_score"], reverse=True)

        if top_k is not None:
            return rescored[:top_k]
        return rescored


def simple_demo() -> None:
    sample_query = "재무제표에 대한 경영진의 책임"

    sample_candidates = [
        {
            "id": "doc1",
            "document": "재무제표에 대한 경영진의 책임 | 경영진은 한국채택국제회계기준에 따라 ...",
            "metadata": {"section_title": "재무제표에 대한 경영진의 책임"},
        },
        {
            "id": "doc2",
            "document": "공정가치금융자산 | 보고기간종료일 현재 공정가치금융자산의 구성내역은 ...",
            "metadata": {"section_title": "공정가치금융자산"},
        },
    ]

    reranker = CrossEncoderReranker()
    reranked = reranker.rerank(sample_query, sample_candidates)

    print("=" * 80)
    print("Reranker Demo")
    print("=" * 80)
    for i, item in enumerate(reranked, start=1):
        print(f"[{i}] id={item['id']}")
        print("rerank_score:", item["rerank_score"])
        print("section_title:", (item.get("metadata", {}) or {}).get("section_title"))
        print("document:", item["document"][:200], "...")


if __name__ == "__main__":
    simple_demo()