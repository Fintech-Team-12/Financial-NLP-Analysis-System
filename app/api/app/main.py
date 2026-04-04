# 수정한 사항: stub response를 search plan 기반 응답으로 바꿈
from fastapi import FastAPI

from pydantic import BaseModel
from chroma.search_pipeline import build_search_plan

app = FastAPI(title="Financial Audit RAG API")


class AskRequest(BaseModel):
    question: str
    year: int | None = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ask")
def ask(req: AskRequest) -> dict:
    search_plan = build_search_plan(req.question)

    # 사용자가 request에서 year를 직접 넣었으면 우선 반영
    if req.year is not None:
        if search_plan["metadata_filter"] is None:
            search_plan["metadata_filter"] = {}
        search_plan["metadata_filter"]["year"] = req.year

    return {
        "question": req.question,
        "year": req.year,
        "parsed_query": {
            "clean_query": search_plan["clean_query"],
            "intent": search_plan["intent"],
            "preferred_content_type": search_plan["preferred_content_type"],
        },
        "search_plan": search_plan,
        "answer": "search plan generated",
        "sources": [],
    }