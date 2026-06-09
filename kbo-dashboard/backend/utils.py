from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def current_season() -> int:
    """KBO 기준(한국 시간) 현재 시즌 연도."""
    return datetime.now(KST).year
