from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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


if __name__ == "__main__":
    # 핵심 불변식: 활성 시즌은 항상 데이터가 있는 시즌이다.
    assert season_has_data(current_season()), "활성 시즌에 데이터가 없다"
    assert not season_has_data(2099), "없는 시즌이 있다고 나온다"
    print("ok:", current_season())
