"""today-games·today-story 가 외부에 요청하지 않고 로컬 일정 CSV 만으로 답하는지 확인한다(P3-S1).

파이썬 소켓만 막으면 C 확장·다른 클라이언트 경로를 놓칠 수 있어, 실제로 쓰는 HTTP 클라이언트의
요청 함수(requests · urllib3 · httpx(OpenAI SDK 가 씀) · urllib)와 openai 모듈까지 모의 객체로 바꾸고
호출 0회를 센다. TestClient 는 앱을 프로세스 안에서 부르므로(전용 transport) 이 차단과 무관하다.
"""
import collections
import contextlib
import os
import socket
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import openai
import requests
import urllib3
from fastapi.testclient import TestClient

import main
import security
from routers import story, today
from services import story_service

SCHEDULE = """Season,Date,Weekday,Time,away_team,home_team,away_score,home_score,status,GameCenter,Highlight,TV,Radio,Ballpark,Note,GameId
2025,2025-04-01,화,18:30,롯데,LG,2.0,5.0,final,리뷰,하이라이트,SPOTV,,잠실,-,20250401LTLG0
2025,2025-04-01,화,18:30,키움,삼성,,,scheduled,,,,,대구,우천취소,
2025,2025-04-01,화,18:30,NC,두산,,,scheduled,,,,,잠실,우천취소,
2025,2025-04-01,화,17:00,한화,KIA,3.0,3.0,final,리뷰,,,,광주,-,20250401HHHT0
2025,2025-04-02,수,18:30,두산,SSG,,,scheduled,,,,,문학,-,20250402OBSK0
"""
STANDINGS = """순위,팀명,승,패,무,승률,최근10경기,연속,홈,방문
1,SSG,10,5,0,0.667,7승3패,2승,6-0-2,4-0-3
2,두산,8,7,0,0.533,5승5패,1패,4-0-4,4-0-3
"""


@contextlib.contextmanager
def no_network(fake_openai=True):
    """외부로 나갈 수 있는 함수를 전부 모의 객체로 바꾸고 {이름: mock} 을 돌려준다.
    fake_openai=False 면 openai 모듈은 진짜로 두고 SDK 의 요청 함수(SyncAPIClient.request)만 막는다."""
    targets = {
        "socket.connect": (socket.socket, "connect"),
        "socket.connect_ex": (socket.socket, "connect_ex"),
        "socket.create_connection": (socket, "create_connection"),
        "socket.getaddrinfo": (socket, "getaddrinfo"),
        "requests.Session.request": (requests.sessions.Session, "request"),
        "requests.HTTPAdapter.send": (requests.adapters.HTTPAdapter, "send"),
        "urllib3.urlopen": (urllib3.connectionpool.HTTPConnectionPool, "urlopen"),
        "httpx.HTTPTransport": (httpx.HTTPTransport, "handle_request"),
        "httpx.AsyncHTTPTransport": (httpx.AsyncHTTPTransport, "handle_async_request"),
        "urllib.urlopen": (urllib.request, "urlopen"),
        "openai.SyncAPIClient.request": (openai._base_client.SyncAPIClient, "request"),
    }
    mocks = {name: MagicMock(side_effect=AssertionError(f"외부 요청 시도: {name}")) for name in targets}
    fake = MagicMock()
    with contextlib.ExitStack() as stack:
        for name, (owner, attr) in targets.items():
            stack.enter_context(patch.object(owner, attr, mocks[name]))
        if fake_openai:
            stack.enter_context(patch.dict(sys.modules, {"openai": fake}))
            mocks["openai.OpenAI"] = fake.OpenAI
        yield mocks


