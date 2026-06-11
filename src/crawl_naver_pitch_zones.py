"""
Naver Sports KBO pitch-level crawler.

Naver's game center relay response includes pitch-by-pitch text events and
PTS tracking fields. This script saves normalized pitch rows and a first-pass
3x3 zone summary that can drive hot/cold-zone visualizations.

Usage:
    python src/crawl_naver_pitch_zones.py --date 2026-06-10
    python src/crawl_naver_pitch_zones.py --from-date 2026-06-10 --to-date 2026-06-11
"""

from __future__ import annotations

import argparse
import math
import re
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "naver"
RAW_DIR.mkdir(parents=True, exist_ok=True)

API_BASE = "https://api-gw.sports.naver.com"
HALF_PLATE_WIDTH_FT = 0.7083
IN_PLAY_RESULTS = {"H"}
SWING_RESULTS = {"H", "F", "S", "W"}
CALLED_STRIKE_RESULTS = {"T"}
BALL_RESULTS = {"B"}
HIT_WORDS = ("안타", "홈런", "2루타", "3루타")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://m.sports.naver.com/kbaseball/schedule/index",
}


def current_kst_date() -> date:
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


def date_range(start: date, end: date) -> list[date]:
    days = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def get_json(url: str, referer: str | None = None) -> dict:
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success", False):
        raise RuntimeError(f"Naver API failed: {payload}")
    return payload.get("result", {})


def fetch_games(game_date: date) -> list[dict]:
    day = game_date.isoformat()
    url = (
        f"{API_BASE}/schedule/games?fields=all&fromDate={day}&toDate={day}"
        "&size=500&categoryId=kbo"
    )
    result = get_json(url)
    games = result.get("games", [])
    return [game for game in games if game.get("categoryId") == "kbo"]


def fetch_relay(game_id: str, inning: int) -> dict:
    referer = f"https://m.sports.naver.com/game/{game_id}/relay"
    url = f"{API_BASE}/schedule/games/{game_id}/relay?inning={inning}"
    result = get_json(url, referer=referer)
    return result.get("textRelayData", {})


def plate_z(pitch: dict) -> float | None:
    """Calculate plate-crossing height in feet from PTS fields.

    y(t) reaches home plate at y=0. The API also sends crossPlateY, but recent
    KBO samples show that field as the half-plate constant, not vertical height.
    """
    try:
        y0 = float(pitch["y0"])
        vy0 = float(pitch["vy0"])
        ay = float(pitch["ay"])
        z0 = float(pitch["z0"])
        vz0 = float(pitch["vz0"])
        az = float(pitch["az"])
    except (KeyError, TypeError, ValueError):
        return None

    if abs(ay) < 1e-9:
        if abs(vy0) < 1e-9:
            return None
        t = -y0 / vy0
    else:
        discriminant = vy0 * vy0 - 2 * ay * y0
        if discriminant < 0:
            return None
        roots = [(-vy0 + math.sqrt(discriminant)) / ay, (-vy0 - math.sqrt(discriminant)) / ay]
        positive_roots = [root for root in roots if root >= 0]
        if not positive_roots:
            return None
        t = min(positive_roots)
    return z0 + vz0 * t + 0.5 * az * t * t


def zone_bucket(x: float | None, z: float | None, bottom: float | None, top: float | None) -> str:
    if x is None or z is None or bottom is None or top is None or top <= bottom:
        return "unknown"

    if x < -HALF_PLATE_WIDTH_FT:
        col = "L-out"
    elif x > HALF_PLATE_WIDTH_FT:
        col = "R-out"
    else:
        col_width = (HALF_PLATE_WIDTH_FT * 2) / 3
        col = str(min(3, max(1, int((x + HALF_PLATE_WIDTH_FT) / col_width) + 1)))

    if z < bottom:
        row = "low-out"
    elif z > top:
        row = "high-out"
    else:
        row_height = (top - bottom) / 3
        row = str(3 - min(2, max(0, int((z - bottom) / row_height))))

    if row.isdigit() and col.isdigit():
        return f"{row}-{col}"
    return f"{row}:{col}"


def safe_float(value) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def season_from_game(game: dict) -> int | None:
    season = game.get("seasonYear")
    if season:
        return int(season)
    game_date = game.get("gameDate")
    if game_date:
        return int(str(game_date)[:4])
    return None


def batter_name_from_relay(relay: dict) -> str | None:
    play_time = relay.get("playTimeAtBat") or {}
    if play_time.get("batterName"):
        return play_time["batterName"]
    title = relay.get("title") or ""
    match = re.search(r"\d+번타자\s+([^\s]+)", title)
    return match.group(1) if match else None


def merge_pitch_options(relay: dict) -> list[dict]:
    pts_by_id = {
        str(option.get("pitchId")): option
        for option in relay.get("ptsOptions", [])
        if option.get("pitchId")
    }
    rows = []
    for option in relay.get("textOptions", []):
        if not isinstance(option, dict) or not option.get("ptsPitchId"):
            continue
        pitch = pts_by_id.get(str(option.get("ptsPitchId")), {})
        rows.append((option, pitch))
    return rows


