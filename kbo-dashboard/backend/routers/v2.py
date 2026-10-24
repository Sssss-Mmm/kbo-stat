"""/api/v2 — 출처·수집 시각·검증 상태를 함께 주는 통계 API (P2-A). 조회 로직은 services/v2_service.py.

v1 라우터·public 테이블과 독립이다. DB 연결 실패는 main.py 의 OperationalError 처리(503)를 그대로 쓰고,
v2 스키마가 아직 없으면(적재 전) 503 으로 알린다 — 빈 결과로 조용히 넘어가지 않는다.
"""
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.exc import ProgrammingError

from database import engine
from security import CURRENT_YEAR, Season
from services import season_service as ss
from services import team_player_service as tp
from services import v2_service as v2

router = APIRouter(prefix="/v2")

GameId = Annotated[str, Path(pattern=r"^\d{8}[A-Z]{4}\d$", description="KBO GameId 13자, 예: 20250719HHKT0")]
PlayerId = Annotated[int, Path(ge=1, le=10_000_000)]
Role = Literal["pitcher", "batter"]
OptionalSeason = Annotated[int | None, Query(ge=1982, le=CURRENT_YEAR)]


def connection():
    with engine.connect() as conn:
        try:
            yield conn
        except ProgrammingError as exc:  # 스키마·뷰가 없는 DB(migrate_records.py 적재 전)
            raise HTTPException(503, "v2 records schema not loaded") from exc


def as_of_param(as_of: Annotated[datetime | None, Query(description="데이터 확보 시각 기준(ISO 8601, 시간대 포함)")] = None):
    if as_of is not None and as_of.tzinfo is None:
        raise HTTPException(422, "as_of must include a timezone offset, e.g. 2026-10-24T00:00:00+09:00")
    return as_of


def through_param(through_date: Annotated[date | None, Query(description="경기 날짜 기준 집계 마지막 날")] = None):
    return through_date


def _found(result, what: str):
    if result is None:
        raise HTTPException(404, f"{what} not found")
    return result


@router.get("/games/{game_id}/box")
def game_box(game_id: GameId, as_of=Depends(as_of_param), conn=Depends(connection)):
    return _found(v2.game_box(conn, game_id, as_of), "game")


@router.get("/players/{player_id}/games")
def player_games(player_id: PlayerId, season: Season, role: Role | None = None,
                 date_from: date | None = None, date_to: date | None = None,
                 limit: Annotated[int, Query(ge=1, le=200)] = 50, offset: Annotated[int, Query(ge=0)] = 0,
                 sort: Literal["date", "-date"] = "date", as_of=Depends(as_of_param), conn=Depends(connection)):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from must be on or before date_to")
    return _found(v2.player_games(conn, player_id, season, role, date_from, date_to, as_of, limit, offset, sort),
                  "player")


@router.get("/players/{player_id}/season")
def player_season(player_id: PlayerId, season: Season, role: Role | None = None,
                  through=Depends(through_param), as_of=Depends(as_of_param), conn=Depends(connection)):
    return _found(v2.player_season(conn, player_id, season, role, through, as_of), "player")


@router.get("/leaders")
def leaders(season: Season, role: Role, stat: str, basis: Literal["official", "calc"] = "official",
            min_outs: Annotated[int, Query(ge=0, le=10_000)] = 0, min_ab: Annotated[int, Query(ge=0, le=10_000)] = 0,
            qualified: bool = False, limit: Annotated[int, Query(ge=1, le=100)] = 20,
            offset: Annotated[int, Query(ge=0)] = 0, through=Depends(through_param), as_of=Depends(as_of_param),
            conn=Depends(connection)):
    allowed = v2.LEADER_STATS[(role, basis)]
    if stat not in allowed:
        raise HTTPException(422, f"stat must be one of {sorted(allowed)} for role={role} basis={basis}")
    if qualified and basis == "calc":
        raise HTTPException(422, "qualified=true needs a team per player; supported with basis=official only")
    if qualified and role == "batter":
        # 규정타석은 타석(PA) 기준인데 외부 기록(네이버 박스스코어)에는 타석 수가 없다 — 짐작하지 않는다.
        raise HTTPException(422, "qualified=true is only supported for pitchers; use min_ab for batters")
    return v2.leaders(conn, season, role, stat, basis, min_outs, min_ab, qualified, through, as_of, limit, offset)


@router.get("/data-quality")
def data_quality(season: Season, as_of=Depends(as_of_param), conn=Depends(connection)):
    return v2.data_quality(conn, season, as_of)


# ---------- P2-C: 시즌·일정·순위·홈 (KBO 수집분 — 외부 공개 금지, meta.publication) ----------

@router.get("/seasons")
def seasons(conn=Depends(connection)):
    return ss.seasons(conn)


@router.get("/schedule")
def schedule(day: Annotated[date | None, Query(alias="date")] = None, season: OptionalSeason = None,
             month: Annotated[int | None, Query(ge=1, le=12)] = None, conn=Depends(connection)):
    if day is None and (season is None or month is None):
        raise HTTPException(422, "give date=YYYY-MM-DD, or season and month")
    if day is not None and (season is not None or month is not None):
        raise HTTPException(422, "date cannot be combined with season/month")
    return ss.schedule(conn, day, season, month)


@router.get("/standings")
def standings(season: Season, through=Depends(through_param), conn=Depends(connection)):
    return _found(ss.standings(conn, season, through), "season schedule")


@router.get("/home")
def home(season: OptionalSeason = None, conn=Depends(connection)):
    return _found(ss.home(conn, season), "season schedule")


# P2-D — 팀 상세 · 선수 검색 · 선수 시즌별 기록(services/team_player_service.py)
TeamName = Annotated[str, Path(min_length=1, max_length=20)]


@router.get("/teams/{team}")
def team_detail(team: TeamName, season: Season, conn=Depends(connection)):
    return _found(tp.team_detail(conn, team, season), "team season")


@router.get("/players/search")
def player_search(q: Annotated[str | None, Query(max_length=30)] = None, team: Annotated[str | None, Query(max_length=20)] = None,
                  season: OptionalSeason = None, role: Role | None = None):
    if not (q and q.strip()) and not team:
        raise HTTPException(422, "give q (player name) or team")
    return tp.search(q, team, season, role)


@router.get("/players/{player_id}/profile")
def player_profile(player_id: PlayerId):
    return _found(tp.profile(player_id), "player")
