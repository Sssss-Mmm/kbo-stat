"""
KBO official pitcher leaderboard crawler.

Fetches the basic pitcher table and both pitcher detail tables from
koreabaseball.com, then merges them into one per-season CSV.

Usage:
    python src/crawl_kbo_pitcher.py
    python src/crawl_kbo_pitcher.py --start 2011 --end 2011 --overwrite
"""

import argparse
import random
import re
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "kbo_official"
RAW_DIR.mkdir(parents=True, exist_ok=True)

BASIC_URL = "https://www.koreabaseball.com/Record/Player/PitcherBasic/BasicOld.aspx"
DETAIL_URLS = [
    "https://www.koreabaseball.com/Record/Player/PitcherBasic/Detail1.aspx",
    "https://www.koreabaseball.com/Record/Player/PitcherBasic/Detail2.aspx",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.koreabaseball.com/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

F_SEASON = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ddlSeason$ddlSeason"
F_SERIES = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ddlSeries$ddlSeries"
F_TEAM = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ddlTeam$ddlTeam"
F_POS = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ddlPos$ddlPos"
F_PAGE = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$hfPage"
F_SORT = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$hfOrderByCol"
F_ORDER = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$hfOrderBy"
BTN_PAGE1 = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ucPager$btnNo1"


def _viewstate(soup: BeautifulSoup) -> dict[str, str]:
    out = {}
    for name in [
        "__VIEWSTATE",
        "__VIEWSTATEGENERATOR",
        "__EVENTVALIDATION",
        "__EVENTTARGET",
        "__EVENTARGUMENT",
        "__LASTFOCUS",
    ]:
        tag = soup.find("input", {"name": name})
        out[name] = tag["value"] if tag else ""
    return out


def _parse_table(soup: BeautifulSoup) -> pd.DataFrame | None:
    tbl = soup.find("table", class_="tData") or soup.find("table")
    if not tbl:
        return None

    rows = tbl.find_all("tr")
    if len(rows) < 2:
        return None

    cols = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
    data = [
        [td.get_text(strip=True) for td in row.find_all(["th", "td"])]
        for row in rows[1:]
        if row.find_all(["th", "td"])
    ]
    return pd.DataFrame(data, columns=cols) if data else None


def _total_pages(soup: BeautifulSoup) -> int:
    nums = [
        int(m.group(1))
        for a in soup.find_all("a", id=True)
        if (m := re.search(r"btnNo(\d+)", a["id"]))
    ]
    return max(nums) if nums else 1


def _fetch_table(
    session: requests.Session,
    year: int,
    url: str,
    sort_col: str = "ERA_RT",
    sort_order: str = "ASC",
) -> pd.DataFrame:
    response = session.get(url, timeout=20)
    response.raise_for_status()
    viewstate = _viewstate(BeautifulSoup(response.text, "lxml"))

    def form(event_target: str, page: str = "1") -> dict[str, str]:
        return {
            **viewstate,
            "__EVENTTARGET": event_target,
            "__EVENTARGUMENT": "",
            F_SEASON: str(year),
            F_SERIES: "0",
            F_TEAM: "",
            F_POS: "",
            F_PAGE: page,
            F_SORT: sort_col,
            F_ORDER: sort_order,
        }

    response = session.post(url, data=form(F_SEASON), timeout=20)
    response.raise_for_status()
    viewstate = _viewstate(BeautifulSoup(response.text, "lxml"))

    response = session.post(url, data=form(BTN_PAGE1), timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")

    frames = []
    first_page = _parse_table(soup)
    if first_page is not None:
        frames.append(first_page)

    total = _total_pages(soup)
    viewstate = _viewstate(soup)

    for page in range(2, total + 1):
        event_target = (
            "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents"
            f"$ucPager$btnNo{page}"
        )
        response = session.post(url, data=form(event_target, str(page)), timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        page_df = _parse_table(soup)
        if page_df is not None:
            frames.append(page_df)
        viewstate = _viewstate(soup)
        time.sleep(random.uniform(0.6, 1.2))

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df.insert(0, "Season", year)
    return df


def _merge_detail(base: pd.DataFrame, detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return base

    merge_keys = ["Season", "선수명", "팀명"]
    missing = [col for col in merge_keys if col not in base.columns or col not in detail.columns]
    if missing:
        raise ValueError(f"Cannot merge detail stats; missing columns: {missing}")

    duplicate_cols = [col for col in ["순위", "ERA"] if col in detail.columns]
    detail = detail.drop(columns=duplicate_cols)
    overlapping = [col for col in detail.columns if col in base.columns and col not in merge_keys]
    if overlapping:
        detail = detail.rename(columns={col: f"{col}_detail" for col in overlapping})
    return base.merge(detail, on=merge_keys, how="left")


def fetch_year(session: requests.Session, year: int) -> pd.DataFrame:
    df = _fetch_table(session, year, BASIC_URL)
    if df.empty:
        return df

    for url in DETAIL_URLS:
        detail = _fetch_table(session, year, url)
        df = _merge_detail(df, detail)
    return df


def crawl(start: int = 2008, end: int = 2026, overwrite: bool = False) -> None:
    session = requests.Session()
    session.headers.update(HEADERS)

    detail_cols = [
        "GS",
        "Wgs",
        "Wgr",
        "GF",
        "SVO",
        "TS",
        "GDP",
        "GO",
        "AO",
        "GO/AO",
        "BABIP",
        "P/G",
        "P/IP",
        "K/9",
        "BB/9",
        "K/BB",
        "OBP",
        "SLG",
        "OPS",
    ]

    for year in range(start, end + 1):
        out = RAW_DIR / f"kbo_pitcher_{year}.csv"
        if out.exists() and not overwrite:
            print(f"  skip  {out.name}")
            continue

        try:
            df = fetch_year(session, year)
            if df.empty:
                print(f"  empty {year}")
            else:
                df.to_csv(out, index=False, encoding="utf-8-sig")
                found_detail_cols = [col for col in detail_cols if col in df.columns]
                print(
                    f"  saved {out.name}  players={len(df)} "
                    f"cols={len(df.columns)} detail_cols={len(found_detail_cols)}"
                )
        except Exception as exc:
            print(f"  ERROR {year}: {exc}")
        time.sleep(random.uniform(1.5, 2.5))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2008)
    parser.add_argument("--end", type=int, default=2026)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace existing season CSVs instead of skipping them",
    )
    args = parser.parse_args()

    print(f"Crawling KBO pitcher stats: {args.start}-{args.end}")
    crawl(args.start, args.end, args.overwrite)
    print("Done.")
