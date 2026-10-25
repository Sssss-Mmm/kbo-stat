"""/api/v2 PostgreSQL 실데이터 통합 테스트 (읽기 전용). V2_PG_TESTS=1 일 때만 돈다.

대상은 TEST_DATABASE_URL 로만 명시한다 — PostgreSQL 이고 DB 이름이 `_test` 로 끝나야 하며, 호스트:포트가
TEST_DATABASE_ALLOWED_HOSTS 에 있어야 한다(database/__init__.py — 운영 백업을 복원한 격리 DB 등).
KBO_ENV=test 로 실행한다 — 운영·개발용 DATABASE_URL·.env 는 쓰지 않는다(database/__init__.py). 조건이 안 맞으면 접속하지 않고 실패한다.

실행 예(격리 네트워크의 테스트 전용 DB):
  docker run --rm --network <격리 네트워크> -v "$PWD/src:/app/src:ro" -v <data>:/data:ro -e KBO_DATA_DIR=/data \
    -e KBO_ENV=test -e V2_PG_TESTS=1 -e TEST_DATABASE_URL=postgresql://t:<pw>@<db 호스트>:5432/kbo_p3a_test \
    -e TEST_DATABASE_ALLOWED_HOSTS=<db 호스트>:5432 <백엔드 이미지> \
    python -m unittest tests.test_v2_pg -v
"""
import os
import unittest
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import make_url

RUN = os.environ.get("V2_PG_TESTS") == "1"


def check_test_pg_url(url):
    """실제 DB 에 접속하는 테스트의 대상이 테스트 전용인지 — 아니면 접속 전에 이유를 돌려준다(None 이면 통과)."""
    if not url:
        return "TEST_DATABASE_URL 이 없다 — 테스트 전용 PostgreSQL 을 명시해야 한다"
    parsed = make_url(url)
    if not parsed.drivername.startswith("postgresql"):
        return f"PostgreSQL 이 아니다({parsed.drivername})"
    if not (parsed.database or "").endswith("_test"):
        return f"DB 이름 '{parsed.database}' 이 '_test' 로 끝나지 않는다 — 테스트 전용 DB 만 허용"
    return None


def setUpModule():
    if RUN:
        problem = check_test_pg_url(os.environ.get("TEST_DATABASE_URL"))
        if problem:
            raise RuntimeError(f"V2_PG_TESTS=1 이지만 {problem}")


class TestPgUrlGuardTest(unittest.TestCase):
    def test_only_explicit_postgres_test_db_is_allowed(self):
        self.assertIsNotNone(check_test_pg_url(None))
        self.assertIsNotNone(check_test_pg_url("sqlite://"))
        self.assertIsNotNone(check_test_pg_url("postgresql://u:p@localhost:5432/kbo_dashboard"))
        self.assertIsNotNone(check_test_pg_url("postgresql://u:p@localhost:5432/test_kbo"))
        self.assertIsNone(check_test_pg_url("postgresql://u:p@db:5432/kbo_p3a_test"))


