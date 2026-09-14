"""CSV 기반 RAG(검색+답변) 엔드포인트.

질의에 대해 data/processed CSV에서 근거 문서를 검색(retrieve)하고, 의도에 맞는
요약 답변을 합성(synthesize)해 반환한다. 실제 로직은 RagService 가 담당한다.
"""
from datetime import datetime
from typing import Optional
from typing import Literal

from fastapi import APIRouter, Depends, Query
from security import CURRENT_YEAR, Season, limit_expensive_requests
from pydantic import BaseModel, Field, field_validator

from services.rag_service import RagService
from services.qa_service import QuestionAnswerService


router = APIRouter(dependencies=[Depends(limit_expensive_requests)])
rag_service = RagService()
qa_service = QuestionAnswerService()


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1000)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    season: Optional[int] = Field(None, ge=1982, le=CURRENT_YEAR)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=4)

    @field_validator('question')
    @classmethod
    def nonblank_question(cls, value):
        if not value.strip():
            raise ValueError('question must not be blank')
        return value.strip()


@router.post("/rag/ask")
def ask_rag(request: AskRequest):
    """질문에 대한 답변 + 근거 문서를 반환한다."""
    season = request.season or datetime.now().year
    return qa_service.ask(request.question, season, [m.model_dump() for m in request.history])


@router.get("/rag/search")
def search_rag(query: str = Query(min_length=1, max_length=2000), season: Season = None, limit: int = Query(8, ge=1, le=20)):
    """답변 합성 없이 검색된 근거 문서만 반환한다."""
    return rag_service.search(query, season or datetime.now().year, limit)
