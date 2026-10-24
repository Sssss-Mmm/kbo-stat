"""P2-C 시즌·일정·순위 — 순수 계산과 /api/v2/{seasons,schedule,standings,home} (SQLite 메모리 DB).

실데이터 2001–2026 대조는 tests/test_v2_pg.py (V2_PG_TESTS=1).
"""
import unittest
from datetime import date, datetime
from fractions import Fraction
from unittest.mock import patch

from fastapi.testclient import TestClient

from migrate_records import schedule_status
from models.records import Build, RawRecord, ScheduleGame, SeasonStanding
from services import season_service as ss
from tests.test_v2_api import make_engine

AT = datetime(2026, 10, 22, 2, 0)


def g(day, away, home, a, h, status="final", dh=0, reason=None, gid=True):
    return dict(game_date=day, dh=dh if gid else None, game_time="18:30", status=status, away_team=away, home_team=home,
                away_score=a, home_score=h, cancel_reason=reason)


class PureTest(unittest.TestCase):
    def test_status_from_source(self):
        self.assertEqual(schedule_status("final", "-", 3, 2), ("final", None))
        self.assertEqual(schedule_status("final", None, 4, 4), ("tie", None))
        self.assertEqual(schedule_status("scheduled", "우천취소", None, None), ("canceled", "우천취소"))
        self.assertEqual(schedule_status("scheduled", "-", None, None), ("scheduled", None))

    def test_pct_rules_and_half_up(self):
        # 2009·2010 은 무승부를 분모에 넣는다(KIA 2009: 81승 48패 4무 → .609)
        self.assertEqual(ss.round_half_up(ss.pct_exact(2009, 81, 48, 4)), 0.609)
        self.assertEqual(ss.round_half_up(ss.pct_exact(2011, 81, 48, 4)), 0.628)
        # 사사오입: 2011 롯데 72승 56패 = .5625 → .563 (기본 round 는 .562)
        self.assertEqual(ss.pct_exact(2011, 72, 56, 5), Fraction(9, 16))
        self.assertEqual(ss.round_half_up(ss.pct_exact(2011, 72, 56, 5)), 0.563)
        self.assertEqual(round(72 / 128, 3), 0.562)
        self.assertIsNone(ss.pct_exact(2025, 0, 0, 3))

    def test_standings_tie_cancel_doubleheader(self):
        games = [g("2025-04-01", "A", "B", 3, 1), g("2025-04-01", "C", "D", 2, 2, status="tie"),
                 g("2025-04-02", "B", "A", 5, 4, dh=1), g("2025-04-02", "B", "A", 0, 1, dh=2),
                 g("2025-04-03", "C", "D", None, None, status="canceled", reason="우천취소", gid=False),
                 g("2025-04-04", "D", "C", 1, 0), g("2025-04-05", "A", "D", None, None, status="scheduled")]
        rows = {r["team"]: r for r in ss.compute_standings(2025, games)}
        self.assertEqual((rows["A"]["wins"], rows["A"]["losses"], rows["A"]["draws"]), (2, 1, 0))
        self.assertEqual(rows["A"]["streak"], "1승")  # 더블헤더 2차전(dh=2)이 마지막
        self.assertEqual(rows["C"]["streak"], "1패")  # 무승부는 연속을 끊지 않는다
        self.assertEqual(rows["C"]["last10"], "0승1무1패")
        self.assertEqual(rows["A"]["home"], "1-0-1")   # 승-무-패
        self.assertEqual((rows["D"]["pct"], rows["D"]["rank"]), (1.0, 1))  # 1승 1무 — 무승부는 승률 분모에서 빠진다
        self.assertEqual([rows[t]["rank"] for t in "ABC"], [2, 3, 4])
        self.assertEqual(rows["A"]["games_behind"], 0.0)  # D 보다 1승 많고 1패 많다
        self.assertFalse(any(r["tie"] for r in rows.values()))

    def test_check_against_source(self):
        games = [g("2011-04-01", "A", "B", 3, 1), g("2011-04-02", "C", "B", 3, 1),
                 g("2011-04-03", "A", "C", 2, 2, status="tie")]
        rows = ss.compute_standings(2011, games)          # A·C 1승 1무(동률 1.000), B 2패
        src = [dict(team=t, rank=k, games=2, wins=w, losses=l, draws=d, pct=p, games_behind=gb, last10=None,
                    streak=None, home_record=None, away_record=None)
               for t, k, w, l, d, p, gb in (("C", 1, 1, 0, 1, 1.0, 0), ("A", 2, 1, 0, 1, 1.0, 0), ("B", 3, 0, 2, 0, 0.0, 1.5))]
        for r in rows:  # 최근10·연속·홈원정은 이 테스트에서 비교 대상에서 뺀다
            for k in ("last10", "streak", "home", "away"):
                r[k] = None
        summary = ss.check_against_source(rows, src)
        by = {r["team"]: r for r in rows}
        self.assertEqual((by["A"]["rank"], by["C"]["rank"], by["A"]["tie"]), (1, 1, True))
        self.assertEqual(by["A"]["check"]["rank"], "tie_resolved_by_source")  # 계산 공동 1위, 원본 2위(상대전적 등)
        self.assertEqual(by["C"]["check"]["rank"], "match")
        self.assertEqual(summary["record_mismatch"], 0)
        # 원본 순위가 승률과 모순(포스트시즌 반영 최종 순위) → 고치지 않고 differs, 승차 기준은 원본 1위
        src[2].update(rank=1, games_behind=0)
        src[0].update(rank=3, games_behind=-1.5)
        src[1].update(games_behind=-1.5)
        summary = ss.check_against_source(rows, src)
        by = {r["team"]: r for r in rows}
        self.assertEqual(by["B"]["check"]["rank"], "differs")
        self.assertEqual((by["B"]["source"]["rank"], by["B"]["rank"]), (1, 3))  # 원본·계산 값 그대로 둘 다 보존
        self.assertEqual(by["C"]["source"]["games_behind_basis"], "source_rank_1")
        self.assertEqual(by["C"]["check"]["fields"], [])
        self.assertEqual(summary["rank_differs"], 2)


