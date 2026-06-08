from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from services.schedule_service import ScheduleService

router = APIRouter()
schedule_service = ScheduleService()


@router.get("/schedule")
async def get_schedule(season: int = None, team: str = None, db: Session = Depends(get_db)):
    """
    현재 시즌 또는 지정된 시즌의 경기 일정을 반환합니다.
    """
    return schedule_service.get_schedule(db, season, team)


@router.get("/schedule/{date}")
async def get_schedule_by_date(date: str, db: Session = Depends(get_db)):
    """
    특정 날짜의 경기 일정을 반환합니다.
    """
    return schedule_service.get_schedule_by_date(db, date)
