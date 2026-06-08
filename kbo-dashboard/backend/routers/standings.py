from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from services.standings_service import StandingsService

router = APIRouter()
standings_service = StandingsService()


@router.get("/standings")
async def get_standings(season: int = None, db: Session = Depends(get_db)):
    """
    현재 시즌 또는 지정된 시즌의 순위표를 반환합니다.
    """
    return standings_service.get_standings(db, season)


@router.get("/standings/{team_id}")
async def get_team_standings(team_id: str, season: int = None, db: Session = Depends(get_db)):
    """
    특정 팀의 상세 순위 정보를 반환합니다.
    """
    return standings_service.get_team_standings(db, team_id, season)
