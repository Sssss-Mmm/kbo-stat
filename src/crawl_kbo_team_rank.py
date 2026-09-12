"""
KBO official team standings crawler.

The KBO team-rank page exposes the current season as a regular HTML table.
This script saves that table as data/raw/kbo_official/kbo_team_rank_<year>.csv.

Usage:
    python src/crawl_kbo_team_rank.py --year 2026
"""

import argparse
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from bs4 import BeautifulSoup

import csv_guard

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "kbo_official"
RAW_DIR.mkdir(parents=True, exist_ok=True)

TEAM_RANK_URL = "https://www.koreabaseball.com/Record/TeamRank/TeamRank.aspx"
DAILY_RANK_URL = "https://www.koreabaseball.com/Record/TeamRank/TeamRankDaily.aspx"
# 두 페이지 모두 ASP.NET 포스트백이라 컨트롤 이름에 이 접두사가 붙는다.
CTL = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$"
# 과거 조회 요청 사이 대기(초). 시즌/날짜를 연속으로 도는 백필용(NFR-09).
PAUSE_SECONDS = 1.2

# 양대리그(드림·매직) 시즌. 순위 페이지가 **한 리그 4팀만** 보여주고 나머지
# 리그는 별도 컨트롤이 필요해 시즌 전체 순위를 한 번에 받을 수 없다.
# ponytail: 45시즌 중 2개라 건너뛴다. 필요해지면 리그 선택 포스트백을 추가할 것.
DUAL_LEAGUE_SEASONS = {1999, 2000}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.koreabaseball.com/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def _parse_table(html: str) -> pd.DataFrame:
    """순위 페이지 HTML 의 첫 테이블(tData)을 헤더+행으로 DataFrame 변환."""
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", class_="tData") or soup.find("table")
    if not table:
        return pd.DataFrame()

    rows = table.find_all("tr")
    if len(rows) < 2:
        return pd.DataFrame()

    cols = [cell.get_text(strip=True) for cell in rows[0].find_all(["th", "td"])]
    data = [
        [cell.get_text(strip=True) for cell in row.find_all(["th", "td"])]
        for row in rows[1:]
        if row.find_all(["th", "td"])
    ]
    return pd.DataFrame(data, columns=cols)


