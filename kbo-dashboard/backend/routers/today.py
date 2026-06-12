"""오늘의 경기(예고 선발 포함) — Naver 스포츠 일정 API 온디맨드 프록시.

하루 중에도 바뀌는 라이브 데이터(예고 선발, 스코어, 경기 상태)라 02:00 일일
CSV 파이프라인과 맞지 않으므로, 요청 시점에 Naver 를 직접 호출하고 짧게 캐싱한다.
"""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from fastapi import APIRouter, HTTPException

router = APIRouter()

NAVER_URL = "https://api-gw.sports.naver.com/schedule/games"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://m.sports.naver.com/kbaseball/schedule/index",
}
KST = ZoneInfo("Asia/Seoul")

# 홈팀 코드 -> 홈 구장. Naver 팀 코드 기준(잠실은 LG/두산 공용).
HOME_STADIUM = {
    "LG": "잠실", "OB": "잠실",  # 두산
    "WO": "고척",                # 키움
    "KT": "수원",
    "SK": "문학", "SSG": "문학",  # SSG
    "NC": "창원",
    "LT": "사직",                # 롯데
    "SS": "대구",                # 삼성
    "HT": "광주", "KIA": "광주",  # KIA
    "HH": "대전",                # 한화
}

# 응답 캐시: date -> (timestamp, data). 라이브 데이터라 짧게만 캐싱.
_cache: dict[str, tuple[float, list]] = {}
_TTL = 60.0


def _normalize(g: dict) -> dict:
    dt = g.get("gameDateTime") or ""
    game_time = dt[11:16] if len(dt) >= 16 else ""
    home_code = g.get("homeTeamCode") or ""
    status_code = g.get("statusCode")  # BEFORE / STARTED(진행) / RESULT(종료) / CANCEL 등
    done = status_code == "RESULT"
    started = status_code not in (None, "BEFORE")  # 경기전이 아니면 스코어 노출
    return {
        "gameId": g.get("gameId"),
        "date": g.get("gameDate"),
        "time": game_time,
        "stadium": HOME_STADIUM.get(home_code, ""),
        "statusCode": status_code,
        "status": g.get("statusInfo"),
        "cancel": bool(g.get("cancel")),
        "home": {
            "name": g.get("homeTeamName"),
            "code": home_code,
            "emblem": g.get("homeTeamEmblemUrl"),
            "score": g.get("homeTeamScore") if started else None,
            "starter": g.get("homeStarterName") or None,
        },
        "away": {
            "name": g.get("awayTeamName"),
            "code": g.get("awayTeamCode") or "",
            "emblem": g.get("awayTeamEmblemUrl"),
            "score": g.get("awayTeamScore") if started else None,
            "starter": g.get("awayStarterName") or None,
        },
        "winner": g.get("winner") if done else None,  # HOME / AWAY / DRAW
        "broadChannel": g.get("broadChannel") or "",
    }


def _fetch(date: str) -> list:
    now = time.time()
    cached = _cache.get(date)
    if cached and now - cached[0] < _TTL:
        return cached[1]
    try:
        resp = requests.get(
            NAVER_URL,
            params={
                "fields": "basic,baseball",
                "upperCategoryId": "kbaseball",
                "categoryId": "kbo",
                "fromDate": date,
                "toDate": date,
                "size": 50,
            },
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        games = resp.json().get("result", {}).get("games") or []
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Naver 일정 조회 실패: {exc}")
    data = [_normalize(g) for g in games]
    data.sort(key=lambda x: (x["time"], x["gameId"] or ""))
    _cache[date] = (now, data)
    return data


@router.get("/today-games")
async def today_games(date: str = None):
    """특정 날짜(기본: 오늘 KST)의 KBO 경기 카드 정보를 반환한다."""
    date = date or datetime.now(KST).strftime("%Y-%m-%d")
    data = _fetch(date)
    return {"status": "success", "date": date, "count": len(data), "data": data}
