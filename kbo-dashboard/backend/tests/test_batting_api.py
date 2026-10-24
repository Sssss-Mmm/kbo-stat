"""P3-A 2단계 — /api/v2/batting/advanced 와 선수 프로필의 타자 고급 지표. 합성 픽스처(가상 선수·숫자) + SQLite.

시나리오(2025 시즌, 팀A·팀B):
- 1 가상갑: KBO 기록실 연결(PA 115) → BB%·K% = 기록실 PA. 투구 계산은 미완결 → BABIP 직접 계산 없음
- 2 가상을 / 3 가상을: 같은 팀 동명이인 — AB·H 로 갈려 3 만 기록실과 연결
- 4 가상병: 투구 계산 완결 → BABIP 직접 계산 + 조립 PA
- 5 가상정: 기록실에 다른 팀으로 올라 있음(이적) → 연결 안 됨, PA 없음
- 6 가상무: 타수 0 → ISO 분모 0, 출처 BABIP 0.000 은 쓰지 않음
- 7 투수갑: 투수(타격 줄은 명단에서 빠짐)
"""
import datetime
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from database import Base
from models import Hitter, Team
from models.records import Build, PlayerGame
from services import batting_advanced as ba
from services import team_player_service as tp
from tests.test_v2_api import make_engine

HIT = "Season,PlayerId,선수명,팀명,포지션,등번호,G,AVG,AB,H,2B,3B,HR,RBI,R,SB,BB,HBP,SO,OBP,SLG,OPS,ISO,BABIP,wOBA,wRC+,WPA,WAR,규정충족\n"
PIT = "Season,PlayerId,선수명,팀명,포지션,등번호,G,W,L,SV,HLD,IP,ERA,SO,H,HR,R,ER,BB,HBP,WHIP,QS,K/9,BB/9,K/BB,WPA,WAR,규정충족\n"


def hit(pid, name, team, ab, h, d2, d3, hr, bb, hbp, so, babip, qualified, pos="내야수"):
    return (f"2025,{pid},{name},{team},{pos},1,50,0.3,{ab},{h},{d2},{d3},{hr},10,10,1,{bb},{hbp},{so},"
            f"0.35,0.45,0.8,0.15,{babip},0.35,110.0,0.5,1.0,{qualified}\n")


def batter_games(build, pid, games, complete, ab, hbp, sf, sh):
    """경기별 행을 만들어 시즌 합이 (ab, hbp, sf, sh) 가 되게 한다. 첫 경기에 몰아 넣는다."""
    out = []
    for i in range(games):
        first = i == 0
        out.append(dict(build_id=build, calc_rule="r1", role="batter", player_id=pid, game_id=f"20250{i + 101:04d}AABB0"[:13],
                        season=2025, ab=ab if first else 0, hbp=hbp if first else 0, sf=sf if first else 0,
                        sh=sh if first else 0, stats_complete=i < complete))
    return out


class BattingApiBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "processed").mkdir()
        (tmp / "raw" / "kbo_official").mkdir(parents=True)
        (tmp / "processed" / "kbo_naver_hitters_2025.csv").write_text(HIT
            + hit(1, "가상갑", "팀A", 100, 30, 5, 1, 4, 10, 2, 20, 0.315, True)
            + hit(2, "가상을", "팀A", 16, 3, 0, 0, 0, 1, 0, 5, 0.273, False)
            + hit(3, "가상을", "팀A", 446, 120, 20, 2, 10, 40, 5, 80, 0.310, True)
            + hit(4, "가상병", "팀B", 50, 15, 3, 0, 2, 5, 1, 10, 0.333, False)
            + hit(5, "가상정", "팀B", 200, 50, 10, 0, 5, 20, 2, 40, 0.290, True)
            + hit(6, "가상무", "팀B", 0, 0, 0, 0, 0, 1, 0, 0, 0.0, False)
            + hit(7, "투수갑", "팀A", 2, 0, 0, 0, 0, 0, 0, 2, 0.0, False, pos="투수"), encoding="utf-8-sig")
        (tmp / "processed" / "kbo_naver_pitchers_2025.csv").write_text(
            PIT + "2025,7,투수갑,팀A,투수,40,20,5,4,0,0,60 1/3,3.5,50,55,4,25,23,18,2,1.21,3,7.5,2.7,2.78,0.3,1.0,False\n",
            encoding="utf-8-sig")
        cls.patches = [patch.object(tp, "PROCESSED_DIR", tmp / "processed"), patch.object(tp, "RAW_DIR", tmp / "raw" / "kbo_official")]
        for p in cls.patches:
            p.start()
        cls.engine = make_engine()
        Base.metadata.create_all(cls.engine)
        with cls.engine.begin() as conn:
            conn.execute(Team.__table__.insert(), [{"id": 1, "name": "팀A"}, {"id": 2, "name": "팀B"}, {"id": 3, "name": "팀C"}])
            conn.execute(Hitter.__table__.insert(), [  # KBO 기록실(규정 이상) — 선수 ID 없음
                dict(season=2025, rank=1, player_name="가상갑", team_id=1, pa=115, ab=100, hits=30, bb=10, so=20, hbp=2),
                dict(season=2025, rank=2, player_name="가상을", team_id=1, pa=495, ab=446, hits=120, bb=40, so=80, hbp=5),
                dict(season=2025, rank=3, player_name="가상정", team_id=3, pa=225, ab=200, hits=50, bb=20, so=40, hbp=2)])
            conn.execute(Build.__table__.insert(), [dict(build_id="pg25", kind="player_game", season=2025, calc_rule="r1",
                                                         source_file="x.csv", row_count=1, loaded_at=datetime.datetime(2026, 10, 23))])
            conn.execute(PlayerGame.__table__.insert(), batter_games("pg25", 1, 10, 9, 100, 2, 1, 0)
                         + batter_games("pg25", 4, 5, 5, 50, 1, 2, 1))
        import main
        import routers.v2 as router
        cls.router_patch = patch.object(router, "engine", cls.engine)
        cls.router_patch.start()
        cls.client = TestClient(main.app)

    @classmethod
    def tearDownClass(cls):
        cls.router_patch.stop()
        for p in cls.patches:
            p.stop()

    def get(self, url, code=200):
        r = self.client.get(url)
        self.assertEqual(r.status_code, code, r.text)
        return r.json()


