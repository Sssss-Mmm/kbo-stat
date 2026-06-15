"""
KBO official average game-time crawler.

The average game-time page renders current team averages and yearly league
averages as HTML tables.

Usage:
    python src/crawl_kbo_game_time.py --year 2026
"""

import argparse
import re
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "kbo_official"
RAW_DIR.mkdir(parents=True, exist_ok=True)

GAME_TIME_URL = "https://www.koreabaseball.com/Kbo/League/GameManageRule/GameTimeAvg.aspx"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.koreabaseball.com/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

TEAM_ALIASES = {
    "LG 트윈스": "LG",
    "KT 위즈": "KT",
    "삼성 라이온즈": "삼성",
    "KIA 타이거즈": "KIA",
    "한화 이글스": "한화",
    "두산 베어스": "두산",
    "NC 다이노스": "NC",
    "SSG 랜더스": "SSG",
    "롯데 자이언츠": "롯데",
    "키움 히어로즈": "키움",
}


def _minutes(value: str) -> int | None:
    """'3:21' 형식의 경기시간 문자열을 분 단위 정수로 변환."""
    text = str(value or "").strip()
    match = re.match(r"^(\d{1,2}):(\d{2})$", text)
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def _parse_team_table(table, year: int) -> pd.DataFrame:
    """팀별 평균 경기시간 표(정규이닝/연장포함 2행)를 팀 단위로 파싱한다."""
    rows = table.find_all("tr")
    teams = []
    for cell in rows[1].find_all(["td", "th"])[1:]:
        img = cell.find("img")
        label = img.get("alt", "").strip() if img else cell.get_text(" ", strip=True)
        teams.append(TEAM_ALIASES.get(label, label.split()[0] if label else ""))

    regular = [cell.get_text(" ", strip=True) for cell in rows[2].find_all(["td", "th"])[1:]]
    include_extra = [cell.get_text(" ", strip=True) for cell in rows[3].find_all(["td", "th"])[1:]]
    records = []
    for team, regular_time, extra_time in zip(teams, regular, include_extra):
        records.append(
            {
                "Season": year,
                "Team": team,
                "RegularInningTime": regular_time,
                "RegularInningMinutes": _minutes(regular_time),
                "IncludeExtraTime": extra_time,
                "IncludeExtraMinutes": _minutes(extra_time),
            }
        )
    return pd.DataFrame(records)


def _parse_yearly_table(table, time_type: str) -> list[dict]:
    """연도별 평균 경기시간 표를 파싱한다(연도행/값행이 2행씩 번갈아 나옴)."""
    records = []
    rows = table.find_all("tr")
    for index in range(1, len(rows), 2):
        years = [cell.get_text(" ", strip=True) for cell in rows[index].find_all(["td", "th"])]
        values = (
            [cell.get_text(" ", strip=True) for cell in rows[index + 1].find_all(["td", "th"])]
            if index + 1 < len(rows)
            else []
        )
        for year, value in zip(years, values):
            if year.isdigit() and value:
                records.append(
                    {
                        "Season": int(year),
                        "Type": time_type,
                        "AverageTime": value,
                        "AverageMinutes": _minutes(value),
                    }
                )
    return records


def crawl(year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """팀별 평균 경기시간과 연도별 리그 평균 두 CSV 를 저장한다."""
    response = requests.get(GAME_TIME_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    tables = soup.find_all("table")
    if len(tables) < 3:
        raise RuntimeError("Expected game-time tables were not found.")

    team = _parse_team_table(tables[0], year)
    yearly = pd.DataFrame(
        _parse_yearly_table(tables[1], "regular")
        + _parse_yearly_table(tables[2], "include_extra")
    )

    team_path = RAW_DIR / f"kbo_game_time_team_{year}.csv"
    yearly_path = RAW_DIR / "kbo_game_time_yearly.csv"
    team.to_csv(team_path, index=False, encoding="utf-8-sig")
    yearly.to_csv(yearly_path, index=False, encoding="utf-8-sig")
    print(f"saved {team_path.name} rows={len(team)}")
    print(f"saved {yearly_path.name} rows={len(yearly)}")
    return team, yearly


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2026)
    args = parser.parse_args()
    crawl(args.year)