class OfflineCase(unittest.TestCase):
    """임시 데이터 디렉터리·요청 한도·스토리 캐시를 격리하고 OPENAI_API_KEY 없이 시작한다(test_llm_offline 도 쓴다)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        for target in (patch.object(today, "RAW_DIR", self.dir),
                       patch.object(story_service, "RAW_DIR", self.dir),
                       patch.object(story_service, "PROCESSED_DIR", self.dir),
                       patch.object(security, "_requests", collections.deque()),
                       patch.object(story, "story_service", story_service.StoryService()),
                       patch.dict(today._cache, clear=True),
                       patch.dict(os.environ)):
            target.start()
            self.addCleanup(target.stop)
        os.environ.pop("OPENAI_API_KEY", None)
        self.client = TestClient(main.app)

    def write_local_data(self):
        (self.dir / "kbo_schedule_2025.csv").write_text(SCHEDULE, encoding="utf-8-sig")
        (self.dir / "kbo_team_rank_2025.csv").write_text(STANDINGS, encoding="utf-8-sig")

    def assert_safe_detail(self, detail):
        """503 문구에 내부 경로·예외 이름이 없다."""
        for leak in (str(self.dir), str(today.RAW_DIR), ".csv", "/", "Traceback", "Error", "Exception"):
            self.assertNotIn(leak, detail)

    def assert_no_calls(self, mocks):
        self.assertEqual({k: m.call_count for k, m in mocks.items() if m.call_count}, {})


class TodayOfflineTest(OfflineCase):

    def test_today_games_uses_local_schedule(self):
        self.write_local_data()
        with no_network() as mocks:
            body = self.client.get("/api/today-games", params={"date": "2025-04-01"}).json()
        self.assert_no_calls(mocks)
        self.assertEqual((body["status"], body["count"], body["source"]), ("success", 4, "local_schedule_csv"))
        self.assertEqual(body["range"], {"from": "2025-04-01", "to": "2025-04-02"})
        self.assertRegex(body["asOf"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}\+09:00$")  # 자료 저장 시각(KST)
        games = {g["gameId"]: g for g in body["data"]}
        self.assertEqual(body["data"][0]["gameId"], "20250401HHHT0")  # 시각순
        final = games["20250401LTLG0"]
        self.assertEqual((final["statusCode"], final["winner"], final["home"]["score"], final["away"]["score"]),
                         ("RESULT", "HOME", 5, 2))
        self.assertEqual((final["home"]["code"], final["away"]["code"], final["stadium"]), ("LG", "LT", "잠실"))
        self.assertIsNone(final["home"]["starter"])  # 로컬에 없는 값은 지어내지 않는다
        self.assertEqual(games["20250401HHHT0"]["winner"], "DRAW")
        cancel = games["local-2025-04-01-WOSS-18:30"]  # 취소 행은 GameId 가 비어 있다 — 겹치지 않는 로컬 식별자
        self.assertEqual((cancel["statusCode"], cancel["cancel"], cancel["status"], cancel["home"]["score"]),
                         ("CANCEL", True, "우천취소", None))
        # 응답 계약: 이전 네이버 프록시와 같은 키
        self.assertEqual(set(final), {"gameId", "date", "time", "stadium", "statusCode", "status", "cancel",
                                      "home", "away", "winner", "broadChannel"})
        self.assertEqual(set(final["home"]), {"name", "code", "emblem", "score", "starter"})

    def test_today_games_date_without_games_is_empty(self):
        self.write_local_data()
        (self.dir / "kbo_schedule_2025.csv").write_text(SCHEDULE + "2025,2025-04-04,금,18:30,LG,KT,,,scheduled,,,,,수원,-,20250404LGKT0\n",
                                                        encoding="utf-8-sig")
        with no_network() as mocks:
            body = self.client.get("/api/today-games", params={"date": "2025-04-03"}).json()  # 저장 범위 안, 경기 없는 날
        self.assert_no_calls(mocks)
        self.assertEqual((body["count"], body["data"]), (0, []))

    def test_date_outside_stored_range_is_unavailable(self):
        self.write_local_data()
        with no_network() as mocks:
            responses = [self.client.get(url, params={"date": "2025-10-20"}) for url in ("/api/today-games", "/api/today-story")]
        self.assert_no_calls(mocks)
        for response in responses:  # 포스트시즌·수집 중단 이후를 '경기 없음'으로 답하지 않는다
            self.assertEqual(response.status_code, 503)
            self.assertIn("2025-04-01~2025-04-02 범위만", response.json()["detail"])
            self.assert_safe_detail(response.json()["detail"])

    def test_missing_local_schedule_is_unavailable(self):
        with no_network() as mocks:
            games = self.client.get("/api/today-games", params={"date": "2025-04-01"})
            stories = self.client.get("/api/today-story", params={"date": "2025-04-01"})
        self.assert_no_calls(mocks)
        for response in (games, stories):
            self.assertEqual(response.status_code, 503)
            self.assertEqual(set(response.json()), {"detail"})
            self.assertIn("저장된 경기 일정 데이터가 없습니다", response.json()["detail"])
            self.assert_safe_detail(response.json()["detail"])

    def test_today_story_uses_local_data_only(self):
        self.write_local_data()
        with no_network() as mocks:
            body = self.client.get("/api/today-story", params={"date": "2025-04-02"}).json()
            review = self.client.get("/api/today-story", params={"date": "2025-04-01"}).json()
        self.assert_no_calls(mocks)
        self.assertFalse(body["ai_enabled"])
        preview = body["data"][0]
        self.assertEqual((preview["kind"], preview["matchup"]), ("preview", "두산 @ SSG"))
        self.assertIsNotNone(preview["winProb"])  # 로컬 순위표로 계산
        stories = {s["gameId"]: s for s in review["data"]}
        self.assertEqual(len(stories), 4)  # GameId 없는 취소 경기 둘이 같은 캐시 키를 쓰지 않는다
        self.assertFalse(any(s["cached"] for s in review["data"]))
        self.assertIn("5 : 2", stories["20250401LTLG0"]["story"])  # 로컬 스코어 그대로(키 없음 → mock 문구)

    def test_empty_or_corrupt_schedule_is_unavailable(self):
        """Codex 교차검증: 빈 파일·필수 열 없음·유효 날짜 없음이 500 이 아니라 고정 문구 503."""
        header = SCHEDULE.splitlines()[0]
        for body in ("", header + "\n", SCHEDULE.replace("home_team", "home"), header + "\n2025,날짜아님,화,18:30,롯데,LG,,,scheduled,,,,,잠실,-,X\n",
                     "\x00\xff 깨진 파일", SCHEDULE.replace("2.0,5.0,final", "손상,5.0,final")):
            (self.dir / "kbo_schedule_2025.csv").write_text(body, encoding="utf-8")
            with no_network() as mocks:
                responses = [self.client.get(url, params={"date": "2025-04-01"}) for url in ("/api/today-games", "/api/today-story")]
            self.assert_no_calls(mocks)
            for response in responses:
                self.assertEqual(response.status_code, 503, body[:30])
                self.assertIn("읽을 수 없습니다", response.json()["detail"])
                self.assert_safe_detail(response.json()["detail"])

    def test_file_stat_and_timestamp_errors_are_unavailable(self):
        """Codex 3차: 파일 상태 확인(권한·I/O)·저장 시각 변환 오류도 500 이 아니라 고정 문구 503."""
        self.write_local_data()
        broken_clock = MagicMock(**{"fromtimestamp.side_effect": OverflowError("ts")})
        for target, fake in (("file_versions", MagicMock(side_effect=PermissionError("/secret/path"))), ("datetime", broken_clock)):
            with patch.object(today, target, fake), patch.dict(today._cache, clear=True), no_network():
                response = self.client.get("/api/today-games", params={"date": "2025-04-01"})
            self.assertEqual(response.status_code, 503, target)
            self.assertIn("읽을 수 없습니다", response.json()["detail"])
            self.assert_safe_detail(response.json()["detail"])

    def test_same_fixture_without_game_id_gets_distinct_ids(self):
        """Codex 교차검증: GameId 없는 같은 날짜·팀·시각 행이 둘이어도 카드·스토리 캐시가 겹치지 않는다."""
        row = "2025,2025-04-01,화,18:30,키움,삼성,,,scheduled,,,,,대구,우천취소,\n"
        # Codex 재검토: 순번을 붙인 ID 가 다른 행의 실제 ID 와 다시 겹치지 않는다
        taken = "2025,2025-04-01,화,19:00,LG,KT,,,scheduled,,,,,수원,-,local-2025-04-01-WOSS-18:30-2\n"
        (self.dir / "kbo_schedule_2025.csv").write_text(SCHEDULE + row + taken, encoding="utf-8-sig")
        with no_network():
            games = self.client.get("/api/today-games", params={"date": "2025-04-01"}).json()["data"]
            stories = self.client.get("/api/today-story", params={"date": "2025-04-01"}).json()["data"]
        ids = [g["gameId"] for g in games]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("local-2025-04-01-WOSS-18:30-3", ids)
        self.assertEqual(len({s["gameId"] for s in stories}), len(stories))
        self.assertFalse(any(s["cached"] for s in stories))

    def test_router_has_no_http_client(self):
        source = Path(today.__file__).read_text(encoding="utf-8")
        for needle in ("import requests", "httpx", "urllib", "naver.com"):
            self.assertNotIn(needle, source)


if __name__ == "__main__":
    unittest.main()
