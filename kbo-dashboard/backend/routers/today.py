"""오늘의 경기 카드 — 로컬 일정 CSV(data/raw/kbo_official/kbo_schedule_{시즌}.csv)만 읽는다.

2026-10-25(P3-S1): 데이터 이용 권한 확인 전이라 요청마다 네이버 일정 API 를 부르던 실시간 프록시를 없앴다.
이 모듈에는 HTTP 클라이언트가 없다 — 실시간 조회를 되살리려면 권한 확인 후 코드 변경(리뷰)이 필요하다.
로컬 일정에는 예고 선발·진행 중 스코어가 없으므로 starter 는 None, 상태는 저장 시점 기준이다.
시즌 CSV 가 없거나 날짜가 저장된 일정 범위 밖이면(포스트시즌·수집 중단 이후) 503 — 빈 목록('경기 없음')이나
지어낸 결과로 대신하지 않는다. 범위 안의 경기 없는 날만 빈 목록이다.
"""
from datetime import datetime
import logging
from threading import Lock
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import APIRouter, HTTPException, Depends
from security import limit_expensive_requests, validated_date
from services.csv_cache import file_versions

router = APIRouter(dependencies=[Depends(limit_expensive_requests)])

ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "data" / "raw" / "kbo_official"
SOURCE = "local_schedule_csv"
OFFLINE = "외부 실시간 조회는 데이터 이용 권한 확인 전까지 비활성화되어 있습니다."
UNAVAILABLE = f"저장된 경기 일정 데이터가 없습니다. {OFFLINE}"
UNREADABLE = f"저장된 경기 일정 자료를 읽을 수 없습니다. {OFFLINE}"
REQUIRED = ["Date", "Time", "away_team", "home_team", "status"]
logger = logging.getLogger(__name__)

# CSV 팀명 -> 팀 코드(이전 네이버 응답과 같은 코드 체계 — story_service.CODE_TO_TEAM 이 역방향).
TEAM_CODE = {
    "LG": "LG", "두산": "OB", "키움": "WO", "KT": "KT", "SSG": "SK",
    "NC": "NC", "롯데": "LT", "삼성": "SS", "KIA": "HT", "한화": "HH",
}

# 시즌 -> (파일 버전, DataFrame, 자료 저장 시각). 파일이 바뀌면 다시 읽는다.
_cache: dict[int, tuple[tuple, pd.DataFrame, str]] = {}
_fetch_lock = Lock()


def _schedule(season: int) -> tuple[pd.DataFrame, str]:
    """(일정, 자료 저장 시각 KST) — 저장 시각은 CSV 수정 시각(마지막 수집 시점)."""
    path = RAW_DIR / f"kbo_schedule_{season}.csv"
    version = file_versions([path])
    cached = _cache.get(season)
    if cached and cached[0] == version:
        return cached[1], cached[2]
    if version == (None,):
        raise HTTPException(status_code=503, detail=UNAVAILABLE)
    df = pd.read_csv(path, dtype={"Date": str, "Time": str, "GameId": str})
    df = df[df["Date"].str.fullmatch(r"\d{4}-\d{2}-\d{2}", na=False)][REQUIRED + [c for c in df if c not in REQUIRED]]
    if df.empty:
        raise HTTPException(status_code=503, detail=UNREADABLE)
    as_of = datetime.fromtimestamp(version[0][0] / 1e9, ZoneInfo("Asia/Seoul")).isoformat(timespec="minutes")
    _cache[season] = (version, df, as_of)
    return df, as_of


def _score(value):
    return None if pd.isna(value) else int(value)


def _text(value) -> str:
    return "" if pd.isna(value) else str(value).strip()


def _normalize(r) -> dict:
    note = _text(r.get("Note"))
    done = r.get("status") == "final"
    cancel = not done and note not in ("", "-")
    status_code = "RESULT" if done else "CANCEL" if cancel else "BEFORE"
    home_score = _score(r.get("home_score")) if done else None
    away_score = _score(r.get("away_score")) if done else None
    winner = None
    if done and home_score is not None and away_score is not None:
        winner = "HOME" if home_score > away_score else "AWAY" if away_score > home_score else "DRAW"
    home, away = _text(r.get("home_team")), _text(r.get("away_team"))
    date, time = _text(r.get("Date")), _text(r.get("Time"))
    # 취소 경기 행은 GameId 가 비어 있다 — 카드 키·story 캐시가 겹치지 않게 날짜·팀·시각으로 로컬 식별자를 만든다.
    game_id = _text(r.get("GameId")) or f"local-{date}-{TEAM_CODE.get(away, away)}{TEAM_CODE.get(home, home)}-{time}"
    return {
        "gameId": game_id,
        "date": date,
        "time": time,
        "stadium": _text(r.get("Ballpark")),
        "statusCode": status_code,
        "status": "종료" if done else note if cancel else "예정",
        "cancel": cancel,
        "home": {"name": home, "code": TEAM_CODE.get(home, ""), "emblem": None, "score": home_score, "starter": None},
        "away": {"name": away, "code": TEAM_CODE.get(away, ""), "emblem": None, "score": away_score, "starter": None},
        "winner": winner,
        "broadChannel": _text(r.get("TV")),
    }


def _load(date: str) -> tuple[list, dict]:
    """(date 의 경기 카드 목록, 자료 정보 {asOf, range}). 외부 요청 없음."""
    date = validated_date(date)
    try:
        return _load_checked(date)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — 파일 상태·읽기·필수 열·시각 변환·정규화·정렬 어디서든: 500 대신 고정 문구 503
        logger.warning("schedule csv unreadable: date=%s %s", date, type(exc).__name__)  # 경로·예외 문구는 남기지 않는다
        raise HTTPException(status_code=503, detail=UNREADABLE) from None


def _load_checked(date: str) -> tuple[list, dict]:
    with _fetch_lock:
        df, as_of = _schedule(int(date[:4]))
    first, last = df["Date"].min(), df["Date"].max()
    if not first <= date <= last:
        raise HTTPException(status_code=503, detail=f"저장된 {date[:4]} 경기 일정은 {first}~{last} 범위만 있습니다(포스트시즌·이후 일정 미포함). {OFFLINE}")
    data = [_normalize(r) for r in df[df["Date"] == date].to_dict("records")]
    # GameId 없는 같은 편성(팀·시각) 행이 겹치면 순번을 붙인다. 실제 ID 를 먼저 모두 예약해 순번 ID 와도 겹치지 않게 한다.
    used, seen = {g["gameId"] for g in data}, set()
    for game in data:
        if game["gameId"] in seen:
            n = 2
            while f"{game['gameId']}-{n}" in used:
                n += 1
            game["gameId"] = f"{game['gameId']}-{n}"
            used.add(game["gameId"])
        seen.add(game["gameId"])
    data.sort(key=lambda x: (x["time"], x["gameId"]))
    return data, {"asOf": as_of, "range": {"from": first, "to": last}}


def _fetch(date: str) -> list:
    """date 의 경기 카드 목록. 이름은 story_service 가 import 하던 그대로 둔다."""
    return _load(date)[0]


@router.get("/today-games")
def today_games(date: str = None):
    """특정 날짜(기본: 오늘 KST)의 KBO 경기 카드 정보를 로컬 일정 CSV 에서 반환한다."""
    date = validated_date(date)
    data, meta = _load(date)
    return {"status": "success", "date": date, "count": len(data), "source": SOURCE, **meta, "data": data}
