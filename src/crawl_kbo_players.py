"""
KBO current registered player crawler.

Fetches the team-by-team player registration page and saves active first-team
registered players with KBO player IDs.

Usage:
    python src/crawl_kbo_players.py
    python src/crawl_kbo_players.py --date 2026-06-11
"""

from __future__ import annotations

import argparse
import re
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from bs4 import BeautifulSoup

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "kbo_official"
RAW_DIR.mkdir(parents=True, exist_ok=True)

REGISTER_URL = "https://www.koreabaseball.com/Player/Register.aspx"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": REGISTER_URL,
    "Accept-Language": "ko-KR,ko;q=0.9",
}

TEAM_CODES = {
    "LG": "LG",
    "KT": "KT",
    "SS": "삼성",
    "HT": "KIA",
    "HH": "한화",
    "OB": "두산",
    "NC": "NC",
    "SK": "SSG",
    "LT": "롯데",
    "WO": "키움",
}

PLAYER_POSITIONS = {"투수", "포수", "내야수", "외야수"}

F_TEAM = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$hfSearchTeam"
F_DATE = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$hfSearchDate"
BTN_SELECT = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$btnCalendarSelect"


def current_kst_date() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")


def form_fields(soup: BeautifulSoup) -> dict[str, str]:
    form = soup.find("form")
    if not form:
        raise RuntimeError("Register form not found.")

    data: dict[str, str] = {}
    for field in form.find_all(["input", "select", "textarea"]):
        name = field.get("name")
        if not name:
            continue
        if field.name == "select":
            selected = field.find("option", selected=True) or field.find("option")
            data[name] = selected.get("value", "") if selected else ""
        elif field.get("type") in {"checkbox", "radio"}:
            if field.has_attr("checked"):
                data[name] = field.get("value", "on")
        else:
            data[name] = field.get("value", "")
    return data


def fetch_team(session: requests.Session, team_code: str, target_date: str | None = None) -> BeautifulSoup:
    response = session.get(REGISTER_URL, timeout=30)
    response.raise_for_status()
    data = form_fields(BeautifulSoup(response.text, "lxml"))
    data[F_TEAM] = team_code
    if target_date:
        data[F_DATE] = target_date.replace("-", "")
    data[BTN_SELECT] = ""

    response = session.post(REGISTER_URL, data=data, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "lxml")


def parse_player_id(href: str) -> str:
    match = re.search(r"playerId=(\d+)", href or "")
    return match.group(1) if match else ""


def parse_body_size(value: str) -> tuple[str, str]:
    match = re.search(r"(\d+)cm,\s*(\d+)kg", value or "")
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def parse_team_soup(soup: BeautifulSoup, team_code: str, target_date: str | None) -> list[dict]:
    rows = []
    roster_date_tag = soup.select_one(".date-txt")
    roster_date = target_date or (roster_date_tag.get_text(strip=True)[:10].replace(".", "-") if roster_date_tag else "")

    for table in soup.find_all("table", class_="tNData"):
        tr_rows = table.find_all("tr")
        if not tr_rows:
            continue
        headers = [cell.get_text(" ", strip=True) for cell in tr_rows[0].find_all(["th", "td"])]
        if len(headers) < 5:
            continue

        position = headers[1]
        if position not in PLAYER_POSITIONS:
            continue

        for tr in tr_rows[1:]:
            cells = tr.find_all(["th", "td"])
            if len(cells) < 5:
                continue
            link = cells[1].find("a", href=True)
            detail_url = link["href"] if link else ""
            height, weight = parse_body_size(cells[4].get_text(" ", strip=True))
            rows.append(
                {
                    "RosterDate": roster_date,
                    "TeamCode": team_code,
                    "Team": TEAM_CODES.get(team_code, team_code),
                    "BackNo": cells[0].get_text(" ", strip=True),
                    "PlayerId": parse_player_id(detail_url),
                    "PlayerName": cells[1].get_text(" ", strip=True),
                    "Position": position,
                    "PitchBat": cells[2].get_text(" ", strip=True),
                    "BirthDate": cells[3].get_text(" ", strip=True),
                    "HeightCm": height,
                    "WeightKg": weight,
                    "Body": cells[4].get_text(" ", strip=True),
                    "DetailUrl": f"https://www.koreabaseball.com{detail_url}" if detail_url.startswith("/") else detail_url,
                    "RecordType": "pitcher" if "PitcherDetail" in detail_url else "hitter",
                }
            )
    return rows


def crawl(target_date: str | None = None) -> pd.DataFrame:
    session = requests.Session()
    session.headers.update(HEADERS)

    rows = []
    for team_code in TEAM_CODES:
        print(f"[players] crawling {team_code}")
        soup = fetch_team(session, team_code, target_date)
        team_rows = parse_team_soup(soup, team_code, target_date)
        print(f"[players] {team_code} rows={len(team_rows)}")
        rows.extend(team_rows)
        time.sleep(0.35)

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("No registered player rows found.")

    df = df.drop_duplicates(subset=["RosterDate", "TeamCode", "PlayerId", "PlayerName", "Position"])
    roster_date = target_date or current_kst_date()
    out = RAW_DIR / f"kbo_registered_players_{roster_date}.csv"
    latest = RAW_DIR / "kbo_registered_players_latest.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    df.to_csv(latest, index=False, encoding="utf-8-sig")
    print(f"[players] saved {out.name} rows={len(df)}")
    print(f"[players] saved {latest.name} rows={len(df)}")
    return df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="YYYY-MM-DD roster date; defaults to current KBO page date")
    args = parser.parse_args()
    crawl(args.date)


if __name__ == "__main__":
    main()
