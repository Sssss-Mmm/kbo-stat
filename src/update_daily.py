"""
Daily KBO data update entrypoint.

Default mode refreshes the fast-changing home-dashboard data:
team standings and schedule/results. Use --players when you also want to
refresh hitter and pitcher leaderboards for the current season.

Usage:
    python src/update_daily.py
    python src/update_daily.py --year 2026 --players
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

import build_team_game_results
import crawl_kbo_attendance
import crawl_kbo_game_time
import crawl_kbo_schedule
import crawl_kbo_team_rank


RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "kbo_official"


def current_kbo_year() -> int:
    """한국 시간 기준 현재 연도(=시즌)."""
    return datetime.now(ZoneInfo("Asia/Seoul")).year


def update_fast(year: int) -> None:
    """매일 바뀌는 핵심 데이터를 갱신한다(순위/일정·결과/관중/경기시간/타자지표)."""
    print(f"[daily] updating team standings for {year}")
    team_rank = crawl_kbo_team_rank.crawl(year)
    save_team_rank_snapshot(team_rank, year)

    print(f"[daily] updating schedule/results for {year}")
    crawl_kbo_schedule.crawl(year)

    print(f"[daily] building team game result datasets for {year}")
    build_team_game_results.build(year)

    print(f"[daily] updating attendance for {year}")
    crawl_kbo_attendance.crawl(year)

    print(f"[daily] updating average game time for {year}")
    crawl_kbo_game_time.crawl(year)

    try:
        import build_hitter_metrics

        print(f"[daily] building hitter metric dataset for {year}")
        build_hitter_metrics.build(year)
    except FileNotFoundError as exc:
        print(f"[daily] skip hitter metrics: {exc}")


def save_team_rank_snapshot(df: pd.DataFrame, year: int) -> None:
    snapshot_date = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    history_path = RAW_DIR / f"kbo_team_rank_history_{year}.csv"
    snapshot_dir = RAW_DIR / "team_rank_snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    snapshot = df.copy()
    snapshot.insert(1, "Date", snapshot_date)
    snapshot_path = snapshot_dir / f"kbo_team_rank_{snapshot_date}.csv"
    snapshot.to_csv(snapshot_path, index=False, encoding="utf-8-sig")

    if history_path.exists():
        history = pd.read_csv(history_path)
        history = history[
            ~(
                (history["Date"].astype(str) == snapshot_date)
                & (history["팀명"].isin(snapshot["팀명"]))
            )
        ]
        history = pd.concat([history, snapshot], ignore_index=True)
    else:
        history = snapshot

    history = history.sort_values(["Date", "순위", "팀명"])
    history.to_csv(history_path, index=False, encoding="utf-8-sig")
    print(
        f"[daily] saved team rank snapshot {snapshot_path.name} "
        f"history_rows={len(history)}"
    )


def update_players(year: int) -> None:
    import crawl_kbo_hitter
    import crawl_kbo_pitcher
    import crawl_kbo_players

    print(f"[daily] updating hitter leaderboard for {year}")
    crawl_kbo_hitter.crawl(start=year, end=year, overwrite=True)

    print(f"[daily] updating pitcher leaderboard for {year}")
    crawl_kbo_pitcher.crawl(start=year, end=year, overwrite=True)

    print("[daily] updating current registered player list")
    crawl_kbo_players.crawl()

    import build_hitter_metrics

    print(f"[daily] rebuilding hitter metric dataset for {year}")
    build_hitter_metrics.build(year)


def update_pitch_zones(target_date: str | None = None) -> None:
    import crawl_naver_pitch_zones

    if target_date:
        day = crawl_naver_pitch_zones.parse_date(target_date)
    else:
        day = crawl_naver_pitch_zones.current_kst_date()
    print(f"[daily] updating Naver pitch-zone data for {day}")
    crawl_naver_pitch_zones.crawl(day)


def load_to_db() -> None:
    """갱신된 CSV를 PostgreSQL로 적재한다 (백엔드 migrate.py 실행).

    migrate.py는 SQLAlchemy 등 백엔드 의존성을 쓰므로 백엔드 venv의
    파이썬으로 실행한다. 없으면 현재 인터프리터로 폴백한다.
    """
    backend = Path(__file__).parent.parent / "kbo-dashboard" / "backend"
    venv_python = backend / "venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else sys.executable

    print(f"[daily] loading CSV into PostgreSQL via {Path(python).name}")
    subprocess.run([python, "migrate.py"], cwd=str(backend), check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=current_kbo_year())
    parser.add_argument(
        "--players",
        action="store_true",
        help="also refresh current-season hitter, pitcher, and registered-player CSVs",
    )
    parser.add_argument(
        "--registered-players",
        action="store_true",
        help="refresh only the current KBO registered-player list",
    )
    parser.add_argument(
        "--pitch-zones",
        action="store_true",
        help="also collect Naver Sports pitch-level relay data for one date",
    )
    parser.add_argument(
        "--pitch-date",
        default=None,
        help="YYYY-MM-DD date for --pitch-zones; defaults to today in KST",
    )
    parser.add_argument(
        "--db",
        action="store_true",
        help="load refreshed CSVs into PostgreSQL after the update",
    )
    args = parser.parse_args()

    started = datetime.now(ZoneInfo("Asia/Seoul"))
    print(f"[daily] started {started:%Y-%m-%d %H:%M:%S %Z}")
    update_fast(args.year)
    if args.registered_players:
        import crawl_kbo_players

        print("[daily] updating current registered player list")
        crawl_kbo_players.crawl()
    if args.players:
        update_players(args.year)
    if args.pitch_zones:
        update_pitch_zones(args.pitch_date)
    if args.db:
        load_to_db()
    finished = datetime.now(ZoneInfo("Asia/Seoul"))
    print(f"[daily] finished {finished:%Y-%m-%d %H:%M:%S %Z}")


if __name__ == "__main__":
    main()
