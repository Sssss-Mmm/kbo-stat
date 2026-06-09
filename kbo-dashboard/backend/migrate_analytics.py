"""
분석용 도메인(CSV 파생) 마이그레이션.

대상: team_rank_history, team_games, team_monthly, hitter_metrics,
attendance, game_time_team, game_time_yearly.

각 함수는 시즌 단위(delete-after)로 멱등성을 보장한다.
migrate.py main()에서 호출한다.
"""
import pandas as pd
from pathlib import Path
from sqlalchemy.orm import Session

from models import (
    Attendance,
    GameTimeTeam,
    GameTimeYearly,
    HitterMetric,
    TeamGame,
    TeamMonthly,
    TeamRankHistory,
)


def _i(value):
    """정수 변환 (빈값/NaN -> None)."""
    if pd.isna(value) or str(value).strip() == "":
        return None
    return int(float(value))


def _f(value):
    if pd.isna(value) or str(value).strip() == "":
        return None
    return float(value)


def _s(value):
    if pd.isna(value):
        return None
    return str(value).strip()


def _month(value):
    """'03' 또는 3 -> '03' 문자열."""
    i = _i(value)
    return f"{i:02d}" if i is not None else None


def _load(db: Session, model, rows, *, season=None):
    """기존 행을 (시즌 기준) 삭제하고 새 행을 일괄 삽입한다."""
    query = db.query(model)
    if season is not None and hasattr(model, "season"):
        query = query.filter(model.season == season)
    query.delete(synchronize_session=False)
    if rows:
        db.bulk_save_objects([model(**row) for row in rows])
    db.commit()


def migrate_team_rank_history(db: Session, raw_dir: Path, season: int):
    path = raw_dir / f"kbo_team_rank_history_{season}.csv"
    if not path.exists():
        return
    df = pd.read_csv(path)
    rows = [
        {
            "season": _i(r["Season"]),
            "date": _s(r["Date"]),
            "rank": _i(r["순위"]),
            "team": _s(r["팀명"]),
            "games": _i(r["경기"]),
            "wins": _i(r["승"]),
            "losses": _i(r["패"]),
            "draws": _i(r["무"]),
            "win_rate": _f(r["승률"]),
            "games_behind": _f(r["게임차"]),
            "last_10_games": _s(r["최근10경기"]),
            "streak": _s(r["연속"]),
            "home_record": _s(r["홈"]),
            "away_record": _s(r["방문"]),
        }
        for _, r in df.iterrows()
    ]
    _load(db, TeamRankHistory, rows, season=season)
    print(f"✅ {season}년 순위 히스토리 {len(rows)}행")


def migrate_team_games(db: Session, processed_dir: Path, season: int):
    path = processed_dir / f"kbo_team_games_{season}.csv"
    if not path.exists():
        return
    df = pd.read_csv(path)
    rows = [
        {
            "season": _i(r["Season"]),
            "date": _s(r["Date"]),
            "month": _month(r["Month"]),
            "game_id": _s(r["GameId"]),
            "team": _s(r["Team"]),
            "opponent": _s(r["Opponent"]),
            "home_away": _s(r["HomeAway"]),
            "ballpark": _s(r["Ballpark"]),
            "runs_for": _i(r["RunsFor"]),
            "runs_against": _i(r["RunsAgainst"]),
            "run_diff": _i(r["RunDiff"]),
            "result": _s(r["Result"]),
            "win": _i(r["Win"]),
            "loss": _i(r["Loss"]),
            "draw": _i(r["Draw"]),
        }
        for _, r in df.iterrows()
    ]
    _load(db, TeamGame, rows, season=season)
    print(f"✅ {season}년 팀 경기결과 {len(rows)}행")


