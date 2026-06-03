"""
KBO 공식 사이트(koreabaseball.com) 투수 스탯 크롤러.

Usage:
    python crawl_kbo_pitcher.py                   # 2008-2025
    python crawl_kbo_pitcher.py --start 2015 --end 2024
"""

import re
import time
import random
import argparse
import requests
import pandas as pd
from bs4 import BeautifulSoup
from pathlib import Path

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "kbo_official"
RAW_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://www.koreabaseball.com/Record/Player/PitcherBasic/BasicOld.aspx"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.koreabaseball.com/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

F_SEASON  = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ddlSeason$ddlSeason"
F_SERIES  = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ddlSeries$ddlSeries"
F_TEAM    = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ddlTeam$ddlTeam"
F_POS     = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ddlPos$ddlPos"
F_PAGE    = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$hfPage"
F_SORT    = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$hfOrderByCol"
F_ORDER   = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$hfOrderBy"
BTN_PAGE1 = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ucPager$btnNo1"


def _viewstate(soup: BeautifulSoup) -> dict:
    out = {}
    for name in ["__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION",
                 "__EVENTTARGET", "__EVENTARGUMENT", "__LASTFOCUS"]:
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
    data = [[td.get_text(strip=True) for td in row.find_all(["th", "td"])]
            for row in rows[1:] if row.find_all(["th", "td"])]
    return pd.DataFrame(data, columns=cols) if data else None


def _total_pages(soup: BeautifulSoup) -> int:
    nums = [int(m.group(1)) for a in soup.find_all("a", id=True)
            if (m := re.search(r"btnNo(\d+)", a["id"]))]
    return max(nums) if nums else 1


def fetch_year(session: requests.Session, year: int) -> pd.DataFrame:
    # 1단계: GET으로 초기 ViewState 획득
    r0 = session.get(BASE_URL, timeout=20)
    r0.raise_for_status()
    vs = _viewstate(BeautifulSoup(r0.text, "lxml"))

    def _form(event_target, page="1"):
        return {**vs, "__EVENTTARGET": event_target, "__EVENTARGUMENT": "",
                F_SEASON: str(year), F_SERIES: "0", F_TEAM: "", F_POS: "",
                F_PAGE: page, F_SORT: "ERA_RT", F_ORDER: "ASC"}

    # 2단계: 년도 변경 POST → ViewState 갱신
    r1 = session.post(BASE_URL, data=_form(F_SEASON), timeout=20)
    r1.raise_for_status()
    vs = _viewstate(BeautifulSoup(r1.text, "lxml"))

    # 3단계: 1페이지 버튼 POST → 올바른 년도 데이터 로드
    r2 = session.post(BASE_URL, data=_form(BTN_PAGE1), timeout=20)
    r2.raise_for_status()
    soup2 = BeautifulSoup(r2.text, "lxml")

    frames = []
    df1 = _parse_table(soup2)
    if df1 is not None:
        frames.append(df1)

    total = _total_pages(soup2)
    vs    = _viewstate(soup2)

    # 4단계: 2페이지부터 페이지네이션
    for page in range(2, total + 1):
        event_target = (
            "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents"
            f"$ucPager$btnNo{page}"
        )
        rp = session.post(BASE_URL, data=_form(event_target, str(page)), timeout=20)
        rp.raise_for_status()
        soup_p = BeautifulSoup(rp.text, "lxml")
        dfp = _parse_table(soup_p)
        if dfp is not None:
            frames.append(dfp)
        vs = _viewstate(soup_p)
        time.sleep(random.uniform(0.6, 1.2))

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df.insert(0, "Season", year)
    return df


def crawl(start: int = 2008, end: int = 2025):
    session = requests.Session()
    session.headers.update(HEADERS)

    for year in range(start, end + 1):
        out = RAW_DIR / f"kbo_pitcher_{year}.csv"
        if out.exists():
            print(f"  skip  {out.name}")
            continue
        try:
            df = fetch_year(session, year)
            if df.empty:
                print(f"  empty {year}")
            else:
                df.to_csv(out, index=False, encoding="utf-8-sig")
                ssg = df[df["팀명"].isin(["SK", "SSG"])]
                print(f"  saved {out.name}  전체={len(df)}명  SK/SSG={len(ssg)}명")
        except Exception as e:
            print(f"  ERROR {year}: {e}")
        time.sleep(random.uniform(1.5, 2.5))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2008)
    parser.add_argument("--end",   type=int, default=2025)
    args = parser.parse_args()
    print(f"KBO 투수 스탯 수집: {args.start}~{args.end}")
    crawl(args.start, args.end)
    print("Done.")
