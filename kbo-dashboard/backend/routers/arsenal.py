"""투구 분석 CSV 읽기 API (구종 아스널 · 볼카운트 야구).

data/processed 의 CSV(build_pitch_arsenal.py / build_count_metrics.py 산출물)를
직접 읽어 반환한다.
zones.py 와 같은 CSV 직결 패턴이라 DB 마이그레이션이 필요 없다.

커버리지(Days/FirstDate/LastDate)는 두 CSV 모두 행마다 같은 값으로 실려 오므로
화면이 표본 기간(부분 수집이라는 사실)을 그대로 표시할 수 있다.
규정충족(규정타석/규정이닝) 여부만 kbo_naver_hitters/pitchers CSV 에서 PlayerId 로 조인해 붙인다.
"""
from fastapi import APIRouter, HTTPException

import pandas as pd

from utils import PROCESSED_DIR, attach_qualified, current_season

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
    return _serve(path, role, season)


@router.get("/count-baseball")
async def count_baseball(season: int = None):
    """볼카운트별 리그 기준선 + 타자별 카운트 성향을 반환한다.

    한 파일에 Scope='리그'(12칸 매트릭스 + 이름 붙인 버킷)와 Scope='선수'
    (이름 붙인 버킷만) 행이 함께 들어 있다. 화면이 Scope 로 갈라 쓴다.
    """
    season = season or current_season()
    path = PROCESSED_DIR / f"kbo_count_baseball_{season}.csv"
    if not path.exists():
        raise HTTPException(
            status_code=404, detail=f"{season}시즌 볼카운트 데이터가 없습니다."
        )
    # Scope='선수' 행은 전부 타자다(리그 행은 PlayerId=0 이라 조인에서 None 이 된다).
    return _serve(path, "batter", season)


def _serve(path, role: str, season: int):
    """CSV 를 그대로 JSON 으로 넘긴다. 두 엔드포인트가 같은 응답 형태를 쓴다."""
    df = pd.read_csv(path)
    # NaN -> None 으로 바꿔 JSON null 로 직렬화되게 한다(분모 0인 셀의 WhiffRate 등).
    df = df.astype(object).where(pd.notna(df), None)
    # 규정타석/규정이닝 충족 여부(프런트 필터용). 스탯 CSV가 없는 시즌은 None.
    data = attach_qualified(df.to_dict(orient="records"), role, season)
    return {"status": "success", "count": len(data), "data": data}