@unittest.skipUnless(RUN, "V2_PG_TESTS=1 일 때만(실제 PostgreSQL 필요)")
class V2PostgresTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        import main
        from database import engine

        cls.engine = engine
        cls.client = TestClient(main.app)

    def get(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.text[:300])
        return response.json()

    def scalar(self, sql, **params):
        with self.engine.connect() as conn:
            return conn.execute(text(sql), params).scalar_one()

    def test_box_keeps_official_and_unproven_calc_apart(self):
        box = self.get("/api/v2/games/20250719HHKT0/box")  # 6회초 1아웃 콜드
        won = next(p for p in box["data"]["pitchers"] if p["player_id"] == 54063)
        self.assertEqual(won["official"]["outs"], 3)
        self.assertEqual(won["official"]["source"], "naver_boxscore")
        self.assertIsNone(won["calc"]["outs"])
        self.assertEqual(won["verification"]["Outs"], "naver_conflict")
        self.assertEqual(won["kbo"]["status"], "not_checked")
        self.assertIn("called_game", {e["kind"] for e in box["data"]["exceptions"]})

    def test_backfilled_data_is_not_shown_as_held_earlier(self):
        # 2026-10 에 받은 원본·빌드는 2025 시점에 없었다 — 그때 기준으론 경기·선수 기록 자체가 없다(404)
        for url in ("/api/v2/players/55730/season?season=2025&as_of=2025-10-31T23:59:59%2B09:00",
                    "/api/v2/games/20250719HHKT0/box?as_of=2025-07-20T00:00:00%2B09:00"):
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_season_totals_match_independent_sql_and_season_page(self):
        pid = 55730  # 폰세
        season = self.get(f"/api/v2/players/{pid}/season?season=2025&role=pitcher")["data"]["roles"]["pitcher"]
        direct = self.scalar("""SELECT SUM(outs) FROM official.game_pitcher_line_current l
                                JOIN ref.game g ON g.game_id = l.game_id WHERE l.player_id = :p AND g.season = 2025""", p=pid)
        self.assertEqual(season["official"]["totals"]["outs"], direct)
        page = Path("/app/data/processed/kbo_naver_pitchers_2025.csv")  # 네이버 시즌 누적(별도 수집)
        if page.exists():
            ip = pd.read_csv(page, encoding="utf-8-sig").set_index("PlayerId").loc[pid, "IP"]
            whole, _, frac = str(ip).partition(" ")
            self.assertEqual(season["official"]["totals"]["outs"], int(whole) * 3 + (int(frac[0]) if frac else 0))

    def test_through_date_limits_games(self):
        full = self.get("/api/v2/players/55730/season?season=2025&role=pitcher")["data"]["roles"]["pitcher"]
        half = self.get("/api/v2/players/55730/season?season=2025&role=pitcher&through_date=2025-06-30")
        part = half["data"]["roles"]["pitcher"]["official"]
        games = self.scalar("""SELECT COUNT(*) FROM official.game_pitcher_line_current l JOIN ref.game g
                               ON g.game_id = l.game_id WHERE l.player_id = 55730 AND g.game_date <= '2025-06-30'""")
        self.assertEqual(part["games"], games)
        self.assertLess(part["games"], full["official"]["games"])

    def test_leaders_match_direct_sql(self):
        top = self.get("/api/v2/leaders?season=2025&role=pitcher&stat=so&limit=5")["data"]["leaders"]
        with self.engine.connect() as conn:
            direct = conn.execute(text("""SELECT l.player_id, SUM(l.so) AS so FROM official.game_pitcher_line_current l
                                          GROUP BY l.player_id ORDER BY so DESC, l.player_id LIMIT 5""")).all()
        self.assertEqual([(r["player_id"], r["value"]) for r in top], [tuple(d) for d in direct])

    def test_qualified_era_uses_team_games(self):
        lead = self.get("/api/v2/leaders?season=2025&role=pitcher&stat=era&qualified=true&limit=100")["data"]
        self.assertGreater(len(lead["leaders"]), 0)
        values = [r["value"] for r in lead["leaders"]]
        self.assertEqual(values, sorted(values))  # 낮을수록 위

    def test_data_quality(self):
        dq = self.get("/api/v2/data-quality?season=2025")["data"]
        self.assertEqual({k: dq["coverage"][k] for k in ("final_games", "official_raw_games", "calc_games")},
                         {"final_games": 720, "official_raw_games": 720, "calc_games": 720})
        self.assertEqual(dq["kbo_verified"], 0)
        self.assertEqual(dq["collection"]["policy"]["kbo_official_site"], "disabled_pending_approval")


if __name__ == "__main__":
    unittest.main()


# 원본 순위가 정규시즌 승률 순서와 다른 시즌 — 모두 그 해 포스트시즌 결과 방향(원본 = 최종 순위). 고치지 않고 differs.
POSTSEASON_ORDER = {2001, 2002, 2003, 2006, 2011, 2013, 2015, 2018, 2019, 2020, 2021, 2022}


