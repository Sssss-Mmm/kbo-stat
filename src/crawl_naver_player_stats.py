"""
Naver KBO full-season player stats crawler.

KBO official ranking pages only list qualified players (규정타석/규정이닝), so the
official crawler yields ~47 hitters / ~18 pitchers. Naver Sports exposes a
season player-stats endpoint that returns EVERY 1군 player who has appeared,
with advanced metrics (OPS/WAR/wRC+/WHIP):

    GET /statistics/categories/kbo/seasons/{year}/players
        ?playerType=HITTER|PITCHER&page=N&pageSize=M   (page is 1-indexed)

Outputs two processed CSVs the web/React "선수 기록" pages consume:

    data/processed/kbo_naver_hitters_{year}.csv
    data/processed/kbo_naver_pitchers_{year}.csv

Usage:
    python src/crawl_naver_player_stats.py --year 2026
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

API = "https://api-gw.sports.naver.com/statistics/categories/kbo/seasons/{year}/players"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://m.sports.naver.com/kbaseball/record/index",
}
PAGE_SIZE = 500

# (출력 컬럼 -> Naver 응답 필드). 타자.
HITTER_FIELDS = {
    "G": "hitterGameCount",
    "AVG": "hitterHra",
    "AB": "hitterAb",
    "H": "hitterHit",
    "2B": "hitterH2",
    "3B": "hitterH3",
    "HR": "hitterHr",
    "RBI": "hitterRbi",
    "R": "hitterRun",
    "SB": "hitterSb",
    "BB": "hitterBb",
    "HBP": "hitterHp",
    "SO": "hitterKk",
    "OBP": "hitterObp",
    "SLG": "hitterSlg",
    "OPS": "hitterOps",
    "ISO": "hitterIsop",
    "BABIP": "hitterBabip",
    "wOBA": "hitterWoba",
    "wRC+": "hitterWrcPlus",
    "WPA": "hitterWpa",
    "WAR": "hitterWar",
}
# 투수.
PITCHER_FIELDS = {
    "G": "pitcherGameCount",
    "W": "pitcherWin",
    "L": "pitcherLose",
    "SV": "pitcherSave",
    "HLD": "pitcherHold",
    "IP": "pitcherInning",
    "ERA": "pitcherEra",
    "SO": "pitcherKk",
    "H": "pitcherHit",
    "HR": "pitcherHr",
    "R": "pitcherR",
    "ER": "pitcherEr",
    "BB": "pitcherBb",
    "HBP": "pitcherHp",
    "WHIP": "pitcherWhip",
    "QS": "pitcherQs",
    "K/9": "pitcherInningKk",
    "BB/9": "pitcherInningBb",
    "K/BB": "pitcherKkBbRate",
    "WPA": "pitcherWpa",
    "WAR": "pitcherWar",
}
PLAYER_TYPE = {"hitter": "HITTER", "pitcher": "PITCHER"}
FIELD_MAP = {"hitter": HITTER_FIELDS, "pitcher": PITCHER_FIELDS}


def current_kbo_year() -> int:
    return datetime.now(ZoneInfo("Asia/Seoul")).year


def position_from_profile(row: dict) -> str | None:
    raw = row.get("profile")
    if not raw:
        return None
    try:
        return json.loads(raw).get("position")
    except (json.JSONDecodeError, TypeError):
        return None


def fetch_all(year: int, player_type: str) -> list[dict]:
    """Page through the endpoint, de-duplicating by playerId."""
    url = API.format(year=year)
    by_id: dict[str, dict] = {}
    page = 1
    while page <= 50:
        params = {"playerType": player_type, "page": page, "pageSize": PAGE_SIZE}
        response = requests.get(url, headers=HEADERS, params=params, timeout=30)
        response.raise_for_status()
        rows = response.json().get("result", {}).get("seasonPlayerStats", []) or []
        before = len(by_id)
        for row in rows:
            by_id[str(row.get("playerId"))] = row
        # 새 id가 없거나 마지막 페이지면 종료(초과 페이지는 중복을 반환).
        if len(rows) < PAGE_SIZE or len(by_id) == before:
            break
        page += 1
    return list(by_id.values())


def build_frame(rows: list[dict], role: str) -> pd.DataFrame:
    fields = FIELD_MAP[role]
    records = []
    for row in rows:
        record = {
            "Season": row.get("year"),
            "PlayerId": row.get("playerId"),
            "선수명": row.get("playerName"),
            "팀명": row.get("teamName"),
            "포지션": position_from_profile(row),
            "등번호": row.get("backNumber"),
        }
        for out_col, src in fields.items():
            record[out_col] = row.get(src)
        record["규정충족"] = bool(row.get("isQualified"))
        records.append(record)

    frame = pd.DataFrame(records)
    if frame.empty:
        return frame
    # 게임 출장 기록이 있는 선수만(0경기 등록 선수 제외).
    frame = frame[frame["G"].fillna(0) > 0]
    sort_key = "WAR" if "WAR" in frame.columns else "G"
    return frame.sort_values(sort_key, ascending=False).reset_index(drop=True)


def crawl(year: int) -> None:
    for role in ("hitter", "pitcher"):
        rows = fetch_all(year, PLAYER_TYPE[role])
        frame = build_frame(rows, role)
        path = PROCESSED_DIR / f"kbo_naver_{role}s_{year}.csv"
        frame.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"[naver-players] saved {path.name} rows={len(frame)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=current_kbo_year())
    args = parser.parse_args()
    crawl(args.year)


if __name__ == "__main__":
    main()
