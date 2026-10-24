"""
외부 사이트 자동 요청 스위치의 공통 구현 — 출처마다 환경변수 하나로 켜고, 기본은 꺼짐.

kbo_access.py(KBO 공식 사이트)·naver_access.py(네이버 스포츠)가 이걸 하나씩 만든다. 크롤러는
`requests` 대신 그 모듈의 `requests` 를 쓰고, 모든 HTTP 메서드·Session 요청은 환경변수가 "1" 일 때만 나간다.
"""
import os

import requests as _requests


HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "request"}
# 요청을 보낼 수 없는 것만(예외·응답 형식·상태 코드). api·sessions·adapters 처럼 요청 함수에 닿는 이름은 넣지 않는다.
PASSTHROUGH = {"RequestException", "HTTPError", "ConnectionError", "Timeout", "exceptions", "codes", "Response"}


class FetchDisabled(RuntimeError):
    """승인 전 자동 요청을 막았을 때."""


class Guard:
    def __init__(self, env: str, label: str, error: type[FetchDisabled] = FetchDisabled):
        self.env, self.label, self.error = env, label, error
        guard = self

        class GuardedSession(_requests.Session):
            def request(self, *args, **kwargs):
                guard.ensure_allowed()
                return super().request(*args, **kwargs)

            def send(self, *args, **kwargs):  # 준비된 요청을 request() 없이 보내는 길도 막는다
                guard.ensure_allowed()
                return super().send(*args, **kwargs)

        class GuardedRequests:
            """requests 모듈 대용. HTTP 메서드는 모두 스위치를 거치고, 그 밖엔 예외·상수만 넘긴다(Codex P2-A 3차:
            head/put/delete·requests.api 같은 우회 경로를 열어 두지 않는다)."""
            Session = GuardedSession

            def __getattr__(self, name):
                if name in HTTP_METHODS:
                    def call(*args, **kwargs):
                        guard.ensure_allowed()
                        return getattr(_requests, name)(*args, **kwargs)
                    return call
                if name in PASSTHROUGH:
                    return getattr(_requests, name)
                raise AttributeError(f"{name} 은(는) 차단 래퍼에서 쓸 수 없다 — 필요하면 PASSTHROUGH 에 명시")

        self.requests = GuardedRequests()

    def allowed(self) -> bool:
        return os.environ.get(self.env) == "1"

    def ensure_allowed(self) -> None:
        if not self.allowed():
            raise self.error(f"{self.label} 자동 요청 비활성화(승인 전) — 허용하려면 {self.env}=1")
