"""
네이버 스포츠(api-gw.sports.naver.com) 자동 요청 스위치 — 기본은 꺼짐.

2026-10-24 결정: 네이버 이용약관·API 사용 조건을 확인할 때까지 자동 수집을 일시 중단한다
(api-gw 의 robots.txt 404 는 허용 근거로 보지 않는다). 코드·데이터는 지우지 않는다.

crawl_naver_pitch_zones.py(문자중계·박스스코어 — crawl_naver_boxscore 도 이 get_json 을 쓴다)와
crawl_naver_player_stats.py 가 이 모듈의 `requests` 를 쓴다. NAVER_AUTOMATED_FETCH_APPROVED=1 일 때만 요청이 나간다.
"""
from fetch_guard import FetchDisabled, Guard

ENV = "NAVER_AUTOMATED_FETCH_APPROVED"


class NaverFetchDisabled(FetchDisabled):
    """승인 전 네이버 자동 요청을 막았을 때."""


_guard = Guard(ENV, "네이버 스포츠", NaverFetchDisabled)
requests = _guard.requests
allowed = _guard.allowed
ensure_allowed = _guard.ensure_allowed


def skip(what: str) -> None:
    """CLI 진입점이 승인 전이면 요청 없이 끝낼 때 남기는 한 줄."""
    print(f"[skip:collect] naver {what}: 승인 전 자동 요청 비활성화 — 기존 데이터 유지 ({ENV}=1 로 허용)")
