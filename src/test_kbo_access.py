"""KBO 자동 요청 차단(kbo_access) 회귀 테스트. 네트워크·파일 쓰기 없음.

실행: python -m unittest discover -s src -p "test_kbo_access.py" -v
"""
import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import kbo_access

CRAWLERS = ["crawl_kbo_attendance", "crawl_kbo_game_time", "crawl_kbo_hitter", "crawl_kbo_pitcher",
            "crawl_kbo_players", "crawl_kbo_schedule", "crawl_kbo_team_rank"]


class GuardTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(kbo_access.ENV, None)

    def test_every_kbo_crawler_uses_the_guard(self):
        for name in CRAWLERS:
            self.assertIs(importlib.import_module(name).requests, kbo_access.requests, name)

    def test_requests_are_blocked_without_approval(self):
        with mock.patch.object(kbo_access._requests, "get") as get, \
                mock.patch.object(kbo_access._requests, "post") as post, \
                mock.patch.object(kbo_access._requests.Session, "request") as session_request:
            for call in (lambda: kbo_access.requests.get("https://www.koreabaseball.com/"),
                         lambda: kbo_access.requests.post("https://www.koreabaseball.com/ws/x"),
                         lambda: kbo_access.requests.Session().get("https://www.koreabaseball.com/")):
                with self.assertRaises(kbo_access.KboFetchDisabled):
                    call()
        get.assert_not_called()
        post.assert_not_called()
        session_request.assert_not_called()

    def test_no_http_method_or_module_path_bypasses_the_switch(self):
        """Codex P2-A 3차: head/put/delete/options·requests.api 로 우회하지 못한다."""
        import naver_access

        for guarded in (kbo_access.requests, naver_access.requests):
            for method in ("head", "put", "patch", "delete", "options", "request"):
                with mock.patch.object(kbo_access._requests, method) as real, self.assertRaises(kbo_access.FetchDisabled):
                    getattr(guarded, method)("https://example.invalid/")
                real.assert_not_called()
            for name in ("api", "sessions", "adapters"):
                with self.assertRaises(AttributeError):
                    getattr(guarded, name)
            self.assertIs(guarded.RequestException, kbo_access._requests.RequestException)
            prepared = kbo_access._requests.Request("GET", "https://example.invalid/").prepare()
            with mock.patch.object(kbo_access._requests.Session, "send") as real_send, \
                    self.assertRaises(kbo_access.FetchDisabled):
                guarded.Session().send(prepared)
            real_send.assert_not_called()

    def test_approval_flag_lets_requests_through(self):
        os.environ[kbo_access.ENV] = "1"
        with mock.patch.object(kbo_access._requests, "get", return_value="ok") as get:
            self.assertEqual(kbo_access.requests.get("u", timeout=1), "ok")
        get.assert_called_once_with("u", timeout=1)
        self.assertIs(kbo_access.requests.RequestException, kbo_access._requests.RequestException)

    def test_daily_update_skips_kbo_steps_but_keeps_local_builds(self):
        import build_hitter_metrics
        import update_daily as u

        crawls = [mock.patch.object(importlib.import_module(n), "crawl") for n in CRAWLERS]
        mocks = [c.start() for c in crawls]
        for c in crawls:
            self.addCleanup(c.stop)
        # 입력 CSV 가 있는 경우의 동작을 본다(로컬 data/ 유무와 무관하게) — 없는 경우는 test_update_daily 가 본다
        with mock.patch.object(u, "_has_input", return_value=True), \
                mock.patch.object(u.build_team_game_results, "build") as team_build, \
                mock.patch.object(build_hitter_metrics, "build") as metric_build:
            u.update_fast(2026)
            u.update_players(2026)
        self.assertFalse(any(m.called for m in mocks))
        team_build.assert_called_once_with(2026)
        self.assertEqual(metric_build.call_count, 2)


class NoBypassTest(unittest.TestCase):
    """Codex P1-D: 크롤러를 거치지 않고 KBO 를 직접 부르는 경로(프로브 등)도 스위치를 지나야 한다."""
    ROOT = Path(__file__).resolve().parent.parent

    def test_every_file_that_touches_kbo_goes_through_the_switch(self):
        for path in [*(self.ROOT / "src").glob("*.py"), *(self.ROOT / "scripts").glob("*.py")]:
            if path.name.startswith("test_") or path.name == "kbo_access.py":
                continue
            text = path.read_text(encoding="utf-8")
            if "koreabaseball" in text or "import crawl_kbo" in text or "from crawl_kbo" in text:
                self.assertIn("kbo_access", text, f"{path.name}: KBO 요청 경로가 kbo_access 를 거치지 않는다")

    def test_probe_stops_before_requesting_kbo(self):
        sys.path.insert(0, str(self.ROOT / "scripts"))
        import probe_kbo_reachable as probe

        with mock.patch.dict(os.environ), mock.patch.object(probe, "egress_ip", return_value="x"), \
                mock.patch.object(kbo_access._requests, "get") as real_get:
            os.environ.pop(kbo_access.ENV, None)
            self.assertEqual(probe.main(), 2)
        real_get.assert_not_called()


class NaverGuardTest(unittest.TestCase):
    """2026-10-24 결정: 네이버 자동 수집도 이용 조건 확인 전까지 중단 — 같은 스위치 구조."""
    ROOT = Path(__file__).resolve().parent.parent

    def setUp(self):
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("NAVER_AUTOMATED_FETCH_APPROVED", None)

    def test_naver_crawlers_use_the_guard_and_block(self):
        import naver_access

        for name in ("crawl_naver_pitch_zones", "crawl_naver_player_stats"):
            self.assertIs(importlib.import_module(name).requests, naver_access.requests, name)
        with mock.patch.object(kbo_access._requests, "get") as real_get, self.assertRaises(naver_access.NaverFetchDisabled):
            importlib.import_module("crawl_naver_pitch_zones").get_json("https://api-gw.sports.naver.com/x")
        real_get.assert_not_called()

    def test_every_file_that_calls_naver_goes_through_the_switch(self):
        for path in [*(self.ROOT / "src").glob("*.py"), *(self.ROOT / "scripts").glob("*.py")]:
            if path.name.startswith("test_") or path.name in ("naver_access.py", "fetch_guard.py"):
                continue
            if "api-gw.sports.naver.com" in path.read_text(encoding="utf-8"):
                self.assertIn("naver_access", path.read_text(encoding="utf-8"), path.name)

    def test_entry_points_skip_without_requests(self):
        import crawl_naver_boxscore as cb
        import crawl_naver_pitch_zones as cz
        import crawl_naver_player_stats as ps
        import update_daily

        with mock.patch.object(kbo_access._requests, "get") as real_get, \
                mock.patch.object(ps, "crawl") as stats_crawl, mock.patch.object(cz, "crawl") as relay_crawl, \
                mock.patch.object(cb, "collect") as box_collect:
            for module, argv in ((ps, ["x", "--year", "2026"]), (cz, ["x", "--missing", "--season", "2026"]),
                                 (cb, ["x", "--season", "2025", "--game", "20250719HHKT0"])):
                with mock.patch.object(sys, "argv", argv):
                    module.main()
            update_daily.update_pitch_zones("2026-10-01")
        for m in (real_get, stats_crawl, relay_crawl, box_collect):
            m.assert_not_called()


if __name__ == "__main__":
    unittest.main()
