from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

KST = ZoneInfo("Asia/Seoul")

# repo 루트/data/processed. 컨테이너에서도 호스트 data/ 가 같은 위치에 마운트된다.
PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"


def season_has_data(season: int) -> bool:
    """해당 시즌 가공 CSV가 하나라도 있으면 True."""
    return any(PROCESSED_DIR.glob(f"*_{season}.csv"))


def current_season() -> int:
    """활성 시즌(KST 기준).

    1~3월에는 새 시즌 데이터가 아직 수집되지 않았는데 연도만 넘어가 있다.
    그대로 쓰면 전 화면이 빈 표가 되므로, 데이터가 없으면 직전 시즌으로 폴백한다.
    """
    year = datetime.now(KST).year
    return year if season_has_data(year) else year - 1


# 규정타석(타자) / 규정이닝(투수) 충족 여부의 출처. 네이버 시즌 스탯 CSV에
# 이미 규정충족 컬럼이 실려 온다(크롤러 산출물).
QUALIFIED_FILES = {
    "batter": "kbo_naver_hitters_{season}.csv",
    "pitcher": "kbo_naver_pitchers_{season}.csv",
}


@lru_cache(maxsize=8)
def _qualified_map(role: str, season: int) -> dict[int, bool] | None:
    """PlayerId -> 규정충족 매핑. 해당 시즌 스탯 CSV가 없으면 None.

    하루 한 번 갱신되는 파생 파일이라 프로세스 수명 동안 캐시해도 된다.
    반환 dict는 캐시에 그대로 남으므로 호출부에서 변형하지 않는다.
    """
    path = PROCESSED_DIR / QUALIFIED_FILES[role].format(season=season)
    if not path.exists():
        return None
    df = pd.read_csv(path, usecols=["PlayerId", "규정충족"])
    return {int(pid): bool(ok) for pid, ok in zip(df["PlayerId"], df["규정충족"])}


def attach_qualified(records: list[dict], role: str, season: int) -> list[dict]:
    """응답 행마다 규정충족(True/False/None)을 PlayerId 기준으로 붙인다.

    시즌 스탯 CSV가 없는 시즌(예: 2025)이나 매칭되는 선수가 없는 행
    (예: 볼카운트 CSV의 리그 집계 행, PlayerId=0)은 None으로 둔다.
    '규정 미달(False)'과 '알 수 없음(None)'은 다르다. False로 채우면
    프런트 필터에서 전원이 걸러져 화면이 빈다.
    """
    mapping = _qualified_map(role, season) or {}
    for row in records:
        row["규정충족"] = mapping.get(row.get("PlayerId"))
    return records


if __name__ == "__main__":
    # 핵심 불변식: 활성 시즌은 항상 데이터가 있는 시즌이다.
    assert season_has_data(current_season()), "활성 시즌에 데이터가 없다"
    assert not season_has_data(2099), "없는 시즌이 있다고 나온다"

    # 조인 자가검증: 스탯 CSV가 있는 시즌은 True/False가 붙고,
    # 없는 시즌/미매칭 행은 None이 붙되 행이 사라지지 않는다.
    known = _qualified_map("batter", current_season()) or {}
    assert known, "현재 시즌 타자 스탯 CSV를 못 읽었다"
    hit_id = next(pid for pid, ok in known.items() if ok)
    rows = [{"PlayerId": hit_id}, {"PlayerId": 0}]
    out = attach_qualified([dict(r) for r in rows], "batter", current_season())
    assert len(out) == 2, "조인이 행을 잃었다"
    assert out[0]["규정충족"] is True and out[1]["규정충족"] is None

    missing = attach_qualified([dict(r) for r in rows], "batter", 2099)
    assert len(missing) == 2, "스탯 CSV 없는 시즌에서 행이 사라졌다"
    assert all(r["규정충족"] is None for r in missing), "알 수 없음을 False로 채웠다"

    print("ok:", current_season())