def fetch_current() -> pd.DataFrame:
    """KBO 순위 페이지를 받아 현재 시즌 순위 테이블을 반환한다."""
    response = requests.get(TEAM_RANK_URL, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return _parse_table(response.text)




def _hidden(soup: BeautifulSoup) -> dict[str, str]:
    """폼의 숨은 입력값 전부.

    __VIEWSTATE 세 개만 보내면 포스트백이 조용히 무시되고 **현재 시즌 표가
    그대로 돌아온다** (에러가 아니라 정상 200 이라 더 위험하다). hfSearchDate
    같은 페이지별 숨은 필드까지 같이 보내야 날짜·연도 선택이 먹는다.
    """
    return {
        tag["name"]: tag.get("value", "")
        for tag in soup.find_all("input", type="hidden")
        if tag.get("name")
    }


def _post(session: requests.Session, url: str, soup: BeautifulSoup, fields: dict) -> BeautifulSoup:
    """숨은 입력값 + 지정 필드로 포스트백하고 새 페이지를 돌려준다."""
    form = {**_hidden(soup), "__EVENTTARGET": "", "__EVENTARGUMENT": "", **fields}
    response = session.post(url, data=form, timeout=20)
    response.raise_for_status()
    return BeautifulSoup(response.text, "lxml")


def _new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def available_seasons(session: requests.Session) -> list[int]:
    """순위 페이지 연도 드롭다운이 제공하는 시즌 목록(2026~1982)."""
    soup = BeautifulSoup(session.get(TEAM_RANK_URL, timeout=20).text, "lxml")
    select = soup.find("select", attrs={"name": lambda v: v and "ddlYear" in v})
    if not select:
        raise RuntimeError("연도 드롭다운을 찾지 못했다 — 페이지 구조가 바뀌었다")
    return [int(o["value"]) for o in select.find_all("option") if o.get("value", "").isdigit()]


def fetch_season(session: requests.Session, year: int) -> pd.DataFrame:
    """그 시즌 **최종** 순위표. 연도 드롭다운 포스트백으로 받는다."""
    soup = BeautifulSoup(session.get(TEAM_RANK_URL, timeout=20).text, "lxml")
    name = CTL + "ddlYear"
    soup = _post(session, TEAM_RANK_URL, soup, {"__EVENTTARGET": name, name: str(year)})
    df = _parse_table(str(soup))
    if df.empty:
        raise RuntimeError(f"{year} 순위표가 비었다")
    df.insert(0, "Season", year)
    return df


def fetch_daily(session: requests.Session, day: date) -> pd.DataFrame:
    """특정 **날짜** 시점의 순위표(TeamRankDaily).

    이 엔드포인트 덕분에 놓친 일일 스냅샷을 나중에 복구할 수 있다. 하루 거르면
    영영 잃는다고 알려져 있었지만(scripts/probe_kbo_reachable.py 주석) 사실이
    아니다 — 2026-04-15, 2025-08-15 로 확인했다.
    """
    stamp = day.strftime("%Y%m%d")
    soup = BeautifulSoup(session.get(DAILY_RANK_URL, timeout=20).text, "lxml")
    soup = _post(session, DAILY_RANK_URL, soup, {
        CTL + "hfSearchYear": str(day.year),
        CTL + "hfSearchDate": stamp,
        CTL + "txtCanlendar": stamp,
        CTL + "btnCalendarSelect": "",
    })
    # 포스트백이 무시되면 오늘 표가 돌아온다. 페이지가 우리가 요청한 날짜를
    # 들고 있는지 확인하지 않으면 엉뚱한 순위를 그 날짜로 저장하게 된다.
    echoed = soup.find("input", attrs={"name": CTL + "hfSearchDate"})
    if not echoed or echoed.get("value", "").strip() != stamp:
        raise RuntimeError(
            f"{day} 조회가 반영되지 않았다 (페이지 날짜="
            f"{echoed.get('value') if echoed else '없음'}) — 포스트백 필드 확인 필요"
        )
    df = _parse_table(str(soup))
    if df.empty:
        return df
    df.insert(0, "Season", day.year)
    df.insert(1, "Date", day.isoformat())
    return df


def save_snapshot(df: pd.DataFrame, year: int, snapshot_date: str | None = None) -> None:
    """하루치 순위표를 스냅샷으로 저장하고 연간 history CSV 에 누적한다.

    history 는 (날짜+팀) 기준으로 같은 날 기존 행을 지우고 다시 넣어, 몇 번을
    돌려도 중복 없이 최신 스냅샷만 남도록 멱등하게 갱신한다.
    """
    snapshot_date = snapshot_date or datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    history_path = RAW_DIR / f"kbo_team_rank_history_{year}.csv"
    snapshot_dir = RAW_DIR / "team_rank_snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    snapshot = df.copy()
    if "Date" in snapshot.columns:
        snapshot = snapshot.drop(columns=["Date"])
    snapshot.insert(1, "Date", snapshot_date)
    # 0행 스냅샷은 순위 페이지 파싱이 깨진 것 — history 를 오염시키기 전에 멈춘다.
    csv_guard.save_csv(
        snapshot, snapshot_dir / f"kbo_team_rank_{snapshot_date}.csv", prefix="[rank]"
    )

    if history_path.exists():
        history = pd.read_csv(history_path, encoding="utf-8-sig")
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
    # 검사를 켠 채로 둔다. history 는 append 로만 늘어나 행 수 급감(V-08)에
    # 걸릴 일이 없고, 팀명·승패무 합 검사(_check_team_rank_history)는 백필에서도
    # 그대로 값어치를 한다 — 과거 날짜를 잘못 파싱해 history 를 오염시키는 걸 막는다.
    csv_guard.save_csv(
        history, history_path, prefix="[rank]", extra=f"snapshot={snapshot_date}"
    )


def backfill_seasons(start: int, end: int) -> None:
    """시즌 최종 순위표를 연도 범위만큼 받아 kbo_team_rank_{year}.csv 로 저장한다."""
    session = _new_session()
    offered = set(available_seasons(session))
    for year in range(start, end + 1):
        if year not in offered:
            print(f"[rank] skip {year} — 드롭다운에 없는 시즌")
            continue
        if year in DUAL_LEAGUE_SEASONS:
            print(f"[rank] skip {year} — 양대리그 시즌(한 리그만 노출돼 전체를 못 받는다)")
            continue
        df = fetch_season(session, year)
        csv_guard.save_csv(df, RAW_DIR / f"kbo_team_rank_{year}.csv", prefix="[rank]")
        time.sleep(PAUSE_SECONDS)


def backfill_daily(start: date, end: date, skip_existing: bool = True) -> None:
    """일자별 순위 스냅샷을 날짜 범위만큼 받아 history 에 누적한다.

    이미 history 에 있는 날짜는 요청하지 않는다(--no-skip-existing 으로 강제 갱신).
    경기가 없던 날은 표가 비어 오므로 조용히 건너뛴다.
    """
    session = _new_session()
    have: set[str] = set()
    history_path = RAW_DIR / f"kbo_team_rank_history_{start.year}.csv"
    if skip_existing and history_path.exists():
        have = set(pd.read_csv(history_path, encoding="utf-8-sig")["Date"].astype(str))

    day = start
    while day <= end:
        if day.isoformat() in have:
            day += timedelta(days=1)
            continue
        df = fetch_daily(session, day)
        if df.empty:
            print(f"[rank] {day} 순위표 없음 — 건너뜀")
        else:
            save_snapshot(df, day.year, day.isoformat())
        time.sleep(PAUSE_SECONDS)
        day += timedelta(days=1)


def crawl(year: int) -> pd.DataFrame:
    """현재 순위표를 받아 Season 컬럼을 붙여 CSV 로 저장한다."""
    df = fetch_current()
    if df.empty:
        raise RuntimeError("No team standings table found.")

    df.insert(0, "Season", year)
    out = RAW_DIR / f"kbo_team_rank_{year}.csv"
    csv_guard.save_csv(df, out)
    print(f"saved {out.name} teams={len(df)}")
    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument(
        "--seasons",
        nargs=2,
        type=int,
        metavar=("START", "END"),
        help="시즌 최종 순위표 백필 (예: --seasons 1982 2025)",
    )
    parser.add_argument(
        "--daily",
        nargs=2,
        metavar=("FROM", "TO"),
        help="일자별 순위 스냅샷 백필 (예: --daily 2026-03-28 2026-09-12)",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="--daily 에서 이미 있는 날짜도 다시 받는다",
    )
    args = parser.parse_args()

    if args.seasons:
        backfill_seasons(*args.seasons)
    elif args.daily:
        parse = lambda v: datetime.strptime(v, "%Y-%m-%d").date()  # noqa: E731
        backfill_daily(parse(args.daily[0]), parse(args.daily[1]),
                       skip_existing=not args.no_skip_existing)
    else:
        crawl(args.year)