class AdvancedListTest(BattingApiBase):
    def rows(self, **params):
        q = "&".join(f"{k}={v}" for k, v in params.items())
        return {r["player_id"]: r for r in self.get(f"/api/v2/batting/advanced?season=2025&limit=200&{q}")["data"]}

    def test_shape_separates_identity_record_pa_and_metrics(self):
        body = self.get("/api/v2/batting/advanced?season=2025")
        r = next(x for x in body["data"] if x["player_id"] == 1)
        self.assertEqual(set(r), {"player_id", "name", "team", "season", "position", "qualified", "record", "pa",
                                  "kbo_record_link", "metrics"})
        self.assertEqual(r["record"]["source"], "naver_season_stats")
        self.assertNotIn("BABIP", r["record"])  # 출처 BABIP 는 metrics.babip_source 로만
        self.assertEqual(set(r["metrics"]), {"iso", "babip", "babip_source", "bb_pct", "k_pct"})
        json.dumps(body)
        self.assertEqual(body["meta"]["publication"], "private_pending_rights")
        self.assertIn("반올림 SLG − 반올림 AVG", body["meta"]["rules"]["iso"])
        self.assertNotIn(7, {x["player_id"] for x in body["data"]})  # 투수의 타격 줄은 명단에서 빠진다

    def test_pa_priority_and_rates(self):
        rows = self.rows()
        self.assertEqual((rows[1]["pa"]["basis"], rows[1]["pa"]["value"]), (ba.PA_KBO, 115))
        bb = rows[1]["metrics"]["bb_pct"]
        self.assertEqual((bb["status"], bb["display"], bb["fraction"]), (ba.CALCULATED, 8.7,
                                                                           {"numerator": 10, "denominator": 115, "scale": 100}))
        self.assertEqual((rows[4]["pa"]["basis"], rows[4]["pa"]["value"]), (ba.PA_ASSEMBLED, 50 + 5 + 1 + 2 + 1))
        for pid in (2, 5, 6):  # PA 미확인 — BB%·K% 를 계산하지 않는다
            self.assertIsNone(rows[pid]["pa"]["value"])
            for k in ("bb_pct", "k_pct"):
                self.assertEqual((rows[pid]["metrics"][k]["status"], rows[pid]["metrics"][k]["value"]), (ba.UNAVAILABLE, None))

    def test_babip_calculated_vs_source_never_mixed(self):
        rows = self.rows()
        self.assertEqual(rows[4]["metrics"]["babip"]["status"], ba.CALCULATED)  # 완결 → 직접 계산
        self.assertAlmostEqual(rows[4]["metrics"]["babip"]["value"], 13 / 40, places=12)  # (15−2)/(50−10−2+2)
        self.assertEqual(rows[1]["metrics"]["babip"]["status"], ba.UNAVAILABLE)  # 미완결 1경기
        self.assertIn("미완결 경기 1개", rows[1]["metrics"]["babip"]["reason"])
        self.assertEqual((rows[1]["metrics"]["babip_source"]["status"], rows[1]["metrics"]["babip_source"]["value"]),
                         (ba.SOURCE, 0.315))
        self.assertIsNone(rows[1]["metrics"]["babip_source"]["fraction"])  # 출처 값은 계산 근거가 없다

    def test_zero_denominator_and_placeholder(self):
        r = self.rows()[6]
        self.assertEqual((r["metrics"]["iso"]["status"], r["metrics"]["iso"]["value"]), (ba.ZERO_DENOMINATOR, None))
        self.assertEqual(r["metrics"]["babip_source"]["status"], ba.UNAVAILABLE)  # 출처 0.000 자리표시
        self.assertTrue(r["metrics"]["iso"]["reason"])

    def test_same_name_and_transfer_links(self):
        rows = self.rows()
        self.assertEqual(rows[3]["kbo_record_link"]["status"], ba.LINKED)          # AB·H 로 갈림
        self.assertEqual(rows[2]["kbo_record_link"]["status"], "not_listed")
        self.assertEqual(rows[5]["kbo_record_link"]["status"], "not_listed")       # 기록실엔 팀C 로 — 연결 안 함
        self.assertEqual(rows[3]["pa"]["value"], 495)

    def test_filters_sort_and_page(self):
        body = self.get("/api/v2/batting/advanced?season=2025&limit=2")
        self.assertEqual([x["player_id"] for x in body["data"]], [3, 5])  # AB 내림차순
        self.assertEqual(body["page"], {"limit": 2, "offset": 0, "total": 6, "next_offset": 2})
        last = self.get("/api/v2/batting/advanced?season=2025&limit=2&offset=4")
        self.assertEqual(last["page"]["next_offset"], None)
        self.assertEqual(set(self.rows(team="팀B")), {4, 5, 6})
        self.assertEqual(set(self.rows(qualified="true")), {1, 3, 5})
        self.assertEqual(body["status_counts"]["bb_pct"], {ba.CALCULATED: 3, ba.UNAVAILABLE: 3})
        self.get("/api/v2/batting/advanced?season=2025&limit=0", 422)
        self.get("/api/v2/batting/advanced?season=1900", 422)
        self.get("/api/v2/batting/advanced", 422)

    def test_season_without_data_is_predictable(self):
        body = self.get("/api/v2/batting/advanced?season=2024")
        self.assertEqual((body["data"], body["reason"], body["page"]["total"]), ([], "no_batting_data", 0))

    def test_query_count_does_not_grow_with_players(self):
        statements = []
        listener = lambda *a: statements.append(a[2])  # noqa: E731
        event.listen(self.engine, "before_cursor_execute", listener)
        try:
            self.get("/api/v2/batting/advanced?season=2025&limit=1")
            few = len(statements)
            statements.clear()
            self.get("/api/v2/batting/advanced?season=2025&limit=200")
            many = len(statements)
        finally:
            event.remove(self.engine, "before_cursor_execute", listener)
        self.assertEqual(few, many)
        self.assertLessEqual(many, 4)  # 기록실 1 + 빌드 선택 1 + 시즌 합 1 (+ 여유)


