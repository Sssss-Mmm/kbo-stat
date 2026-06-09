"""분석 도메인 읽기 API.

프론트엔드(web/*.js)의 CSV 파싱을 그대로 대체할 수 있도록, 응답 JSON의
키를 원본 CSV 컬럼명(한글 포함)과 동일하게 맞춘다.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import (
    Attendance,
    GameTimeTeam,
    GameTimeYearly,
    HitterMetric,
    TeamGame,
    TeamMonthly,
    TeamRankHistory,
)
from utils import current_season

router = APIRouter()


def _f(value):
    return float(value) if value is not None else None


def _ok(data):
    return {"status": "success", "count": len(data), "data": data}


@router.get("/team-rank-history")
async def team_rank_history(season: int = None, db: Session = Depends(get_db)):
    season = season or current_season()
    rows = (
        db.query(TeamRankHistory)
        .filter(TeamRankHistory.season == season)
        .order_by(TeamRankHistory.date, TeamRankHistory.rank)
        .all()
    )
    return _ok([
        {
            "Season": r.season,
            "Date": r.date,
            "순위": r.rank,
            "팀명": r.team,
            "경기": r.games,
            "승": r.wins,
            "패": r.losses,
            "무": r.draws,
            "승률": _f(r.win_rate),
            "게임차": _f(r.games_behind),
            "최근10경기": r.last_10_games,
            "연속": r.streak,
            "홈": r.home_record,
            "방문": r.away_record,
        }
        for r in rows
    ])


@router.get("/team-games")
async def team_games(season: int = None, team: str = None, db: Session = Depends(get_db)):
    season = season or current_season()
    query = db.query(TeamGame).filter(TeamGame.season == season)
    if team:
        query = query.filter(TeamGame.team == team)
    rows = query.order_by(TeamGame.date).all()
    return _ok([
        {
            "Season": r.season,
            "Date": r.date,
            "Month": r.month,
            "GameId": r.game_id,
            "Team": r.team,
            "Opponent": r.opponent,
            "HomeAway": r.home_away,
            "Ballpark": r.ballpark,
            "RunsFor": r.runs_for,
            "RunsAgainst": r.runs_against,
            "RunDiff": r.run_diff,
            "Result": r.result,
            "Win": r.win,
            "Loss": r.loss,
            "Draw": r.draw,
        }
        for r in rows
    ])


@router.get("/team-monthly")
async def team_monthly(season: int = None, team: str = None, db: Session = Depends(get_db)):
    season = season or current_season()
    query = db.query(TeamMonthly).filter(TeamMonthly.season == season)
    if team:
        query = query.filter(TeamMonthly.team == team)
    rows = query.order_by(TeamMonthly.month).all()
    return _ok([
        {
            "Season": r.season,
            "Month": r.month,
            "Team": r.team,
            "Games": r.games,
            "Wins": r.wins,
            "Losses": r.losses,
            "Draws": r.draws,
            "RunsFor": r.runs_for,
            "RunsAgainst": r.runs_against,
            "RunDiff": r.run_diff,
            "WinRate": _f(r.win_rate),
        }
        for r in rows
    ])


@router.get("/hitter-metrics")
async def hitter_metrics(season: int = None, db: Session = Depends(get_db)):
    season = season or current_season()
    rows = (
        db.query(HitterMetric)
        .filter(HitterMetric.season == season)
        .order_by(HitterMetric.rank)
        .all()
    )
    return _ok([
        {
            "Season": r.season,
            "Rank": r.rank,
            "Player": r.player,
            "Team": r.team,
            "PA": r.pa,
            "AVG": _f(r.avg),
            "OBP": _f(r.obp),
            "SLG": _f(r.slg),
            "HR": r.hr,
            "RBI": r.rbi,
            "XR": _f(r.xr),
            "WARProxy": _f(r.war_proxy),
            "OPS": _f(r.ops),
        }
        for r in rows
    ])


@router.get("/attendance")
async def attendance(season: int = None, db: Session = Depends(get_db)):
    season = season or current_season()
    rows = (
        db.query(Attendance)
        .filter(Attendance.season == season)
        .order_by(Attendance.month, Attendance.team)
        .all()
    )
    return _ok([
        {
            "Season": r.season,
            "Month": r.month,
            "Team": r.team,
            "Attendance": r.attendance,
            "UpdatedAt": r.updated_at,
        }
        for r in rows
    ])


@router.get("/game-time/team")
async def game_time_team(season: int = None, db: Session = Depends(get_db)):
    season = season or current_season()
    rows = db.query(GameTimeTeam).filter(GameTimeTeam.season == season).order_by(GameTimeTeam.team).all()
    return _ok([
        {
            "Season": r.season,
            "Team": r.team,
            "RegularInningTime": r.regular_inning_time,
            "RegularInningMinutes": r.regular_inning_minutes,
            "IncludeExtraTime": r.include_extra_time,
            "IncludeExtraMinutes": r.include_extra_minutes,
        }
        for r in rows
    ])


@router.get("/game-time/yearly")
async def game_time_yearly(db: Session = Depends(get_db)):
    rows = db.query(GameTimeYearly).order_by(GameTimeYearly.season).all()
    return _ok([
        {
            "Season": r.season,
            "Type": r.type,
            "AverageTime": r.average_time,
            "AverageMinutes": r.average_minutes,
        }
        for r in rows
    ])
