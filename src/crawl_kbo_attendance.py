"""
KBO official attendance crawler.

The KBO crowd page provides team attendance totals from
/ws/Record.asmx/GetCrowdTeam. The endpoint is current-season oriented; this
script saves the fetched rows with the requested season label.

Usage:
    python src/crawl_kbo_attendance.py --year 2026
"""

import argparse
import json
from pathlib import Path

import pandas as pd
import requests

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "kbo_official"
RAW_DIR.mkdir(parents=True, exist_ok=True)

CROWD_URL = "https://www.koreabaseball.com/ws/Record.asmx/GetCrowdTeam"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.koreabaseball.com/Record/Crowd/GraphTeam.aspx",
    "Origin": "https://www.koreabaseball.com",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
}


def fetch_crowd(month: int = 0) -> dict:
    response = requests.post(
        CROWD_URL,
        headers=HEADERS,
        data={"leagueId": 1, "seriesId": 0, "gameMonth": month},
        timeout=30,
    )
    response.raise_for_status()
    return json.loads(response.text)


def _payload_to_rows(payload: dict, year: int, month: int) -> list[dict]:
    teams = [team.strip() for team in payload.get("categories", "").split(",") if team.strip()]
    values = payload.get("data", [{}])[0].get("data", [])
    updated_at = payload.get("date", "")
    rows = []
    for team, attendance in zip(teams, values):
        rows.append(
            {
                "Season": year,
                "Month": month,
                "Team": team,
                "Attendance": int(attendance),
                "UpdatedAt": updated_at,
            }
        )
    return rows


def crawl(year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    total_payload = fetch_crowd(0)
    total = pd.DataFrame(_payload_to_rows(total_payload, year, 0))
    if total.empty:
        raise RuntimeError("No attendance rows found.")

    monthly_rows = []
    for month in range(3, 12):
        payload = fetch_crowd(month)
        monthly_rows.extend(_payload_to_rows(payload, year, month))
    monthly = pd.DataFrame(monthly_rows)

    total_path = RAW_DIR / f"kbo_attendance_{year}.csv"
    monthly_path = RAW_DIR / f"kbo_attendance_monthly_{year}.csv"
    total.to_csv(total_path, index=False, encoding="utf-8-sig")
    monthly.to_csv(monthly_path, index=False, encoding="utf-8-sig")
    print(f"saved {total_path.name} rows={len(total)}")
    print(f"saved {monthly_path.name} rows={len(monthly)}")
    return total, monthly


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2026)
    args = parser.parse_args()
    crawl(args.year)
