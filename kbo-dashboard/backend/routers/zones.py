"""핫/콜드존 읽기 API.

data/processed 의 zone CSV(build_zone_metrics.py 산출물)를 직접 읽어 반환한다.
DB 모델 없이 파생 CSV를 그대로 서빙한다(rag_service 와 동일한 파일 접근 방식).
"""
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException

from utils import current_season

router = APIRouter()

ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = ROOT / "data" / "processed"

ROLE_FILES = {
    "batter": "kbo_batter_zones_{season}.csv",
    "pitcher": "kbo_pitcher_zones_{season}.csv",
}


def _read_zone_csv(role: str, season: int) -> list[dict]:
    path = PROCESSED_DIR / ROLE_FILES[role].format(season=season)
    if not path.exists():
        return []
    df = pd.read_csv(path)
    # NaN -> None 으로 바꿔 JSON null 로 직렬화되게 한다(예: 인플레이 0인 셀의 BipHitRate).
    df = df.astype(object).where(pd.notna(df), None)
    return df.to_dict(orient="records")


@router.get("/zones")
async def zones(role: str = "batter", season: int = None):
    """타자/투수의 (선수, 존) 단위 핫/콜드 집계를 반환한다."""
    if role not in ROLE_FILES:
        raise HTTPException(status_code=400, detail="role must be 'batter' or 'pitcher'")
    season = season or current_season()
    data = _read_zone_csv(role, season)
    return {"status": "success", "count": len(data), "data": data}
