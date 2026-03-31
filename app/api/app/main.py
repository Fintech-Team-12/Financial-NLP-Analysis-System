from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Financial Audit RAG API")


class AskRequest(BaseModel):
    question: str
    year: int | None = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ask")
def ask(req: AskRequest) -> dict:
    return {
        "question": req.question,
        "year": req.year,
        "answer": "stub response",
        "sources": [],
    }
