"""전체 선수 시즌 스탯 읽기 API.

KBO 공식 순위는 규정 충족 선수만 나오므로, Naver 시즌 선수 스탯
(crawl_naver_player_stats.py 산출물)을 직접 읽어 모든 1군 선수를 반환한다.
zones 와 동일하게 data/processed CSV 를 그대로 서빙한다.
"""
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException

from utils import current_season

router = APIRouter()

ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = ROOT / "data" / "processed"

ROLE_FILES = {
    "hitter": "kbo_naver_hitters_{season}.csv",
    "pitcher": "kbo_naver_pitchers_{season}.csv",
}


def _read_csv(role: str, season: int) -> list[dict]:
    path = PROCESSED_DIR / ROLE_FILES[role].format(season=season)
    if not path.exists():
        return []
    df = pd.read_csv(path)
    df = df.astype(object).where(pd.notna(df), None)
    return df.to_dict(orient="records")


@router.get("/player-stats")
async def player_stats(role: str = "hitter", season: int = None):
    """타자/투수 전체 선수의 시즌 스탯(Naver)을 반환한다."""
    if role not in ROLE_FILES:
        raise HTTPException(status_code=400, detail="role must be 'hitter' or 'pitcher'")
    season = season or current_season()
    data = _read_csv(role, season)
    return {"status": "success", "count": len(data), "data": data}