def row_from_pitch(game: dict, relay: dict, text_option: dict, pitch: dict) -> dict:
    state = text_option.get("currentGameState") or {}
    players = text_option.get("currentPlayersInfo") or {}
    away_player = players.get("away") or {}
    home_player = players.get("home") or {}
    batter_side = away_player if away_player.get("playerType") == "batter" else home_player
    pitcher_side = away_player if away_player.get("playerType") == "pitcher" else home_player

    x = safe_float(pitch.get("crossPlateX"))
    z = plate_z(pitch)
    bottom = safe_float(pitch.get("bottomSz"))
    top = safe_float(pitch.get("topSz"))
    result_text = relay.get("title") or ""
    pitch_result = text_option.get("pitchResult", "")

    return {
        "Date": game.get("gameDate"),
        "GameId": game.get("gameId"),
        "Season": season_from_game(game),
        "Inning": pitch.get("inn") or relay.get("inn"),
        "HomeAway": relay.get("homeOrAway"),
        "AwayTeam": game.get("awayTeamName"),
        "HomeTeam": game.get("homeTeamName"),
        "BatterId": state.get("batter"),
        "PitcherId": state.get("pitcher"),
        "BatterName": batter_name_from_relay(relay),
        "BatterSide": pitch.get("stance"),
        "PitcherName": pitcher_side.get("name"),
        "PitchNo": text_option.get("pitchNum"),
        "PitchId": text_option.get("ptsPitchId"),
        "PitchText": text_option.get("text"),
        "PitchResult": pitch_result,
        "PitchType": text_option.get("stuff"),
        "SpeedKmh": safe_float(text_option.get("speed")),
        "Ball": safe_float(state.get("ball")),
        "Strike": safe_float(state.get("strike")),
        "Out": safe_float(state.get("out")),
        "PlateX": x,
        "PlateZ": z,
        "RawCrossPlateY": safe_float(pitch.get("crossPlateY")),
        "TopSz": top,
        "BottomSz": bottom,
        "Zone": zone_bucket(x, z, bottom, top),
        "AtBatText": result_text,
        "IsSwing": pitch_result in SWING_RESULTS,
        "IsBall": pitch_result in BALL_RESULTS,
        "IsCalledStrike": pitch_result in CALLED_STRIKE_RESULTS,
        "IsInPlay": pitch_result in IN_PLAY_RESULTS,
        "IsHit": pitch_result in IN_PLAY_RESULTS and any(word in result_text for word in HIT_WORDS),
    }


def crawl_date(game_date: date, pause_seconds: float = 0.15) -> pd.DataFrame:
    games = fetch_games(game_date)
    rows = []
    for game in games:
        game_id = game.get("gameId")
        if not game_id or game.get("statusCode") not in {"RESULT", "ENDED", "STARTED"}:
            continue
        for inning in range(1, 13):
            relay = fetch_relay(game_id, inning)
            relays = relay.get("textRelays", [])
            if not relays and inning > 9:
                break
            for text_relay in relays:
                for text_option, pitch in merge_pitch_options(text_relay):
                    rows.append(row_from_pitch(game, text_relay, text_option, pitch))
            time.sleep(pause_seconds)
    return pd.DataFrame(rows)


def build_zone_summary(pitches: pd.DataFrame) -> pd.DataFrame:
    if pitches.empty:
        return pd.DataFrame()
    usable = pitches[pitches["Zone"] != "unknown"].copy()
    if usable.empty:
        return pd.DataFrame()

    group_cols = ["Season", "BatterId", "BatterName", "BatterSide", "Zone"]
    summary = (
        usable.groupby(group_cols, dropna=False)
        .agg(
            Pitches=("PitchId", "count"),
            Swings=("IsSwing", "sum"),
            Balls=("IsBall", "sum"),
            CalledStrikes=("IsCalledStrike", "sum"),
            InPlay=("IsInPlay", "sum"),
            Hits=("IsHit", "sum"),
            AvgSpeedKmh=("SpeedKmh", "mean"),
        )
        .reset_index()
    )
    summary["SwingRate"] = summary["Swings"] / summary["Pitches"]
    summary["BipHitRate"] = summary["Hits"] / summary["InPlay"].replace(0, pd.NA)
    return summary


def crawl(start: date, end: date | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    end = end or start
    frames = []
    for day in date_range(start, end):
        print(f"[naver-pitch] crawling {day}")
        day_frame = crawl_date(day)
        print(f"[naver-pitch] {day} pitches={len(day_frame)}")
        if not day_frame.empty:
            frames.append(day_frame)

    pitches = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if pitches.empty:
        print("[naver-pitch] no pitch rows found")
        return pitches, pd.DataFrame()

    suffix = start.isoformat() if start == end else f"{start.isoformat()}_{end.isoformat()}"
    pitch_path = RAW_DIR / f"naver_kbo_pitches_{suffix}.csv"
    summary_path = RAW_DIR / f"naver_kbo_zone_summary_{suffix}.csv"
    summary = build_zone_summary(pitches)

    pitches.to_csv(pitch_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    print(f"[naver-pitch] saved {pitch_path.name} rows={len(pitches)}")
    print(f"[naver-pitch] saved {summary_path.name} rows={len(summary)}")
    return pitches, summary


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=parse_date, default=None)
    parser.add_argument("--from-date", type=parse_date, default=None)
    parser.add_argument("--to-date", type=parse_date, default=None)
    args = parser.parse_args()

    if args.date:
        start = end = args.date
    else:
        start = args.from_date or current_kst_date()
        end = args.to_date or start
    crawl(start, end)


if __name__ == "__main__":
    main()
