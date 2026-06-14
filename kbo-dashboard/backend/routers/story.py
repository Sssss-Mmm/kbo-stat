"""AI 데일리 경기 스토리 엔드포인트."""
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from services.story_service import StoryService

router = APIRouter()
story_service = StoryService()
KST = ZoneInfo("Asia/Seoul")


@router.get("/today-story")
async def today_story(date: Optional[str] = None, season: Optional[int] = None):
    """특정 날짜(기본: 오늘 KST)의 경기별 AI 프리뷰/리뷰를 반환한다."""
    date = date or datetime.now(KST).strftime("%Y-%m-%d")
    season = season or int(date[:4])
    return story_service.stories_for_date(date, season)
