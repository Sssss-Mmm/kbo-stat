"""핫/콜드존 읽기 API.

data/processed 의 zone CSV(build_zone_metrics.py 산출물)를 직접 읽어 반환한다.
DB 모델 없이 파생 CSV를 그대로 서빙한다(rag_service 와 동일한 파일 접근 방식).
규정충족(규정타석/규정이닝) 여부만 kbo_naver_hitters/pitchers CSV 에서 PlayerId 로 조인해 붙인다.

/api/pitch-coverage 는 투구 원본(data/raw/naver)이 실제로 담은 경기 범위를 낸다.
DB 수집 시각(자료 기준 줄)과 별개다 — 투구 크롤러는 따로 돌아서 경기가 빠질 수 있다.
"""
import glob
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException

from utils import attach_qualified, current_season

router = APIRouter()

ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = ROOT / "data" / "processed"
RAW_DIR = ROOT / "data" / "raw" / "naver"

ROLE_FILES = {
    "batter": "kbo_batter_zones_{season}.csv",
    "pitcher": "kbo_pitcher_zones_{season}.csv",
}


def _read_zone_csv(role: str, season: int) -> list[dict]:
    path = PROCESSED_DIR / ROLE_FILES[role].format(season=season)
    if not path.exists():
        raise HTTPException(
            status_code=404, detail=f"{season}시즌 {role} 존 데이터가 없습니다."
        )
    df = pd.read_csv(path)
    # NaN -> None 으로 바꿔 JSON null 로 직렬화되게 한다(예: 인플레이 0인 셀의 BipHitRate).
    df = df.astype(object).where(pd.notna(df), None)
    # 규정타석/규정이닝 충족 여부(프런트 필터용). 스탯 CSV가 없는 시즌은 None.
    return attach_qualified(df.to_dict(orient="records"), role, season)


@router.get("/zones")
async def zones(role: str = "batter", season: int = None):
    """타자/투수의 (선수, 존) 단위 핫/콜드 집계를 반환한다."""
    if role not in ROLE_FILES:
        raise HTTPException(status_code=400, detail="role must be 'batter' or 'pitcher'")
    season = season or current_season()
    data = _read_zone_csv(role, season)
    return {"status": "success", "count": len(data), "data": data}


def _pitch_files(season: int) -> list[str]:
    """build_zone_metrics.load_pitches 와 같은 규칙으로 시즌 투구 파일을 고른다(파일명 연도)."""
    files = sorted(glob.glob(str(RAW_DIR / "naver_kbo_pitches_*.csv")))
    return [f for f in files
            if not (years := set(re.findall(r"(\d{4})-\d{2}-\d{2}", Path(f).stem))) or str(season) in years]


# 화면 탭이 실제로 읽는 분석 CSV(빌더 산출물). 원본보다 오래됐는지 /api/pitch-coverage 가 함께 알려 준다.
ANALYSIS_FILES = {
    "batter_zones": "kbo_batter_zones_{season}.csv",
    "pitcher_zones": "kbo_pitcher_zones_{season}.csv",
    "pitcher_arsenal": "kbo_pitcher_arsenal_{season}.csv",
    "batter_vs_pitch": "kbo_batter_vs_pitch_{season}.csv",
    "count_baseball": "kbo_count_baseball_{season}.csv",
}
# build_zone_metrics.assign_zones 가 이 좌표 중 하나라도 비면 버린다 — 존 CSV 투구 수와 맞춰 볼 원본 기준.
ZONE_COORDS = ["PlateX", "PlateZ", "TopSz", "BottomSz"]


@lru_cache(maxsize=8)
def _raw_stats(season: int, signature: tuple) -> dict | None:
    """signature(파일 경로·mtime)가 같으면 캐시를 쓴다 — 원본 61MB 를 매 요청 읽지 않는다."""
    want = {"Date", "GameId", "Season", "PitchId", *ZONE_COORDS}
    frames = [pd.read_csv(path, usecols=lambda c: c in want) for path, _ in signature]
    pitches = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if pitches.empty:
        return None
    pitches = pitches[pitches["Season"] == season].dropna(subset=["GameId", "Date"])
    if pitches.empty:
        return None
    # 투구 수·날짜 수는 빌더(load_pitches)와 같은 중복 제거 뒤에 센다.
    deduped = pitches.dropna(subset=["PitchId"]).drop_duplicates(["GameId", "PitchId"])
    dates = pitches["Date"].astype(str)
    return {
        # 원본 GameId 는 KBO 경기 ID(13자) 뒤에 시즌이 붙는다: 20260328HTSK0 + 2026.
        "games": frozenset(pitches["GameId"].astype(str).str[:13]),
        "first_date": dates.min(), "last_date": dates.max(),
        "days": int(deduped["Date"].astype(str).nunique()),
        "zone_pitches": int(len(deduped.dropna(subset=ZONE_COORDS))),
    }