def migrate_team_monthly(db: Session, processed_dir: Path, season: int):
    path = processed_dir / f"kbo_team_monthly_{season}.csv"
    if not path.exists():
        return
    df = pd.read_csv(path)
    rows = [
        {
            "season": _i(r["Season"]),
            "month": _month(r["Month"]),
            "team": _s(r["Team"]),
            "games": _i(r["Games"]),
            "wins": _i(r["Wins"]),
            "losses": _i(r["Losses"]),
            "draws": _i(r["Draws"]),
            "runs_for": _i(r["RunsFor"]),
            "runs_against": _i(r["RunsAgainst"]),
            "run_diff": _i(r["RunDiff"]),
            "win_rate": _f(r["WinRate"]),
        }
        for _, r in df.iterrows()
    ]
    _load(db, TeamMonthly, rows, season=season)
    print(f"✅ {season}년 팀 월간집계 {len(rows)}행")


def migrate_hitter_metrics(db: Session, processed_dir: Path, season: int):
    path = processed_dir / f"kbo_hitter_metrics_{season}.csv"
    if not path.exists():
        return
    df = pd.read_csv(path)
    rows = [
        {
            "season": _i(r["Season"]),
            "rank": _i(r["Rank"]),
            "player": _s(r["Player"]),
            "team": _s(r["Team"]),
            "pa": _i(r["PA"]),
            "avg": _f(r["AVG"]),
            "obp": _f(r["OBP"]),
            "slg": _f(r["SLG"]),
            "hr": _i(r["HR"]),
            "rbi": _i(r["RBI"]),
            "xr": _f(r["XR"]),
            "war_proxy": _f(r["WARProxy"]),
            "ops": _f(r["OPS"]),
        }
        for _, r in df.iterrows()
    ]
    _load(db, HitterMetric, rows, season=season)
    print(f"✅ {season}년 타자 지표 {len(rows)}행")


def migrate_attendance(db: Session, raw_dir: Path, season: int):
    rows = []
    for name in (f"kbo_attendance_{season}.csv", f"kbo_attendance_monthly_{season}.csv"):
        path = raw_dir / name
        if not path.exists():
            continue
        df = pd.read_csv(path)
        rows.extend(
            {
                "season": _i(r["Season"]),
                "month": _i(r["Month"]),
                "team": _s(r["Team"]),
                "attendance": _i(r["Attendance"]),
                "updated_at": _s(r["UpdatedAt"]),
            }
            for _, r in df.iterrows()
        )
    if rows:
        _load(db, Attendance, rows, season=season)
        print(f"✅ {season}년 관중 {len(rows)}행")


def migrate_game_time_team(db: Session, raw_dir: Path, season: int):
    path = raw_dir / f"kbo_game_time_team_{season}.csv"
    if not path.exists():
        return
    df = pd.read_csv(path)
    rows = [
        {
            "season": _i(r["Season"]),
            "team": _s(r["Team"]),
            "regular_inning_time": _s(r["RegularInningTime"]),
            "regular_inning_minutes": _i(r["RegularInningMinutes"]),
            "include_extra_time": _s(r["IncludeExtraTime"]),
            "include_extra_minutes": _i(r["IncludeExtraMinutes"]),
        }
        for _, r in df.iterrows()
    ]
    _load(db, GameTimeTeam, rows, season=season)
    print(f"✅ {season}년 팀 경기시간 {len(rows)}행")


def migrate_game_time_yearly(db: Session, raw_dir: Path):
    """연도 전체 단일 파일 -> 테이블 전체 교체."""
    path = raw_dir / "kbo_game_time_yearly.csv"
    if not path.exists():
        return
    df = pd.read_csv(path)
    rows = [
        {
            "season": _i(r["Season"]),
            "type": _s(r["Type"]),
            "average_time": _s(r["AverageTime"]),
            "average_minutes": _i(r["AverageMinutes"]),
        }
        for _, r in df.iterrows()
    ]
    _load(db, GameTimeYearly, rows)  # season=None -> 전체 교체
    print(f"✅ 연도별 경기시간 {len(rows)}행")


def migrate_analytics(db: Session, raw_dir: Path, processed_dir: Path, seasons) -> None:
    for season in seasons:
        migrate_team_rank_history(db, raw_dir, season)
        migrate_team_games(db, processed_dir, season)
        migrate_team_monthly(db, processed_dir, season)
        migrate_hitter_metrics(db, processed_dir, season)
        migrate_attendance(db, raw_dir, season)
        migrate_game_time_team(db, raw_dir, season)
    migrate_game_time_yearly(db, raw_dir)
