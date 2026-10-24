"""
KBO 공식 사이트(koreabaseball.com) 자동 요청 스위치 — 기본은 꺼짐.

2026-10-24 결정: KBO robots.txt 가 "사전 승인 없이 자동 수집·크롤링·복제하는 행위를 금지"하고
`User-agent: * / Disallow: /` 라, 승인 전에는 자동 요청을 하지 않는다. 크롤러 코드는 지우지 않는다.

crawl_kbo_*.py 는 `requests` 대신 이 모듈의 `requests` 를 쓴다. get/post/Session 요청이
KBO_AUTOMATED_FETCH_APPROVED=1 일 때만 나가고, 아니면 KboFetchDisabled 로 멈춘다 — 일일 파이프라인·
캐치업(start_kbo.sh)·수동 실행·CI 프로브 어느 경로로 불러도 같은 자리에서 막힌다.
승인을 받은 뒤 그 범위 안에서만 환경변수를 켠다.
"""
from fetch_guard import FetchDisabled, Guard, _requests  # noqa: F401 (_requests: 테스트가 실제 모듈을 바꿔 끼운다)

ENV = "KBO_AUTOMATED_FETCH_APPROVED"


class KboFetchDisabled(FetchDisabled):
    """승인 없는 KBO 자동 요청을 막았을 때."""


_guard = Guard(ENV, "KBO 공식 사이트", KboFetchDisabled)
requests = _guard.requests
allowed = _guard.allowed
ensure_allowed = _guard.ensure_allowed