def _analysis(season: int, raw: dict) -> dict:
    """분석 CSV 별 실제 범위와 원본 대비 stale 여부. 파일이 없으면 None(탭이 '데이터 없음'을 따로 낸다).

    아스널·볼카운트 CSV 는 빌더가 Days/FirstDate/LastDate 를 행마다 싣는다 → 날짜로 비교.
    존 CSV 는 날짜 메타가 없어 좌표 있는 투구 수로 비교한다(재집계 없이 Pitches 합만 읽는다).
    """
    out = {}
    for key, name in ANALYSIS_FILES.items():
        path = PROCESSED_DIR / name.format(season=season)
        if not path.exists():
            out[key] = None
        elif key.endswith("_zones"):
            pitches = int(pd.read_csv(path, usecols=["Pitches"], encoding="utf-8-sig")["Pitches"].sum())
            out[key] = {"pitches": pitches, "raw_pitches": raw["zone_pitches"], "stale": pitches != raw["zone_pitches"]}
        else:
            row = pd.read_csv(path, usecols=["Days", "FirstDate", "LastDate"], nrows=1, encoding="utf-8-sig")
            if row.empty:
                out[key] = None
                continue
            first, last, days = str(row["FirstDate"][0]), str(row["LastDate"][0]), int(row["Days"][0])
            out[key] = {"first_date": first, "last_date": last, "days": days,
                        "stale": (first, last, days) != (raw["first_date"], raw["last_date"], raw["days"])}
    return out


def pitch_coverage(season: int) -> dict | None:
    files = _pitch_files(season)
    raw = _raw_stats(season, tuple((f, Path(f).stat().st_mtime_ns) for f in files))
    if raw is None:
        return None
    games = raw["games"]
    out = {
        "season": season, "first_date": raw["first_date"], "last_date": raw["last_date"], "days": raw["days"],
        "games": len(games), "regular_games": None, "regular_total": None, "rate": None,
        "unscheduled_games": None, "other_games": None, "analysis": _analysis(season, raw),
    }
    # 분모 = 치러진 정규시즌 경기(kbo_team_games). 없으면 수집률을 비워 둔다(추정하지 않는다).
    schedule = PROCESSED_DIR / f"kbo_team_games_{season}.csv"
    if schedule.exists():
        regular = set(pd.read_csv(schedule, usecols=["GameId"], encoding="utf-8-sig")["GameId"].astype(str))
        if regular:
            hit = len(games & regular)
            # 일정에 없는 경기: 정규시즌 ID 는 YYYYMMDD 로 시작하고, 포스트시즌은 3333·4444·5555·7777 같은
            # 코드로 시작한다. 시즌 연도로 시작하는데 일정에 없으면 일정 CSV 가 늦게 갱신된 정규시즌
            # 경기일 수 있어 '정규시즌 외'로 단정하지 않고 따로 센다.
            rest = games - regular
            unscheduled = sum(g.startswith(str(season)) for g in rest)
            out.update(regular_games=hit, regular_total=len(regular), rate=round(hit / len(regular), 4),
                       unscheduled_games=unscheduled, other_games=len(rest) - unscheduled)
    return out


@router.get("/pitch-coverage")
async def pitch_coverage_api(season: int = None):
    """투구 데이터가 담은 경기 범위(시작·종료일, 수집 경기 수, 정규시즌 대비 수집률).

    원본이 없으면 data=null. 정규시즌 일정 CSV 가 없으면 regular_*/rate/unscheduled/other 가 null 이다.
    analysis 는 탭별 분석 CSV 의 실제 범위와 stale(원본보다 오래됨) 여부다.
    """
    season = season or current_season()
    return {"status": "success", "data": pitch_coverage(season)}
