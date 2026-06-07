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
from zoneinfo import ZoneInfo

import crawl_kbo_schedule
import crawl_kbo_team_rank


def current_kbo_year() -> int:
    return datetime.now(ZoneInfo("Asia/Seoul")).year


def update_fast(year: int) -> None:
    print(f"[daily] updating team standings for {year}")
    crawl_kbo_team_rank.crawl(year)

    print(f"[daily] updating schedule/results for {year}")
    crawl_kbo_schedule.crawl(year)


def update_players(year: int) -> None:
    import crawl_kbo_hitter
    import crawl_kbo_pitcher

    print(f"[daily] updating hitter leaderboard for {year}")
    crawl_kbo_hitter.crawl(start=year, end=year, overwrite=True)

    print(f"[daily] updating pitcher leaderboard for {year}")
    crawl_kbo_pitcher.crawl(start=year, end=year, overwrite=True)


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
