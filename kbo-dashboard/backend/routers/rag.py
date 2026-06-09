from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.rag_service import RagService


router = APIRouter()
rag_service = RagService()


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    season: Optional[int] = None


@router.post("/rag/ask")
async def ask_rag(request: AskRequest):
    season = request.season or datetime.now().year
    return rag_service.ask(request.question, season)


@router.get("/rag/search")
async def search_rag(query: str, season: Optional[int] = None, limit: int = 8):
    return rag_service.search(query, season or datetime.now().year, limit)