def seed(conn):
    conn.execute(Build.__table__.insert(), [
        dict(build_id="s25", kind="schedule", season=2025, calc_rule="", source_file="kbo_schedule_2025.csv", row_count=5,
             loaded_at=AT),
        dict(build_id="r25", kind="season_standing", season=2025, calc_rule="", source_file="kbo_team_rank_2025.csv",
             row_count=2, loaded_at=AT)])
    rows = [g(date(2025, 3, 22), "LG", "두산", 3, 1), g(date(2025, 3, 23), "LG", "두산", 2, 2, status="tie"),
            g(date(2025, 3, 25), "두산", "LG", None, None, status="canceled", reason="우천취소", gid=False),
            g(date(2025, 3, 26), "두산", "LG", 5, 4, dh=1), g(date(2025, 3, 26), "두산", "LG", 1, 0, dh=2)]
    ids = ["20250322LGOB0", "20250323LGOB0", None, "20250326OBLG1", "20250326OBLG2"]
    conn.execute(ScheduleGame.__table__.insert(), [
        dict(r, build_id="s25", row_no=i, season=2025, weekday="토", status_raw="final" if r["status"] in ("final", "tie")
             else "scheduled", ballpark="잠실", game_id=ids[i], source="kbo_site_crawl", collected_at=AT)
        for i, r in enumerate(rows)])
    std = dict(season=2025, games=4, draws=1, last10=None, streak=None, home_record=None, away_record=None,
               source="kbo_site_crawl", collected_at=AT, build_id="r25")
    conn.execute(SeasonStanding.__table__.insert(), [
        dict(std, team="두산", rank=1, wins=2, losses=1, pct=0.667, games_behind=0),
        dict(std, team="LG", rank=2, wins=1, losses=2, pct=0.333, games_behind=1)])
    conn.execute(RawRecord.__table__.insert(), [dict(raw_file="2025/20250322LGOB0/a.json", source="naver_boxscore",
                                                     season=2025, game_id="20250322LGOB0", url="u", fetched_at=AT,
                                                     sha256="x", payload={})])


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = make_engine()
        with cls.engine.begin() as conn:
            seed(conn)
        import routers.v2 as router
        import main
        cls.patch = patch.object(router, "engine", cls.engine)
        cls.patch.start()
        cls.client = TestClient(main.app)

    @classmethod
    def tearDownClass(cls):
        cls.patch.stop()

    def get(self, url, code=200):
        r = self.client.get(url)
        self.assertEqual(r.status_code, code, r.text)
        return r.json()

    def test_seasons(self):
        body = self.get("/api/v2/seasons")
        s = body["data"][0]
        self.assertEqual((s["season"], s["box_games"], s["postseason"]), (2025, 1, "not_collected"))
        self.assertEqual((s["schedule"]["played"], s["schedule"]["ties"], s["schedule"]["canceled"]), (4, 1, 1))
        self.assertEqual(s["schedule"]["last_played_date"], "2025-03-26")
        self.assertEqual(body["meta"]["publication"], "private_pending_rights")
        self.assertEqual(body["meta"]["updates"], "paused")

    def test_schedule_day_states(self):
        day = self.get("/api/v2/schedule?date=2025-03-26")
        self.assertEqual([x["doubleheader"] for x in day["data"]], [1, 2])
        self.assertFalse(any(x["has_box"] for x in day["data"]))      # 박스스코어 없음 → 링크 없음
        self.assertTrue(self.get("/api/v2/schedule?date=2025-03-22")["data"][0]["has_box"])
        cancel = self.get("/api/v2/schedule?date=2025-03-25")["data"][0]
        self.assertEqual((cancel["status"], cancel["cancel_reason"], cancel["game_id"]), ("canceled", "우천취소", None))
        self.assertEqual(self.get("/api/v2/schedule?date=2025-03-23")["data"][0]["status"], "tie")
        self.assertEqual(self.get("/api/v2/schedule?date=2025-03-24")["reason"], "no_games")
        self.assertEqual(self.get("/api/v2/schedule?date=2025-10-30")["reason"], "out_of_range")
        self.assertEqual(self.get("/api/v2/schedule?date=2025-03-01")["reason"], "out_of_range")
        self.assertEqual(self.get("/api/v2/schedule?date=2024-05-01")["reason"], "season_not_held")
        self.assertEqual(len(self.get("/api/v2/schedule?season=2025&month=3")["data"]), 5)
        self.assertEqual(self.get("/api/v2/schedule?season=2025&month=11")["reason"], "out_of_range")
        self.get("/api/v2/schedule", 422)
        self.get("/api/v2/schedule?date=2025-03-26&season=2025", 422)

    def test_standings_final_and_through(self):
        body = self.get("/api/v2/standings?season=2025")
        top = body["data"][0]
        self.assertEqual((top["team"], top["wins"], top["losses"], top["draws"], top["pct"]), ("두산", 2, 1, 1, 0.667))
        # 원본 픽스처는 최근10·연속·홈원정을 비워 둔다 → 그 항목만 불일치, 순위는 일치
        self.assertEqual(top["check"], {"status": "mismatch", "fields": ["last10", "streak", "home", "away"],
                                        "rank": "match"})
        self.assertEqual(top["source"]["rank"], 1)
        self.assertEqual(body["coverage"], "season_final")
        self.assertEqual(body["rules"]["pct"], "wins/(wins+losses)")
        # 3/23 까지: LG 1승 1무, 두산 1패 1무 — 원본(시즌 최종)과 비교하지 않는다
        part = self.get("/api/v2/standings?season=2025&through_date=2025-03-23")
        self.assertEqual(part["coverage"], "partial")
        self.assertEqual((part["data"][0]["team"], part["data"][0]["wins"]), ("LG", 1))
        self.assertEqual(part["data"][0]["check"], {"status": "not_compared"})
        self.assertIsNone(part["check_summary"])
        self.assertEqual(self.get("/api/v2/standings?season=2025&through_date=2025-03-01")["coverage"],
                         "before_first_game")
        self.assertEqual(self.get("/api/v2/standings?season=2025&through_date=2025-12-31")["coverage"],
                         "after_last_played")
        self.get("/api/v2/standings?season=2024", 404)

    def test_home(self):
        body = self.get("/api/v2/home")
        self.assertEqual(body["season"], 2025)
        self.assertEqual(body["banner"]["last_played_date"], "2025-03-26")
        self.assertEqual(body["banner"]["updates"], "paused")
        self.assertEqual(len(body["last_games"]["games"]), 2)
        self.assertEqual(body["standings"][0]["source_rank"], 1)
        self.get("/api/v2/home?season=2024", 404)


class EmptyBuildTest(unittest.TestCase):
    """예전 적재로 남은 0행 원본 빌드가 최신이어도 500 대신 '자료 없음'(Codex 지적 후속)."""

    def test_empty_reference_build_reads_as_not_held(self):
        engine = make_engine()
        with engine.begin() as conn:
            conn.execute(Build.__table__.insert(), [
                dict(build_id=k[:3] + "24", kind=k, season=2024, calc_rule="", source_file="x.csv", row_count=0, loaded_at=AT)
                for k in ("schedule", "season_standing")])
            entry = ss.seasons(conn)["data"][0]
            self.assertEqual((entry["season"], entry["schedule"], entry["standings"]), (2024, None, None))
            self.assertEqual(ss.schedule(conn, None, 2024, 4)["reason"], "season_not_held")
            self.assertEqual(ss.schedule(conn, date(2024, 4, 2), None, None)["reason"], "season_not_held")
            self.assertIsNone(ss.standings(conn, 2024, None))
            self.assertIsNone(ss.home(conn, 2024))


if __name__ == "__main__":
    unittest.main()