@unittest.skipUnless(RUN, "V2_PG_TESTS=1 일 때만(실제 PostgreSQL 필요)")
class SeasonPostgresTest(unittest.TestCase):
    setUpClass = classmethod(V2PostgresTest.setUpClass.__func__)
    get, scalar = V2PostgresTest.get, V2PostgresTest.scalar

    def test_every_season_recomputes_source_standings(self):
        for season in range(2001, 2027):
            body = self.get(f"/api/v2/standings?season={season}")
            self.assertEqual(body["coverage"], "season_final", season)
            self.assertEqual(body["check_summary"]["record_mismatch"], 0, season)   # 승·패·무·승률·승차·최근10·연속·홈·원정
            self.assertEqual(body["check_summary"]["missing_in_source"], 0, season)
            self.assertEqual(body["check_summary"]["rank_differs"] > 0, season in POSTSEASON_ORDER, season)
            # 계산 승·패·무 = v1 이 쓰는 public.standings (migrate.py 의 독립 적재 경로) — 읽기만 한다
            with self.engine.connect() as conn:
                public = {tuple(r) for r in conn.execute(text(
                    "SELECT t.name, s.wins, s.losses, s.draws FROM standings s JOIN teams t ON t.id = s.team_id "
                    "WHERE s.season = :s"), {"s": season})}
            self.assertEqual({(r["team"], r["wins"], r["losses"], r["draws"]) for r in body["data"]}, public, season)

    def test_rules_examples(self):
        b2009 = self.get("/api/v2/standings?season=2009")
        self.assertEqual(b2009["rules"]["pct"], "wins/(wins+losses+draws)")
        lotte = next(r for r in self.get("/api/v2/standings?season=2011")["data"] if r["team"] == "롯데")
        self.assertEqual((lotte["wins"], lotte["losses"], lotte["pct"], lotte["rank"], lotte["source"]["rank"]),
                         (72, 56, 0.563, 2, 3))   # .5625 사사오입 · 정규 2위 · 원본(최종) 3위
        self.assertEqual(lotte["check"]["rank"], "differs")
        lg_hh = [r for r in self.get("/api/v2/standings?season=2011")["data"] if r["team"] in ("LG", "한화")]
        self.assertEqual({(r["rank"], r["source"]["rank"], r["tie"]) for r in lg_hh}, {(6, 6, True)})  # 공동 6위
        ssg = next(r for r in self.get("/api/v2/standings?season=2024")["data"] if r["team"] == "SSG")
        self.assertEqual((ssg["rank"], ssg["source"]["rank"], ssg["check"]["rank"]), (5, 6, "tie_resolved_by_source"))

    def test_through_date_uses_only_finished_games(self):
        body = self.get("/api/v2/standings?season=2025&through_date=2025-06-30")
        played = self.scalar("""SELECT COUNT(*) FROM official.schedule_game_current
                                WHERE season = 2025 AND status IN ('final','tie') AND game_date <= '2025-06-30'""")
        self.assertEqual(sum(r["games"] for r in body["data"]), 2 * played)
        self.assertEqual(body["coverage"], "partial")

    def test_schedule_and_box_links(self):
        self.assertEqual(self.get("/api/v2/seasons")["data"][-1]["season"], 2026)
        day = self.get("/api/v2/schedule?date=2025-07-19")["data"]
        self.assertTrue(day and all(g["has_box"] == (g["status"] in ("final", "tie")) for g in day))
        self.assertFalse(any(g["has_box"] for g in self.get("/api/v2/schedule?date=2026-07-19")["data"]))  # 2026 박스 없음
        boxed = self.scalar("SELECT COUNT(DISTINCT game_id) FROM ingest.raw_record WHERE season = 2025")
        s2025 = next(e for e in self.get("/api/v2/seasons")["data"] if e["season"] == 2025)
        self.assertEqual(s2025["box_games"], boxed)
        self.assertEqual(self.get("/api/v2/schedule?date=2026-11-01")["reason"], "out_of_range")
        self.assertEqual(self.get("/api/v2/schedule?date=2000-05-01")["reason"], "season_not_held")
