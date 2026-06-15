"""CSV 기반 RAG(검색+답변) 엔드포인트.

질의에 대해 data/processed CSV에서 근거 문서를 검색(retrieve)하고, 의도에 맞는
요약 답변을 합성(synthesize)해 반환한다. 실제 로직은 RagService 가 담당한다.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.rag_service import RagService


router = APIRouter()
rag_service = RagService()


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)  # 사용자 질문 (빈 문자열 불가)
    season: Optional[int] = None  # 미지정 시 현재 연도 사용


@router.post("/rag/ask")
async def ask_rag(request: AskRequest):
    """질문에 대한 답변 + 근거 문서를 반환한다."""
    season = request.season or datetime.now().year
    return rag_service.ask(request.question, season)


@router.get("/rag/search")
async def search_rag(query: str, season: Optional[int] = None, limit: int = 8):
    """답변 합성 없이 검색된 근거 문서만 반환한다."""
    return rag_service.search(query, season or datetime.now().year, limit)