class ProfileQueryCountTest(BattingApiBase):
    def test_profile_queries_do_not_grow_with_seasons(self):
        """Codex 교차검증 지적: 프로필이 시즌마다 빌드 선택·집계를 따로 하면 1 + 2N 쿼리 — 시즌 수와 무관해야 한다."""
        statements = []
        listener = lambda *a: statements.append(a[2])  # noqa: E731
        event.listen(self.engine, "before_cursor_execute", listener)
        try:
            tp.batting_context(self.engine, [2025], 1)
            one = len(statements)
            statements.clear()
            ctx = tp.batting_context(self.engine, list(range(2007, 2026)), 1)
            many = len(statements)
        finally:
            event.remove(self.engine, "before_cursor_execute", listener)
        self.assertEqual(one, many)
        self.assertLessEqual(many, 3)
        self.assertEqual(ctx["calc"][2025][1]["games"], 10)  # 한 번에 모아도 시즌·선수별 합은 그대로


class DbUnavailableTest(BattingApiBase):
    def test_db_failure_degrades_instead_of_failing(self):
        def boom(*a, **k):
            raise OperationalError("SELECT 1", {}, Exception("down"))
        with patch.object(self.engine, "connect", side_effect=boom):
            body = self.get("/api/v2/batting/advanced?season=2025&limit=200")
            prof = self.get("/api/v2/players/1/profile")
        rows = {r["player_id"]: r for r in body["data"]}
        self.assertEqual(len(body["meta"]["warnings"]), 2)
        self.assertEqual(rows[1]["metrics"]["iso"]["status"], ba.CALCULATED)  # CSV 만으로 되는 것은 된다
        self.assertEqual(rows[1]["metrics"]["bb_pct"]["status"], ba.UNAVAILABLE)
        self.assertEqual(rows[4]["metrics"]["babip"]["status"], ba.UNAVAILABLE)
        self.assertEqual(len(prof["meta"]["advanced"]["warnings"]), 2)


class ProfileTest(BattingApiBase):
    def test_batter_lines_gain_advanced_and_keep_existing_keys(self):
        with_adv = self.get("/api/v2/players/1/profile")
        plain = tp.profile(1)  # 엔진 없이 = 확장 전 응답
        self.assertEqual(with_adv["data"]["player"], plain["data"]["player"])
        for a, b in zip(with_adv["data"]["seasons"], plain["data"]["seasons"]):
            self.assertEqual({k: v for k, v in a.items() if k != "advanced"}, json.loads(json.dumps(b)))
            self.assertIn("advanced", a)
        self.assertEqual(with_adv["data"]["seasons"][0]["advanced"]["pa"]["basis"], ba.PA_KBO)
        self.assertEqual(with_adv["meta"]["sources"], json.loads(json.dumps(plain["meta"]["sources"])))
        self.assertIn("rules", with_adv["meta"]["advanced"])

    def test_cached_lines_are_not_mutated(self):
        self.get("/api/v2/players/1/profile")
        self.assertNotIn("advanced", tp.naver_lines(2025, "batter")[0])

    def test_pitcher_lines_have_no_advanced(self):
        prof = self.get("/api/v2/players/7/profile")
        roles = {s["role"]: s for s in prof["data"]["seasons"]}
        self.assertEqual(set(roles), {"pitcher"})  # 투수의 타격 줄은 원래 빠진다
        self.assertNotIn("advanced", roles["pitcher"])
        self.assertNotIn("advanced", prof["meta"])
        self.get("/api/v2/players/999/profile", 404)


if __name__ == "__main__":
    unittest.main()
