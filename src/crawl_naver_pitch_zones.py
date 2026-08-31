"""
Naver Sports KBO pitch-level crawler.

Naver's game center relay response includes pitch-by-pitch text events and
PTS tracking fields. This script saves normalized pitch rows and a first-pass
3x3 zone summary that can drive hot/cold-zone visualizations.

하루가 끝날 때마다 그날치 CSV 를 저장하므로 긴 범위를 돌리다 끊겨도 이미 받은
날은 남는다. 백필은 월 단위로 나눠 돌리고, 실패하면 남은 날짜 범위만 재실행한다.

Usage:
    python src/crawl_naver_pitch_zones.py --date 2026-06-10
    python src/crawl_naver_pitch_zones.py --from-date 2026-06-10 --to-date 2026-06-11
    python src/crawl_naver_pitch_zones.py --from-date 2025-05-01 --to-date 2025-05-31 --pause 0.5
    python src/crawl_naver_pitch_zones.py --selfcheck
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

import csv_guard

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "naver"
RAW_DIR.mkdir(parents=True, exist_ok=True)

API_BASE = "https://api-gw.sports.naver.com"
# 이닝 요청 사이 대기(초). 백필처럼 수만 건을 순차로 때릴 때의 부하를 감안한 값
# (NFR-09: 공개 API 가 아니라 내부 응답 구조다). --pause 로 조절한다.
PAUSE_SECONDS = 0.5
HALF_PLATE_WIDTH_FT = 0.7083
IN_PLAY_RESULTS = {"H"}
SWING_RESULTS = {"H", "F", "S", "W"}
CALLED_STRIKE_RESULTS = {"T"}
BALL_RESULTS = {"B"}
# At-bat outcome descriptions: hits contain one of these words, while outs,
# errors and fielder's choices never do. Errors/FC are excluded explicitly.
HIT_WORDS = ("안타", "루타", "홈런")
# 정규시즌(kbo_r)과 포스트시즌(kbo_ps_*)만 수집한다.
#   kbo_as = 올스타전. 팀명이 "나눔"/"드림" 이라 팀 집계를 오염시킨다.
#   kbo_e  = 시범경기. 팀명은 정상이지만 기록에 안 들어가는 경기라 시즌 존 집계에
#            섞이면 안 된다(기존 2026 데이터도 개막일 kbo_r 부터라 여기 맞춘다).
# roundCode 가 없는 응답은 걸러지지 않는다 — 모르는 건 버리지 않는 쪽이 안전하다.
SKIP_ROUND_CODES = {"kbo_as", "kbo_e"}
NON_HIT_WORDS = ("실책", "야수선택")

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
    """네이버 스포츠 API 를 호출해 success 확인 후 result 부분만 반환한다."""
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
    """해당 날짜의 KBO 경기 목록을 가져온다."""
    day = game_date.isoformat()
    url = (
        f"{API_BASE}/schedule/games?fields=all&fromDate={day}&toDate={day}"
        "&size=500&categoryId=kbo"
    )
    result = get_json(url)
    games = result.get("games", [])
    return [game for game in games if game.get("categoryId") == "kbo"]


def fetch_relay(game_id: str, inning: int) -> dict:
    """한 경기·한 이닝의 문자중계(투구 단위 이벤트) 데이터를 가져온다."""
    referer = f"https://m.sports.naver.com/game/{game_id}/relay"
    url = f"{API_BASE}/schedule/games/{game_id}/relay?inning={inning}"
    result = get_json(url, referer=referer)
    return result.get("textRelayData", {})


def fetch_name_map(game_id: str) -> dict[str, str]:
    """Build a playerId -> name map from the game record box scores.

    The relay payload only carries player ids (and the batter name in the
    at-bat header). The record endpoint's batter/pitcher box scores list every
    player who appeared, with both pcode/playerCode and name, so it gives a
    complete id->name lookup for the game.
    """
    referer = f"https://m.sports.naver.com/game/{game_id}/record"
    url = f"{API_BASE}/schedule/games/{game_id}/record"
    try:
        record = get_json(url, referer=referer).get("recordData", {})
    except (requests.RequestException, RuntimeError):
        return {}

    name_map: dict[str, str] = {}
    for key in ("battersBoxscore", "pitchersBoxscore"):
        box = record.get(key) or {}
        for side in ("away", "home"):
            for player in box.get(side, []) or []:
                code = player.get("pcode") or player.get("playerCode")
                name = player.get("name")
                if code and name:
                    name_map[str(code)] = name
    return name_map


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
    """투구의 좌우(x)·높이(z)와 타자별 존 상/하단으로 'row-col' 9분할 존을 정한다.

    존을 벗어나면 L-out/R-out, low-out/high-out 으로 표기한다. row 3=상단, col 1=좌.
    """
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
    """경기 정보에서 시즌 연도를 구한다(seasonYear 없으면 경기일 앞 4자리)."""
    season = game.get("seasonYear")
    if season:
        return int(season)
    game_date = game.get("gameDate")
    if game_date:
        return int(str(game_date)[:4])
    return None


def batter_name_from_relay(relay: dict) -> str | None:
    """타석 헤더나 제목('N번타자 이름')에서 타자명을 뽑는다(name_map 보조용)."""
    play_time = relay.get("playTimeAtBat") or {}
    if play_time.get("batterName"):
        return play_time["batterName"]
    title = relay.get("title") or ""
    match = re.search(r"\d+번타자\s+([^\s]+)", title)
    return match.group(1) if match else None


def at_bat_result(relay: dict, batter_name: str | None) -> str:
    """Return the at-bat outcome description, e.g. "좌익수 앞 1루타".

    The play result is a non-pitch text event formatted "{batter} : {desc}",
    distinct from baserunner advancement lines. We pick the line whose subject
    is the current batter; falling back to the last non-pitch result-like line.
    """
    candidates = []
    for option in relay.get("textOptions", []):
        if not isinstance(option, dict) or option.get("ptsPitchId") or option.get("pitchNum"):
            continue
        text = option.get("text") or ""
        if " : " not in text:
            continue
        subject, _, desc = text.partition(" : ")
        candidates.append((subject.strip(), desc.strip()))

    if batter_name:
        for subject, desc in candidates:
            if subject == batter_name:
                return desc
    return candidates[-1][1] if candidates else ""


def is_hit_description(desc: str) -> bool:
    """타석 결과 설명이 안타인지 판정한다(실책/야수선택은 안타 아님)."""
    if any(word in desc for word in NON_HIT_WORDS):
        return False
    return any(word in desc for word in HIT_WORDS)


def merge_pitch_options(relay: dict) -> list[dict]:
    """문자중계의 투구 이벤트(textOptions)에 PTS 추적값(ptsOptions)을 짝지어 준다."""
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


def is_home_batting(relay: dict) -> bool:
    """relay.homeOrAway==1 means the home team is batting (pitcher is away)."""
    value = relay.get("homeOrAway")
    return str(value) in {"1", "home", "HOME"}


def row_from_pitch(
    game: dict,
    relay: dict,
    text_option: dict,
    pitch: dict,
    name_map: dict[str, str] | None = None,
    result_text: str = "",
) -> dict:
    """투구 1개를 한 행(좌표/존/구속/스윙·볼·인플레이·안타 플래그 등)으로 정규화한다."""
    state = text_option.get("currentGameState") or {}
    name_map = name_map or {}

    x = safe_float(pitch.get("crossPlateX"))
    z = plate_z(pitch)
    bottom = safe_float(pitch.get("bottomSz"))
    top = safe_float(pitch.get("topSz"))
    pitch_result = text_option.get("pitchResult", "")
    in_play = pitch_result in IN_PLAY_RESULTS

    away_team = game.get("awayTeamName")
    home_team = game.get("homeTeamName")
    batter_is_home = is_home_batting(relay)
    batter_team = home_team if batter_is_home else away_team
    pitcher_team = away_team if batter_is_home else home_team

    batter_id = state.get("batter")
    pitcher_id = state.get("pitcher")

    return {
        "Date": game.get("gameDate"),
        "GameId": game.get("gameId"),
        "Season": season_from_game(game),
        "Inning": pitch.get("inn") or relay.get("inn"),
        "HomeAway": relay.get("homeOrAway"),
        "AwayTeam": away_team,
        "HomeTeam": home_team,
        "BatterTeam": batter_team,
        "PitcherTeam": pitcher_team,
        "BatterId": batter_id,
        "PitcherId": pitcher_id,
        "BatterName": name_map.get(str(batter_id)) or batter_name_from_relay(relay),
        "BatterSide": pitch.get("stance"),
        "PitcherName": name_map.get(str(pitcher_id)),
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
        "IsInPlay": in_play,
        "IsHit": in_play and is_hit_description(result_text),
    }


def crawl_date(game_date: date, pause_seconds: float = PAUSE_SECONDS) -> pd.DataFrame:
    """하루치 모든 경기를 이닝별로 돌며 투구 단위 행들을 수집한다."""
    games = fetch_games(game_date)
    rows = []
    for game in games:
        game_id = game.get("gameId")
        if not game_id or game.get("statusCode") not in {"RESULT", "ENDED", "STARTED"}:
            continue
        if game.get("roundCode") in SKIP_ROUND_CODES:
            print(f"[naver-pitch] skip {game_id} roundCode={game.get('roundCode')}")
            continue
        name_map = fetch_name_map(game_id)
        for inning in range(1, 13):
            relay = fetch_relay(game_id, inning)
            relays = relay.get("textRelays", [])
            if not relays and inning > 9:
                break
            for text_relay in relays:
                batter_name = batter_name_from_relay(text_relay)
                result_text = at_bat_result(text_relay, batter_name)
                for text_option, pitch in merge_pitch_options(text_relay):
                    rows.append(
                        row_from_pitch(game, text_relay, text_option, pitch, name_map, result_text)
                    )
            time.sleep(pause_seconds)
    return pd.DataFrame(rows)


def build_zone_summary(pitches: pd.DataFrame) -> pd.DataFrame:
    """투구 행을 (타자, 존) 단위로 집계한 1차 존 요약을 만든다(좌표 미상 제외)."""
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


def crawl(start: date, end: date | None = None, pause_seconds: float = PAUSE_SECONDS) -> int:
    """날짜 범위를 돌며 **하루가 끝날 때마다** 그날치 CSV 를 저장하고 총 행 수를 돌려준다.

    하루 = 파일 하나(naver_kbo_pitches_{날짜}.csv)라서
      - 중간에 끊겨도 이미 받은 날은 디스크에 남는다(범위 전체를 메모리에 쌓지 않는다),
      - 같은 날을 다시 돌리면 같은 파일을 같은 내용으로 덮어써 멱등하다,
      - 실패한 청크는 남은 날짜 범위만 다시 돌리면 된다.
    build_zone_metrics 는 파일 여러 개를 (GameId, PitchId) 로 dedupe 해 읽으므로
    기존 범위 파일들과 섞여 있어도 무방하다.
    """
    end = end or start
    total = 0
    for day in date_range(start, end):
        print(f"[naver-pitch] crawling {day}")
        pitches = crawl_date(day, pause_seconds)
        if pitches.empty:
            # 리그 휴식기·전 경기 우천취소는 0행이 정상이다. 저장하지 않고 넘어간다
            # (csv_guard 가 0행 저장을 막는 것과 같은 이유 — 빈 파일을 남기지 않는다).
            print(f"[naver-pitch] {day} pitches=0 — no games, skipped")
            continue
        suffix = day.isoformat()
        csv_guard.save_csv(
            pitches, RAW_DIR / f"naver_kbo_pitches_{suffix}.csv", prefix="[naver-pitch]"
        )
        csv_guard.save_csv(
            build_zone_summary(pitches),
            RAW_DIR / f"naver_kbo_zone_summary_{suffix}.csv",
            prefix="[naver-pitch]",
        )
        total += len(pitches)
    print(f"[naver-pitch] done {start}~{end} rows={total}")
    return total


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


# 실제 응답 한 타석을 그대로 잘라온 고정 입력 (2026-08-30 NC@한화 1회말 3번타자 박민우,
# gameId=20260830NCHH02026, inning=1). 파서가 쓰는 키만 남겼고 값은 손대지 않았다.
# 네이버가 스키마를 바꾸면 크롤러는 예외 대신 빈 결과를 뱉으므로, 이 selfcheck 가
# 과거 시즌 백필에서 그걸 잡아낼 유일한 수단이다.
SAMPLE_GAME = {
    "gameId": "20260830NCHH02026",
    "gameDate": "20260830",
    "seasonYear": 0,  # 실제 응답값. 0 이면 gameDate 앞 4자리로 폴백해야 한다.
    "awayTeamName": "NC",
    "homeTeamName": "한화",
    "statusCode": "RESULT",
}
SAMPLE_RELAY = {
    "inn": 1,
    "homeOrAway": "0",  # 0 = 원정 공격 → 타자팀 NC, 투수팀 한화
    "title": "3번타자 박민우",
    "playTimeAtBat": None,
    "textOptions": [
        {"text": "3번타자 박민우", "stuff": "",
         "currentGameState": {"ball": "0", "strike": "0", "out": "2",
                              "batter": "62907", "pitcher": "54729"}},
        {"text": "1구 스트라이크", "stuff": "직구", "speed": "145", "pitchResult": "T",
         "pitchNum": 1, "ptsPitchId": "260830_180338",
         "currentGameState": {"ball": "0", "strike": "1", "out": "2",
                              "batter": "62907", "pitcher": "54729"}},
        {"text": "2구 스트라이크", "stuff": "커브", "speed": "108", "pitchResult": "T",
         "pitchNum": 2, "ptsPitchId": "260830_180353",
         "currentGameState": {"ball": "0", "strike": "2", "out": "2",
                              "batter": "62907", "pitcher": "54729"}},
        {"text": "3구 파울", "stuff": "직구", "speed": "149", "pitchResult": "F",
         "pitchNum": 3, "ptsPitchId": "260830_180415",
         "currentGameState": {"ball": "0", "strike": "2", "out": "2",
                              "batter": "62907", "pitcher": "54729"}},
        {"text": "4구 타격", "stuff": "스위퍼", "speed": "119", "pitchResult": "H",
         "pitchNum": 4, "ptsPitchId": "260830_180441",
         "currentGameState": {"ball": "0", "strike": "2", "out": "2",
                              "batter": "62907", "pitcher": "54729"}},
        {"text": "박민우 : 우익수 뒤 2루타", "stuff": "",
         "currentGameState": {"ball": "0", "strike": "2", "out": "2",
                              "batter": "62907", "pitcher": "54729"}},
    ],
    "ptsOptions": [
        {"pitchId": "260830_180338", "crossPlateX": 0.430857, "crossPlateY": 0.7083,
         "y0": 55.0, "vy0": -131.863, "ay": 28.5711, "z0": 5.68636, "vz0": -4.59938,
         "az": -14.332, "topSz": 3.351, "bottomSz": 1.625, "stance": "L", "inn": 1},
        {"pitchId": "260830_180353", "crossPlateX": 0.307723, "crossPlateY": 0.7083,
         "y0": 55.0, "vy0": -97.5239, "ay": 17.6154, "z0": 5.81857, "vz0": 8.3542,
         "az": -43.3934, "topSz": 3.351, "bottomSz": 1.625, "stance": "L", "inn": 1},
        {"pitchId": "260830_180415", "crossPlateX": -0.34812, "crossPlateY": 0.7083,
         "y0": 55.0, "vy0": -135.099, "ay": 29.0826, "z0": 5.747, "vz0": -6.50207,
         "az": -10.497, "topSz": 3.351, "bottomSz": 1.625, "stance": "L", "inn": 1},
        {"pitchId": "260830_180441", "crossPlateX": -0.077561, "crossPlateY": 0.7083,
         "y0": 55.0, "vy0": -108.174, "ay": 19.5417, "z0": 5.47534, "vz0": 4.53497,
         "az": -36.7109, "topSz": 3.351, "bottomSz": 1.625, "stance": "L", "inn": 1},
    ],
}


def _selfcheck() -> None:
    """고정 relay 응답으로 파싱 → 존 배정까지의 비자명한 부분을 검사한다."""
    # 1) textOptions(ptsPitchId) ↔ ptsOptions(pitchId) 키 이름이 다른 짝짓기.
    #    타석 헤더와 결과 텍스트(투구 아님)는 빠져야 한다.
    paired = merge_pitch_options(SAMPLE_RELAY)
    assert len(paired) == 4, f"투구 4개가 아니라 {len(paired)}개로 잡혔다"
    assert all(pitch for _, pitch in paired), "PTS 좌표가 붙지 않은 투구가 있다 (pitchId 매칭 실패)"

    # 2) 타석 경계: 한 textRelay = 한 타석이라 첫 투구는 항상 PitchNo==1 로 시작한다.
    pitch_nums = [opt["pitchNum"] for opt, _ in paired]
    assert pitch_nums == [1, 2, 3, 4], f"타석 내 투구 번호가 어긋났다 {pitch_nums}"

    # 3) crossPlateY 는 높이가 아니다(여기서는 반쪽 플레이트 상수 0.7083). 높이는
    #    y=0 도달 시각을 풀어 z(t) 로 구해야 한다 — 이걸 헷갈리면 존이 통째로 틀어진다.
    heights = [round(plate_z(pitch), 3) for _, pitch in paired]
    assert heights == [2.298, 3.090, 2.017, 2.660], heights
    assert all(abs(h - HALF_PLATE_WIDTH_FT) > 1 for h in heights), "plate_z 가 crossPlateY 를 그대로 돌려줬다"

    # 4) 존 배정: row 1=상단, col 1=좌. 존 밖은 low/high-out, L/R-out.
    zones = [zone_bucket(safe_float(p.get("crossPlateX")), plate_z(p),
                         safe_float(p.get("bottomSz")), safe_float(p.get("topSz")))
             for _, p in paired]
    assert zones == ["2-3", "1-3", "3-1", "2-2"], zones
    assert zone_bucket(0.0, 0.5, 1.625, 3.351) == "low-out:2"
    assert zone_bucket(-2.0, 9.9, 1.625, 3.351) == "high-out:L-out"
    assert zone_bucket(None, 2.5, 1.625, 3.351) == "unknown"

    # 5) 타석 결과: "{타자} : {설명}" 라인만 결과이고 주루 라인은 아니다. 안타 판정은
    #    문구 기반이라(스키마 아님) 표현이 바뀌면 조용히 틀린다.
    batter = batter_name_from_relay(SAMPLE_RELAY)
    assert batter == "박민우", batter
    desc = at_bat_result(SAMPLE_RELAY, batter)
    assert desc == "우익수 뒤 2루타", desc
    assert is_hit_description(desc)
    assert not is_hit_description("유격수 앞 땅볼로 출루")
    assert not is_hit_description("중견수 앞 안타성 타구, 실책으로 출루"), "실책은 안타가 아니다"

    # 6) 행 정규화: 인플레이 안타는 마지막 1구뿐, 시즌은 seasonYear=0 → gameDate 폴백,
    #    homeOrAway="0"(원정 공격) → 타자팀 NC / 투수팀 한화.
    rows = [row_from_pitch(SAMPLE_GAME, SAMPLE_RELAY, opt, pitch, {"62907": "박민우", "54729": "문동주"}, desc)
            for opt, pitch in paired]
    assert [r["IsHit"] for r in rows] == [False, False, False, True]
    assert [r["IsSwing"] for r in rows] == [False, False, True, True]
    assert [r["IsCalledStrike"] for r in rows] == [True, True, False, False]
    assert rows[0]["Season"] == 2026, rows[0]["Season"]
    assert rows[0]["BatterTeam"] == "NC" and rows[0]["PitcherTeam"] == "한화"
    assert rows[0]["BatterName"] == "박민우" and rows[0]["PitcherName"] == "문동주"
    assert rows[0]["BatterSide"] == "L" and rows[0]["SpeedKmh"] == 145.0
    assert rows[3]["PitchType"] == "스위퍼"

    # 7) 올스타전은 팀명이 구단이 아니라 "나눔"/"드림" 이라 반드시 걸러져야 한다.
    #    시범경기(kbo_e)도 시즌 기록이 아니라 제외한다. 정규/포스트시즌은 남아야 한다.
    assert {"kbo_as", "kbo_e"} <= SKIP_ROUND_CODES
    assert not {"kbo_r", "kbo_ps_ks", "kbo_ps_pr"} & SKIP_ROUND_CODES

    # 8) 존 요약이 투구 수를 보존하는지(좌표 4개 모두 유효).
    summary = build_zone_summary(pd.DataFrame(rows))
    assert summary["Pitches"].sum() == 4, summary

    print("crawl_naver_pitch_zones selfcheck OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=parse_date, default=None)
    parser.add_argument("--from-date", type=parse_date, default=None)
    parser.add_argument("--to-date", type=parse_date, default=None)
    parser.add_argument(
        "--pause",
        type=float,
        default=PAUSE_SECONDS,
        help=f"이닝 요청 사이 대기 초 (기본 {PAUSE_SECONDS}). 낮추지 말 것",
    )
    parser.add_argument("--selfcheck", action="store_true", help="파서 자가검증만 실행")
    args = parser.parse_args()

    if args.selfcheck:
        _selfcheck()
        return

    if args.date:
        start = end = args.date
    else:
        start = args.from_date or current_kst_date()
        end = args.to_date or start
    crawl(start, end, args.pause)


if __name__ == "__main__":
    main()
