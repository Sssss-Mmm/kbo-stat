"""OPENAI_API_KEY 가 있어도 승인 스위치 없이는 경기 리뷰·질의응답이 OpenAI 로 나가지 않는지 확인한다(P3-S1).

진짜 openai SDK 를 그대로 두고 그 요청 함수(SyncAPIClient.request)와 하위 httpx·소켓을 모의 객체로 막는다
(test_today_offline.no_network(fake_openai=False)). 로그·표준출력에 키와 프롬프트 내용이 남지 않는지도 본다.
"""
import collections
import contextlib
import io
import logging
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import openai

from services import llm_access
from services.ai_budget import AIBudget
from services.qa_service import QuestionAnswerService
from tests.test_qa import fixture as qa_fixture
from tests.test_today_offline import OfflineCase, no_network

SECRET = "sk-test-DO-NOT-LEAK-1234567890"
QUESTION = "삼성 최근 10경기 왜 못해? 비밀문구-프롬프트"


@contextlib.contextmanager
def captured_output():
    """루트 로거(DEBUG)·stdout·stderr 를 모두 모은다."""
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            yield buffer
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)


class LlmOfflineTest(OfflineCase):

    def setUp(self):
        super().setUp()
        os.environ["OPENAI_API_KEY"] = SECRET  # 운영처럼 키는 있다
        os.environ.pop(llm_access.ENV, None)
        self.write_local_data()
        self.qa = QuestionAnswerService()
        for target in (patch.object(self.qa, "_load", return_value=qa_fixture()),
                       patch("services.qa_service.ai_budget", AIBudget()),
                       patch("services.story_service.ai_budget", AIBudget())):
            target.start()
            self.addCleanup(target.stop)
        self.init_patch = patch.object(openai.OpenAI, "__init__", side_effect=AssertionError("OpenAI 클라이언트 생성"))
        self.init = self.init_patch.start()
        self.init_active = True
        self.addCleanup(lambda: self.init_active and self.init_patch.stop())

    def assert_no_leak(self, text):
        self.assertNotIn(SECRET, text)
        self.assertNotIn("비밀문구-프롬프트", text)
        self.assertNotIn("AnalysisPlan으로 바꾼다", text)  # 시스템 프롬프트 본문도 남지 않는다
        self.assertNotIn("칼럼니스트", text)

    def test_review_and_qa_do_not_call_openai_even_with_key(self):
        with no_network(fake_openai=False) as mocks, captured_output() as out:
            review = self.client.get("/api/today-story", params={"date": "2025-04-01"}).json()
            answer = self.qa.ask(QUESTION, 2026)
        self.assert_no_calls(mocks)
        self.assertEqual(self.init.call_count, 0)
        self.assertFalse(review["ai_enabled"])
        final = next(s for s in review["data"] if s["gameId"] == "20250401LTLG0")
        self.assertTrue(final["story"].startswith("[기록 요약]"))  # 로컬 스코어로 만든 요약
        self.assertIn("5 : 2", final["story"])
        self.assertEqual(answer["mode"], "analysis")  # 기록 계산 결과
        self.assertEqual(answer["notice"], llm_access.DISABLED_NOTICE)
        self.assertTrue(answer["evidence"])
        self.assert_no_leak(out.getvalue())

    def test_only_exact_approval_value_enables(self):
        for value in ("", "0", "true", "yes", "1 "):
            with patch.dict(os.environ, {llm_access.ENV: value}):
                self.assertFalse(llm_access.allowed(), repr(value))
                with self.assertRaises(llm_access.LlmDisabled):
                    llm_access.client()
        with patch.dict(os.environ, {llm_access.ENV: "1"}):
            os.environ.pop("OPENAI_API_KEY")
            self.assertFalse(llm_access.allowed())  # 승인만 있고 키가 없으면 여전히 꺼짐

    def test_approved_path_reaches_only_the_mocked_sdk_request(self):
        """승인을 켜면 진짜 SDK 클라이언트가 만들어지고 그 요청 함수에 닿는다 — 차단 지점이 맞다는 확인(실제 요청 없음)."""
        self.init_patch.stop()
        self.init_active = False
        os.environ[llm_access.ENV] = "1"
        with no_network(fake_openai=False) as mocks, captured_output() as out:
            answer = self.qa.ask(QUESTION, 2026)
            review = self.client.get("/api/today-story", params={"date": "2025-04-01"})
        self.assertEqual(review.status_code, 200)  # 리뷰 실패가 그날 카드 전체를 500 으로 만들지 않는다
        final = next(s for s in review.json()["data"] if s["gameId"] == "20250401LTLG0")
        self.assertTrue(final["story"].startswith("[기록 요약]"))
        self.assertIn("만들지 못해", final["story"])  # 승인 전 차단과 다른 문구
        self.assertIn("story model call failed: AssertionError", out.getvalue())
        sdk = mocks.pop("openai.SyncAPIClient.request")
        self.assertGreaterEqual(sdk.call_count, 1)  # 프롬프트는 여기서 멈췄다
        self.assert_no_calls(mocks)  # 그 아래 httpx·소켓에는 닿지 않음
        self.assertEqual(answer["mode"], "analysis")
        self.assertIn("기록 계산", answer["notice"])
        self.assertIn("QA model call failed: AssertionError", out.getvalue())  # 예외 종류만 기록
        self.assert_no_leak(out.getvalue())

    def test_importing_app_does_not_import_openai(self):
        code = "import sys, main; print('openai' in sys.modules)"
        env = {**os.environ, "OPENAI_API_KEY": SECRET, "KBO_ENV": "test"}
        result = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
                                env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.stdout.strip(), "False", result.stderr[-500:])
        self.assert_no_leak(result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
