from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from services.player_service import PlayerService

router = APIRouter()
player_service = PlayerService()


@router.get("/players/hitters")
async def get_hitters(season: int = None, limit: int = 50, db: Session = Depends(get_db)):
    """
    타자 순위를 반환합니다.
    """
    return player_service.get_hitters(db, season, limit)


@router.get("/players/pitchers")
async def get_pitchers(season: int = None, limit: int = 50, db: Session = Depends(get_db)):
    """
    투수 순위를 반환합니다.
    """
    return player_service.get_pitchers(db, season, limit)


@router.get("/players/search/{player_name}")
async def search_player(player_name: str, season: int = None, db: Session = Depends(get_db)):
    """
    선수명으로 검색합니다.
    """
    return player_service.get_player_by_name(db, player_name, season)


@router.get("/players/team/{team_name}")
async def get_team_players(team_name: str, season: int = None, player_type: str = "hitter", db: Session = Depends(get_db)):
    """
    팀별 선수들을 반환합니다.
    """
    return player_service.get_team_players(db, team_name, season, player_type)
