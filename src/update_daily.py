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
    return datetime.now(ZoneInfo("Asia/Seoul")).year


def update_fast(year: int) -> None:
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

    print(f"[daily] updating hitter leaderboard for {year}")
    crawl_kbo_hitter.crawl(start=year, end=year, overwrite=True)

    print(f"[daily] updating pitcher leaderboard for {year}")
    crawl_kbo_pitcher.crawl(start=year, end=year, overwrite=True)

    import build_hitter_metrics

    print(f"[daily] rebuilding hitter metric dataset for {year}")
    build_hitter_metrics.build(year)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=current_kbo_year())
    parser.add_argument(
        "--players",
        action="store_true",
        help="also refresh current-season hitter and pitcher CSVs",
    )
    args = parser.parse_args()

    started = datetime.now(ZoneInfo("Asia/Seoul"))
    print(f"[daily] started {started:%Y-%m-%d %H:%M:%S %Z}")
    update_fast(args.year)
    if args.players:
        update_players(args.year)
    finished = datetime.now(ZoneInfo("Asia/Seoul"))
    print(f"[daily] finished {finished:%Y-%m-%d %H:%M:%S %Z}")


if __name__ == "__main__":
    main()
