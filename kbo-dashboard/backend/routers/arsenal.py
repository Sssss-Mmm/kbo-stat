"""구종 아스널 읽기 API.

data/processed 의 arsenal CSV(build_pitch_arsenal.py 산출물)를 직접 읽어 반환한다.
zones.py 와 같은 CSV 직결 패턴이라 DB 마이그레이션이 필요 없다.

한 행 = (선수, 구종, 볼카운트 버킷). 커버리지(Days/FirstDate/LastDate)는 행마다
같은 값으로 실려 오므로 화면이 표본 기간을 그대로 표시할 수 있다.
"""
from fastapi import APIRouter, HTTPException

import pandas as pd

from utils import PROCESSED_DIR, current_season

router = APIRouter()

ROLE_FILES = {
    "pitcher": "kbo_pitcher_arsenal_{season}.csv",
    "batter": "kbo_batter_vs_pitch_{season}.csv",
}


@router.get("/pitch-arsenal")
async def pitch_arsenal(role: str = "pitcher", season: int = None):
    """투수의 구종 배합 / 타자의 상대 구종별 성적을 반환한다."""
    if role not in ROLE_FILES:
        raise HTTPException(status_code=400, detail="role must be 'pitcher' or 'batter'")
    season = season or current_season()
    path = PROCESSED_DIR / ROLE_FILES[role].format(season=season)
    if not path.exists():
        raise HTTPException(
            status_code=404, detail=f"{season}시즌 {role} 구종 데이터가 없습니다."
        )
    df = pd.read_csv(path)
    # NaN -> None 으로 바꿔 JSON null 로 직렬화되게 한다(스윙 0인 셀의 WhiffRate 등).
    df = df.astype(object).where(pd.notna(df), None)
    return {"status": "success", "count": len(df), "data": df.to_dict(orient="records")}
