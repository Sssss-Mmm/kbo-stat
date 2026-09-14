import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from pydantic import ValidationError

import security
from routers.rag import AskRequest
from routers.story import today_story
from services.story_service import BUDGET_MESSAGE, StoryService
from services.ai_budget import AIBudget


class SecurityTest(unittest.TestCase):
    def test_reject_invalid_inputs(self):
        for value in ("2026-02-30", "20260101", "../.env", "1900-01-01"):
            with self.assertRaises(HTTPException):
                security.validated_date(value)
        for fields in ({"question": "x" * 2001}, {"question": "x", "season": 900001}):
            with self.assertRaises(ValidationError):
                AskRequest(**fields)
        with self.assertRaises(HTTPException):
            today_story("2025-01-01", 2024)

    def test_global_limit_expires(self):
        with patch.object(security, "_requests", security.deque()), patch.object(security, "monotonic", return_value=100) as clock:
            for _ in range(60):
                security.limit_expensive_requests()
            with self.assertRaises(HTTPException) as error:
                security.limit_expensive_requests()
            self.assertEqual(error.exception.status_code, 429)
            clock.return_value = 161
            security.limit_expensive_requests()

    def test_new_season_does_not_flush_stories(self):
        service = StoryService()
        service._story_cache["existing"] = (0, {})
        service._load_csv(1982)
        self.assertIn("existing", service._story_cache)

    def test_concurrent_requests_generate_once(self):
        service = StoryService()
        game = {"gameId": "test", "statusCode": "RESULT"}
        with patch("services.story_service._fetch", return_value=[game]), patch.object(service, "_load_csv", return_value={}), patch.object(service, "_build_context", return_value={"matchup": "test"}), patch.object(service, "_generate", return_value="review") as generate:
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda _: service.stories_for_date("2025-01-01", 2025), range(4)))
            self.assertEqual(generate.call_count, 1)
            self.assertEqual(len(results), 4)

    def test_budget_message_is_not_cached_for_finished_games(self):
        service = StoryService()
        game = {"gameId": "test", "statusCode": "RESULT"}
        with patch.object(service, "_build_context", return_value={"matchup": "test"}), patch.object(service, "_generate", side_effect=[BUDGET_MESSAGE, "review"]):
            self.assertEqual(service._story_for_game(game, {})["story"], BUDGET_MESSAGE)
            self.assertEqual(service._story_for_game(game, {})["story"], "review")

    def test_paid_attempt_budget_includes_failures(self):
        sdk = MagicMock()
        sdk.OpenAI.return_value.chat.completions.create.side_effect = RuntimeError("offline")
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test", "AI_MAX_CALLS_PER_DAY": "1"}), patch.dict("sys.modules", {"openai": sdk}), patch('services.story_service.ai_budget', AIBudget()):
            service = StoryService()
            with self.assertRaises(RuntimeError):
                service._generate({}, "review")
            self.assertIn("한도", service._generate({}, "review"))
            self.assertEqual(sdk.OpenAI.return_value.chat.completions.create.call_count, 1)
            sdk.OpenAI.assert_called_once_with(timeout=20.0, max_retries=0)


if __name__ == "__main__":
    unittest.main()
