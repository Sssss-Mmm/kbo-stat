"""외부 LLM(OpenAI) 호출 승인 스위치 — 기본은 꺼짐.

2026-10-25(P3-S1): 데이터 이용 권한 확인 전이라, 경기 기록·선수 정보가 프롬프트로 외부에 나가지 않게 막는다.
OPENAI_API_KEY 가 있어도 LLM_EXTERNAL_CALLS_APPROVED=1 이 아니면 OpenAI 클라이언트를 만들지 않는다(키는 건드리지 않는다).
story_service·qa_service 는 OpenAI 를 직접 import 하지 않고 client() 만 쓴다. 운영 compose 는 이 변수를 넘기지 않는다.
"""
import os

ENV = "LLM_EXTERNAL_CALLS_APPROVED"
DISABLED_NOTICE = "외부 AI 호출이 꺼져 있어(데이터 이용 권한 확인 전) 기록 계산으로 답했습니다."


class LlmDisabled(RuntimeError):
    """승인 전 외부 LLM 호출을 막았을 때."""


def allowed() -> bool:
    return os.environ.get(ENV) == "1" and bool(os.environ.get("OPENAI_API_KEY"))


def client():
    """승인됐을 때만 OpenAI 클라이언트를 만든다. 아니면 openai 를 import 하기 전에 LlmDisabled."""
    if not allowed():
        raise LlmDisabled(f"외부 LLM 호출 비활성화(승인 전) — 허용하려면 {ENV}=1 과 OPENAI_API_KEY")
    from openai import OpenAI  # 승인됐을 때만 import (의존성 선택적)

    return OpenAI(timeout=20.0, max_retries=0)
