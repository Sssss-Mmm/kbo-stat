"""
KBO 공식 사이트(koreabaseball.com) 타자 스탯 크롤러.

전략:
  - sort=PA_CN 으로 모든 선수(150명) 수집 후 팀명으로 필터
  - ASP.NET WebForms: 1페이지 GET, 2페이지~ __doPostBack POST
  - SK(~2021) / SSG(2021~) 양쪽 팀명 처리

Usage:
    python crawl_kbo.py                   # 2008-2025, 전 팀 수집
    python crawl_kbo.py --start 2015 --end 2024
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

BASE_URL = "https://www.koreabaseball.com/Record/Player/HitterBasic/BasicOld.aspx"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.koreabaseball.com/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

F_SEASON = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ddlSeason$ddlSeason"
F_SERIES = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ddlSeries$ddlSeries"
F_TEAM   = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ddlTeam$ddlTeam"
F_POS    = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ddlPos$ddlPos"


def _viewstate(soup: BeautifulSoup) -> dict:
    out = {}
    for name in ["__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"]:
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
    data = [[td.get_text(strip=True) for td in row.find_all(["th", "td"])] for row in rows[1:] if row.find_all(["th", "td"])]
    return pd.DataFrame(data, columns=cols) if data else None


def _total_pages(soup: BeautifulSoup) -> int:
    pager = soup.find(class_="paging")
    if not pager:
        return 1
    nums = [int(m.group(1)) for a in pager.find_all("a", id=True)
            if (m := re.search(r"btnNo(\d+)", a["id"]))]
    return max(nums) if nums else 1


def fetch_year(session: requests.Session, year: int) -> pd.DataFrame:
    # 1페이지: GET
    r0 = session.get(BASE_URL, params={
        "sort": "PA_CN", "order": "D",
        "year": str(year), "teamCode": "", "pcode": "", "playerName": "",
    }, timeout=20)
    r0.raise_for_status()
    soup0 = BeautifulSoup(r0.text, "lxml")

    frames = []
    df0 = _parse_table(soup0)
    if df0 is not None:
        frames.append(df0)

    total = _total_pages(soup0)
    vs    = _viewstate(soup0)

    for page in range(2, total + 1):
        event_target = (
            "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents"
            f"$ucPager$btnNo{page}"
        )
        post = {
            "__EVENTTARGET":   event_target,
            "__EVENTARGUMENT": "",
            F_SEASON: str(year),
            F_SERIES: "0",
            F_TEAM:   "",
            F_POS:    "0",
            **vs,
        }
        rp = session.post(BASE_URL, data=post, timeout=20)
        rp.raise_for_status()
        soup_p = BeautifulSoup(rp.text, "lxml")
        dfp = _parse_table(soup_p)
        if dfp is not None:
            frames.append(dfp)
        vs = _viewstate(soup_p)   # 다음 페이지용 ViewState 갱신
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
        out = RAW_DIR / f"kbo_{year}.csv"
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
    print(f"KBO 스탯 수집: {args.start}~{args.end}")
    crawl(args.start, args.end)
    print("Done.")
