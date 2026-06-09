"""
KBO official schedule crawler.

The KBO schedule page fills its table from /ws/Schedule.asmx/GetScheduleList.
This script saves the regular-season schedule as
data/raw/kbo_official/kbo_schedule_<year>.csv.

Usage:
    python src/crawl_kbo_schedule.py --year 2026
"""

import argparse
import re
from datetime import date
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "kbo_official"
RAW_DIR.mkdir(parents=True, exist_ok=True)

SCHEDULE_URL = "https://www.koreabaseball.com/ws/Schedule.asmx/GetScheduleList"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.koreabaseball.com/Schedule/Schedule.aspx",
    "Origin": "https://www.koreabaseball.com",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
}

REGULAR_SEASON = "0,9,6"


def _clean_html(value: str) -> str:
    soup = BeautifulSoup(value or "", "lxml")
    return soup.get_text(" ", strip=True)


def _parse_game(value: str) -> dict:
    soup = BeautifulSoup(value or "", "lxml")
    all_spans = [span.get_text(strip=True) for span in soup.find_all("span")]
    teams = [all_spans[0], all_spans[-1]] if len(all_spans) >= 2 else []
    score_spans = soup.select("em span")
    score_values = [span.get_text(strip=True) for span in score_spans]
    numbers = [int(text) for text in score_values if text.isdigit()]

    away = teams[0] if teams else ""
    home = teams[1] if len(teams) > 1 else ""
    away_score = numbers[0] if len(numbers) > 0 else None
    home_score = numbers[1] if len(numbers) > 1 else None
    status = "scheduled" if away_score is None or home_score is None else "final"

    return {
        "away_team": away,
        "home_team": home,
        "away_score": away_score,
        "home_score": home_score,
        "status": status,
    }


def _extract_game_id(value: str) -> str:
    match = re.search(r"gameId=([^&'\" ]+)", value or "")
    return match.group(1) if match else ""


def _parse_row(row: dict, year: int, current_day: str) -> tuple[dict | None, str]:
    cells = row.get("row", [])
    if not cells:
        return None, current_day

    first_text = _clean_html(cells[0].get("Text", ""))
    has_day = bool(re.match(r"\d{2}\.\d{2}", first_text))
    if has_day:
        current_day = first_text
        cells = cells[1:]

    if len(cells) < 7 or not current_day:
        return None, current_day

    month, day = map(int, current_day[:5].split("."))
    game_date = date(year, month, day).isoformat()
    time_text = _clean_html(cells[0].get("Text", ""))
    game_html = cells[1].get("Text", "")
    game = _parse_game(game_html)
    game_center = _clean_html(cells[2].get("Text", ""))
    game_id = _extract_game_id(cells[2].get("Text", ""))
    if not game_center and not game_id:
        game["status"] = "scheduled"
        game["away_score"] = None
        game["home_score"] = None

    record = {
        "Season": year,
        "Date": game_date,
        "Weekday": current_day[current_day.find("(") + 1 : current_day.find(")")] if "(" in current_day else "",
        "Time": time_text,
        **game,
        "GameCenter": game_center,
        "Highlight": _clean_html(cells[3].get("Text", "")),
        "TV": _clean_html(cells[4].get("Text", "")),
        "Radio": _clean_html(cells[5].get("Text", "")),
        "Ballpark": _clean_html(cells[6].get("Text", "")),
        "Note": _clean_html(cells[7].get("Text", "")) if len(cells) > 7 else "",
        "GameId": game_id,
    }
    return record, current_day


def fetch_schedule(year: int, month: str = "", team_id: str = "") -> pd.DataFrame:
    response = requests.post(
        SCHEDULE_URL,
        headers=HEADERS,
        data={
            "leId": 1,
            "srIdList": REGULAR_SEASON,
            "seasonId": year,
            "gameMonth": month,
            "teamId": team_id,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    records = []
    current_day = ""
    for row in payload.get("rows", []):
        record, current_day = _parse_row(row, year, current_day)
        if record:
            records.append(record)
    return pd.DataFrame(records)


def crawl(year: int) -> pd.DataFrame:
    df = fetch_schedule(year)
    if df.empty:
        raise RuntimeError("No schedule rows found.")

    out = RAW_DIR / f"kbo_schedule_{year}.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"saved {out.name} games={len(df)}")
    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2026)
    args = parser.parse_args()
    crawl(args.year)
