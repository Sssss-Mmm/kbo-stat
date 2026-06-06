"""
KBO official team standings crawler.

The KBO team-rank page exposes the current season as a regular HTML table.
This script saves that table as data/raw/kbo_official/kbo_team_rank_<year>.csv.

Usage:
    python src/crawl_kbo_team_rank.py --year 2026
"""

import argparse
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "kbo_official"
RAW_DIR.mkdir(parents=True, exist_ok=True)

TEAM_RANK_URL = "https://www.koreabaseball.com/Record/TeamRank/TeamRank.aspx"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.koreabaseball.com/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def _parse_table(html: str) -> pd.DataFrame:
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
    response = requests.get(TEAM_RANK_URL, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return _parse_table(response.text)


def crawl(year: int) -> pd.DataFrame:
    df = fetch_current()
    if df.empty:
        raise RuntimeError("No team standings table found.")

    df.insert(0, "Season", year)
    out = RAW_DIR / f"kbo_team_rank_{year}.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"saved {out.name} teams={len(df)}")
    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2026)
    args = parser.parse_args()
    crawl(args.year)
