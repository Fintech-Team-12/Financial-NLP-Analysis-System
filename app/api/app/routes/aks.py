from fastapi import APIRouter
from pydantic import BaseModel
from app.services.rag_service import make_rag_response

router = APIRouter()


class AskRequest(BaseModel):
    question: str


@router.post("/ask")
def ask(request: AskRequest):
    return make_rag_response(request.question)