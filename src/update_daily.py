"""
Daily KBO data update entrypoint.

Default mode refreshes the fast-changing home-dashboard data:
team standings and schedule/results. Use --players when you also want to
refresh hitter and pitcher leaderboards for the current season.

KBO 공식 사이트 요청 단계(순위·일정·관중·경기시간·선수 기록·등록선수)는 승인 전까지 건너뛴다
(kbo_access.py, 2026-10-24 결정). 기존 CSV 로 하는 가공 단계는 그대로 돈다.

로그 구분(grep 용):
  [skip:collect]  수집을 정책상 건너뜀(승인 전) — 오류 아님
  [skip:input]    입력 CSV 가 없어 가공을 건너뜀(예: 수집이 멈춘 채 새해) — 없는 자료는 만들지 않는다, 오류 아님
  [error]         실제 실패 — 0 이 아닌 종료 코드로 끝난다

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

import build_team_game_results
import kbo_access
import crawl_kbo_attendance
import crawl_kbo_game_time
import crawl_kbo_schedule
import crawl_kbo_team_rank


def _skip_kbo(what: str) -> None:
    print(f"[skip:collect] KBO {what}: 승인 전 자동 요청 비활성화 — 기존 CSV 유지 ({kbo_access.ENV}=1 로 허용)")


def _has_input(path: Path, what: str) -> bool:
    """가공 입력이 있으면 True. 없으면 [skip:input] 를 남기고 False — 다른 FileNotFoundError 는 숨기지 않는다."""
    if path.exists():
        return True
    print(f"[skip:input] {what}: 입력 없음 {path} — 만들지 않고 기존 산출물·DB 유지")
    return False


def current_kbo_year() -> int:
    """한국 시간 기준 현재 연도(=시즌)."""
    return datetime.now(ZoneInfo("Asia/Seoul")).year


def update_fast(year: int) -> None:
    """매일 바뀌는 핵심 데이터를 갱신한다(순위/일정·결과/관중/경기시간/타자지표)."""
    if kbo_access.allowed():
        print(f"[daily] updating team standings for {year}")
        team_rank = crawl_kbo_team_rank.crawl(year)
        crawl_kbo_team_rank.save_snapshot(team_rank, year)

        print(f"[daily] updating schedule/results for {year}")
        crawl_kbo_schedule.crawl(year)
    else:
        _skip_kbo("standings/schedule/attendance/game-time")

    if _has_input(build_team_game_results.RAW_DIR / f"kbo_schedule_{year}.csv", f"team game results {year}"):
        print(f"[daily] building team game result datasets for {year}")
        build_team_game_results.build(year)

    if kbo_access.allowed():
        print(f"[daily] updating attendance for {year}")
        crawl_kbo_attendance.crawl(year)

        print(f"[daily] updating average game time for {year}")
        crawl_kbo_game_time.crawl(year)

    _build_hitter_metrics(year)


def _build_hitter_metrics(year: int) -> None:
    import build_hitter_metrics

    if _has_input(build_hitter_metrics.RAW_DIR / f"kbo_{year}.csv", f"hitter metrics {year}"):
        print(f"[daily] building hitter metric dataset for {year}")
        build_hitter_metrics.build(year)


def update_players(year: int) -> None:
    """타자/투수 리더보드 + 등록선수 명단 + 타자 파생지표를 다시 만든다(--players)."""
    if kbo_access.allowed():
        import crawl_kbo_hitter
        import crawl_kbo_pitcher
        import crawl_kbo_players

        print(f"[daily] updating hitter leaderboard for {year}")
        crawl_kbo_hitter.crawl(start=year, end=year, overwrite=True)

        print(f"[daily] updating pitcher leaderboard for {year}")
        crawl_kbo_pitcher.crawl(start=year, end=year, overwrite=True)

        print("[daily] updating current registered player list")
        crawl_kbo_players.crawl()
    else:
        _skip_kbo("hitter/pitcher leaderboards, registered players")

    _build_hitter_metrics(year)


def update_pitch_zones(target_date: str | None = None) -> None:
    """특정 날짜(기본: 오늘 KST)의 네이버 투구 단위 데이터를 수집한다(--pitch-zones)."""
    import crawl_naver_pitch_zones
    import naver_access

    if not naver_access.allowed():
        naver_access.skip("pitch-zone crawl")
        return
    if target_date:
        day = crawl_naver_pitch_zones.parse_date(target_date)
    else:
        day = crawl_naver_pitch_zones.current_kst_date()
    print(f"[daily] updating Naver pitch-zone data for {day}")
    crawl_naver_pitch_zones.crawl(day)


def build_pitch_derived(year: int) -> None:
    """수집된 투구 원본에서 존/구종/볼카운트 파생 데이터셋을 다시 만든다.

    같은 원본을 세 번 읽지만 각각 1~5초라 나눠 두는 편이 낫다(한쪽이 깨져도
    다른 쪽 산출물은 남는다). 0행이면 csv_guard 가 덮어쓰기를 막고 예외를 던진다.
    """
    import build_count_metrics
    import build_pitch_arsenal
    import build_zone_metrics

    print(f"[daily] building hot/cold zone datasets for {year}")
    build_zone_metrics.build(year)

    print(f"[daily] building pitch arsenal datasets for {year}")
    build_pitch_arsenal.build(year)

    print(f"[daily] building ball/strike count dataset for {year}")
    build_count_metrics.build(year)


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
    """CLI 진입점: 옵션에 따라 fast/players/pitch-zones/db 단계를 선택 실행한다."""
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
    print(f"[daily] started {started:%Y-%m-%d %H:%M:%S %Z} season={args.year}")
    try:
        run(args)
    except Exception as exc:
        print(f"[error] daily update failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
    finished = datetime.now(ZoneInfo("Asia/Seoul"))
    print(f"[daily] finished {finished:%Y-%m-%d %H:%M:%S %Z}")


def run(args) -> None:
    update_fast(args.year)
    if args.registered_players and not kbo_access.allowed():
        _skip_kbo("registered players")
    elif args.registered_players:
        import crawl_kbo_players

        print("[daily] updating current registered player list")
        crawl_kbo_players.crawl()
    if args.players:
        update_players(args.year)
    if args.pitch_zones:
        update_pitch_zones(args.pitch_date)
        build_pitch_derived(args.year)
    if args.db:
        load_to_db()


if __name__ == "__main__":
    main()
