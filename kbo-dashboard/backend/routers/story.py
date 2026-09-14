"""AI 데일리 경기 스토리 엔드포인트."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from security import Season, limit_expensive_requests, validated_date

from services.story_service import StoryService

router = APIRouter(dependencies=[Depends(limit_expensive_requests)])
story_service = StoryService()


@router.get("/today-story")
def today_story(date: Optional[str] = None, season: Season = None):
    """특정 날짜(기본: 오늘 KST)의 경기별 AI 프리뷰/리뷰를 반환한다."""
    date = validated_date(date)
    if season is not None and season != int(date[:4]):
        raise HTTPException(422, "season must match date year")
    season = season or int(date[:4])
    return story_service.stories_for_date(date, season)
