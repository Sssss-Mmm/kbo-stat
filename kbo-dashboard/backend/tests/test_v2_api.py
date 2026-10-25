"""/api/v2 단위 테스트 — SQLite 메모리 DB 에 ref·ingest·official·derived·verify 를 ATTACH 해 같은 SQL 을 돌린다.

PostgreSQL 실데이터 통합 테스트는 tests/test_v2_pg.py (V2_PG_TESTS=1 일 때만).
"""
import unittest
from datetime import date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from models.records import (SCHEMAS, Build, Game, GameBatterLine, GamePitcherLine, PlayerGame, PlayerGameCheck,
                            Player, PlayerName, RawRecord, RecordsBase, VerifyException)
from services import v2_service as v2

G1, G2 = "20250401LGOB0", "20250402LGOB0"
T = lambda h: datetime(2026, 10, 23, h)  # noqa: E731 — 수집·적재 시각(UTC, 시간만 바꿔 쓴다)


def make_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def attach(conn, _):
        for schema in SCHEMAS:
            conn.execute(f"ATTACH DATABASE ':memory:' AS {schema}")

    RecordsBase.metadata.create_all(engine)
    return engine


def line(raw, game, pid, name, team, side, **stats):
    return dict(raw_file=raw, player_id=pid, source="naver_boxscore", season=2025, game_id=game, fetched_at=stats.pop("at"),
                sha256="x", game_status_code="4", side=side, team=team, player=name, team_sum_mismatch="", **stats)


def calc(build, game, day, pid, name, role, **stats):
    base = dict(build_id=build, calc_rule="r1", role=role, player_id=pid, game_id=game, season=2025, game_date=day,
                dh=0, player=name, team="LG", opponent="두산", home_away="away", pa_complete=True, stats_complete=True,
                outs_complete=True, result_unknown=0, pa_uncertain=0, attribution_uncertain=0)
    return {**base, **stats}


def seed(conn):
    def ins(model, rows):  # executemany 는 줄마다 같은 열이어야 한다 — 빠진 열은 NULL
        cols = {k for r in rows for k in r}
        conn.execute(model.__table__.insert(), [{c: r.get(c) for c in cols} for r in rows])
    ins(Game, [dict(game_id=G1, season=2025, game_date=date(2025, 4, 1), dh=0, away_team="LG", home_team="두산",
                    status="final", away_score=3, home_score=2, ballpark="잠실", source="kbo_schedule"),
               dict(game_id=G2, season=2025, game_date=date(2025, 4, 2), dh=0, away_team="LG", home_team="두산",
                    status="final", away_score=1, home_score=4, ballpark="잠실", source="kbo_schedule")])
    ins(Player, [dict(player_id=90, name="투수A"), dict(player_id=91, name="투수B"), dict(player_id=1, name="타자1"),
                 dict(player_id=2, name="타자2")])
    ins(PlayerName, [dict(player_id=90, name="투수A", source="naver_boxscore")])
    ins(RawRecord, [dict(raw_file=f"2025/{G1}/a.json", source="naver_boxscore", season=2025, game_id=G1, url="u",
                         fetched_at=T(1), sha256="x", payload={}),
                    dict(raw_file=f"2025/{G1}/b.json", source="naver_boxscore", season=2025, game_id=G1, url="u",
                         fetched_at=T(5), sha256="y", payload={}),  # 다시 받은 원본: 투수B 가 빠졌다
                    dict(raw_file=f"2025/{G2}/a.json", source="naver_boxscore", season=2025, game_id=G2, url="u",
                         fetched_at=T(1), sha256="z", payload={})])
    a, b, c = f"2025/{G1}/a.json", f"2025/{G1}/b.json", f"2025/{G2}/a.json"
    ins(GamePitcherLine, [
        line(a, G1, 90, "투수A", "LG", "away", at=T(1), ord=1, ip="5", outs=15, bf=20, h=4, bb=1, so=5, er=2, r=2),
        line(a, G1, 91, "투수B", "LG", "away", at=T(1), ord=2, ip="4", outs=12, bf=14, h=2, bb=0, so=3, er=0, r=0),
        line(b, G1, 90, "투수A", "LG", "away", at=T(5), ord=1, ip="9", outs=27, bf=33, h=5, bb=1, so=9, er=2, r=2),
        line(c, G2, 90, "투수A", "LG", "away", at=T(1), ord=1, ip="0", outs=0, bf=3, h=3, bb=0, so=0, er=3, r=3),
        line(c, G2, 91, "투수B", "LG", "away", at=T(1), ord=2, ip="6", outs=18, bf=22, h=3, bb=2, so=7, er=1, r=1),
    ])
    ins(GameBatterLine, [
        line(a, G1, 1, "타자1", "LG", "away", at=T(1), bat_order=1, ab=4, h=2, hr=1, bb=0, so=1),
        line(b, G1, 1, "타자1", "LG", "away", at=T(5), bat_order=1, ab=4, h=2, hr=1, bb=0, so=1),
        line(b, G1, 2, "타자2", "LG", "away", at=T(5), bat_order=2, ab=0, h=0, hr=0, bb=1, so=0),
        line(c, G2, 1, "타자1", "LG", "away", at=T(1), bat_order=1, ab=3, h=0, hr=0, bb=1, so=2),
    ])
    ins(Build, [dict(build_id="old", kind="player_game", season=2025, calc_rule="r0", source_file="f", row_count=1,
                     loaded_at=T(2)),
                dict(build_id="new", kind="player_game", season=2025, calc_rule="r1", source_file="f", row_count=4,
                     loaded_at=T(6)),
                dict(build_id="chk", kind="player_game_check", season=2025, calc_rule="r1", source_file="f",
                     row_count=2, loaded_at=T(6), basis_build_id="new"),
                dict(build_id="exc", kind="verify_exception", season=2025, calc_rule="r1", source_file="f",
                     row_count=1, loaded_at=T(6), basis_build_id="new"),
                # 옛 계산 빌드를 기준으로 만든 대조가 더 늦게 올라왔다 — 새 계산 옆에 붙으면 안 된다
                dict(build_id="chk-old", kind="player_game_check", season=2025, calc_rule="r0", source_file="f",
                     row_count=1, loaded_at=T(7), basis_build_id="old")])
    ins(PlayerGame, [
        calc("old", G1, date(2025, 4, 1), 90, "투수A", "pitcher", outs=27, bf=33, h=5, bb=1, hbp=0, so=9),
        calc("new", G1, date(2025, 4, 1), 90, "투수A", "pitcher", outs=None, outs_complete=False, bf=33, h=5, bb=1,
             hbp=0, so=9),
        calc("new", G2, date(2025, 4, 2), 90, "투수A", "pitcher", outs=0, bf=3, h=3, bb=0, hbp=0, so=0),
        calc("new", G1, date(2025, 4, 1), 1, "타자1", "batter", pa=4, ab=4, h=2, b2=0, b3=0, hr=1, bb=0, hbp=0, sf=0,
             sh=0, so=1),
        calc("new", G2, date(2025, 4, 2), 1, "타자1", "batter", pa=4, ab=3, h=0, b2=0, b3=0, hr=0, bb=1, hbp=0, sf=0,
             sh=0, so=2, stats_complete=False),
    ])
    ins(PlayerGameCheck, [
        dict(build_id="chk", calc_rule="r1", external_raw_file=b, role="pitcher", player_id=90, metric="Outs",
             season=2025, game_id=G1, player="투수A", calc_value=27, calc_proven=False, external_value=27,
             external_source="naver_boxscore", external_fetched_at=T(5), status="naver_verified", checked_at=T(6)),
        dict(build_id="chk", calc_rule="r1", external_raw_file=b, role="pitcher", player_id=90, metric="SO",
             season=2025, game_id=G1, player="투수A", calc_value=9, calc_proven=True, external_value=9,
             external_source="naver_boxscore", external_fetched_at=T(5), status="observed_naver_match", checked_at=T(6)),
    ])
    ins(PlayerGameCheck, [dict(build_id="chk-old", calc_rule="r0", external_raw_file=b, role="pitcher", player_id=90,
                               metric="Outs", season=2025, game_id=G1, player="투수A", calc_value=27, calc_proven=True,
                               external_value=27, external_source="naver_boxscore", external_fetched_at=T(5),
                               status="observed_naver_match", checked_at=T(7))])
    ins(VerifyException, [dict(build_id="exc", row_no=0, calc_rule="r1", season=2025, game_id=G1, kind="walkoff",
                               role=None, player_id=None, player="", count=1, detail="", checked_at=T(6))])


class V2Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = make_engine()
        with cls.engine.begin() as conn:
            seed(conn)

    def setUp(self):
        self.conn = self.engine.connect()
        self.addCleanup(self.conn.close)


class PureTest(unittest.TestCase):
    def test_innings_from_outs(self):
        self.assertEqual([v2.ip_text(n) for n in (0, 1, 2, 3, 17, None)], ["0", "0 1/3", "0 2/3", "1", "5 2/3", None])

    def test_zero_denominators_are_none(self):
        self.assertEqual(v2.rates("pitcher", {"outs": 0, "er": 3, "h": 3, "bb": 0}), {"era": None, "whip": None})
        self.assertEqual(v2.rates("batter", {"h": 0, "ab": 0}), {"avg": None})
        self.assertEqual(v2.rates("pitcher", {"outs": 27, "er": 2, "h": 5, "bb": 1}), {"era": 2.0, "whip": 0.67})


class BoxTest(V2Base):
    def test_latest_raw_only_and_calc_kept_separate(self):
        box = v2.game_box(self.conn, G1, None)
        pitchers = {p["player_id"]: p for p in box["data"]["pitchers"]}
        self.assertEqual(box["data"]["official"]["raw_file"], f"2025/{G1}/b.json")
        self.assertNotIn(91, pitchers)  # 새 원본에서 빠진 선수는 현재 기록에 없다
        self.assertEqual(pitchers[90]["official"]["outs"], 27)
        self.assertEqual(pitchers[90]["official"]["ip_from_outs"], "9")
        self.assertIsNone(pitchers[90]["calc"]["outs"])  # 미확정 계산값은 null 그대로
        self.assertFalse(pitchers[90]["calc"]["outs_complete"])
        self.assertEqual(pitchers[90]["verification"], {"Outs": "naver_verified", "SO": "observed_naver_match"})
        self.assertEqual(pitchers[90]["kbo"], {"status": "not_checked"})
        self.assertEqual(box["data"]["exceptions"][0]["kind"], "walkoff")
        self.assertEqual(box["meta"]["kbo_direct_verification"], "not_available")

    def test_as_of_picks_what_was_actually_held_then(self):
        then = v2.game_box(self.conn, G1, T(3))  # 두 번째 원본·새 빌드 이전
        self.assertEqual(then["data"]["official"]["raw_file"], f"2025/{G1}/a.json")
        pitchers = {p["player_id"]: p for p in then["data"]["pitchers"]}
        self.assertEqual(pitchers[91]["official"]["outs"], 12)
        self.assertEqual(pitchers[90]["calc"]["outs"], 27)  # 옛 빌드
        # 백필 이전 — 아무것도 없었다: 나중에 적재한 일정·선수 정보도 내보이지 않는다(Codex P2-A 3차)
        self.assertIsNone(v2.game_box(self.conn, G1, datetime(2025, 12, 31)))
        self.assertIsNone(v2.player_season(self.conn, 90, 2025, None, None, datetime(2025, 12, 31)))
        self.assertIsNone(v2.player_games(self.conn, 90, 2025, None, None, None, datetime(2025, 12, 31), 50, 0, "date"))

    def test_verification_comes_only_from_the_shown_calc_build(self):
        """Codex P2-A 3차: 대조 빌드는 지금 보여 주는 계산 빌드를 기준으로 만든 것만 붙인다."""
        now = {p["player_id"]: p for p in v2.game_box(self.conn, G1, None)["data"]["pitchers"]}
        self.assertEqual(now[90]["verification"]["Outs"], "naver_verified")  # chk(new 기준), 더 늦은 chk-old 아님
        then = {p["player_id"]: p for p in v2.game_box(self.conn, G1, T(3))["data"]["pitchers"]}
        self.assertEqual(then[90]["verification"], {})  # 옛 계산 빌드 시점 — 그때 연결된 대조가 없었다

    def test_later_raw_from_another_source_does_not_hide_naver_lines(self):
        """Codex 재검증 2차: 같은 경기에 더 늦은 KBO 원본이 들어와도 네이버 줄·출처 표시가 그대로."""
        from sqlalchemy import text

        self.conn.rollback()
        tx = self.conn.begin()
        try:
            self.conn.execute(text("""INSERT INTO ingest.raw_record (raw_file, source, season, game_id, url, fetched_at,
                                      sha256, payload, loaded_at) VALUES ('kbo/2025/x', 'kbo_gamecenter', 2025, :g, 'u',
                                      :at, 'k', '{}', :at)"""), {"g": G1, "at": T(9)})
            box = v2.game_box(self.conn, G1, None)
            self.assertEqual(box["data"]["official"]["raw_file"], f"2025/{G1}/b.json")
            pitchers = {p["player_id"]: p for p in box["data"]["pitchers"]}
            self.assertEqual(pitchers[90]["official"]["outs"], 27)
            season = v2.player_season(self.conn, 90, 2025, "pitcher", None, None)["data"]["roles"]["pitcher"]
            self.assertEqual(season["official"]["games"], 2)
        finally:
            tx.rollback()

    def test_verification_only_for_the_raw_shown(self):
        """Codex P2-B: 대조가 끝난 뒤 새 원본만 들어오면, 새 기록 옆에 옛 원본의 대조 상태를 붙이지 않는다."""
        from sqlalchemy import text

        self.conn.rollback()
        tx = self.conn.begin()
        try:
            self.conn.execute(text("""INSERT INTO ingest.raw_record (raw_file, source, season, game_id, url, fetched_at,
                                      sha256, payload, loaded_at) VALUES ('2025/G1/c.json', 'naver_boxscore', 2025, :g,
                                      'u', :at, 'w', '{}', :at)"""), {"g": G1, "at": T(8)})
            self.conn.execute(text("""INSERT INTO official.game_pitcher_line (raw_file, player_id, source, season, game_id,
                                      fetched_at, sha256, side, team, player, team_sum_mismatch, outs)
                                      VALUES ('2025/G1/c.json', 90, 'naver_boxscore', 2025, :g, :at, 'w', 'away', 'LG',
                                      '투수A', '', 24)"""), {"g": G1, "at": T(8)})
            pitchers = {p["player_id"]: p for p in v2.game_box(self.conn, G1, None)["data"]["pitchers"]}
            self.assertEqual(pitchers[90]["official"]["outs"], 24)
            self.assertEqual(pitchers[90]["verification"], {})  # 새 원본과는 아직 대조하지 않았다
            season = v2.player_season(self.conn, 90, 2025, "pitcher", None, None)["data"]["roles"]["pitcher"]
            self.assertEqual(season["verification"], {})
            # 데이터 품질 집계도 같은 기준(Codex 재검증): G1 의 옛 원본 대조(Outs·SO)는 빠진다
            self.assertNotIn("pitcher.Outs", v2.data_quality(self.conn, 2025, None)["data"]["verification"]["by_metric"])
        finally:
            tx.rollback()

    def test_as_of_hides_unversioned_score(self):
        then = v2.game_box(self.conn, G1, T(3))
        self.assertIsNone(then["data"]["game"]["score"])
        self.assertEqual(then["meta"]["reference_data"], "current_unversioned")
        self.assertEqual(v2.game_box(self.conn, G1, None)["data"]["game"]["score"], {"away": 3, "home": 2})

    def test_unknown_game(self):
        self.assertIsNone(v2.game_box(self.conn, "20990101ZZZZ0", None))


class PlayerTest(V2Base):
    def test_game_log_pagination_and_sort(self):
        first = v2.player_games(self.conn, 90, 2025, "pitcher", None, None, None, 1, 0, "-date")
        self.assertEqual([g["game_id"] for g in first["data"]["games"]], [G2])
        self.assertEqual(first["page"], {"limit": 1, "offset": 0, "total": 2, "next_offset": 1, "sort": "-date"})
        second = v2.player_games(self.conn, 90, 2025, "pitcher", None, None, None, 1, 1, "-date")
        self.assertEqual([g["game_id"] for g in second["data"]["games"]], [G1])
        self.assertIsNone(second["page"]["next_offset"])
        ranged = v2.player_games(self.conn, 90, 2025, None, date(2025, 4, 2), None, None, 50, 0, "date")
        self.assertEqual([g["game_id"] for g in ranged["data"]["games"]], [G2])

    def test_season_totals_through_date_and_null_outs(self):
        season = v2.player_season(self.conn, 90, 2025, "pitcher", None, None)["data"]["roles"]["pitcher"]
        self.assertEqual(season["official"]["totals"]["outs"], 27)  # G1 최신 원본 27 + G2 0
        self.assertEqual(season["official"]["totals"]["ip_from_outs"], "9")
        self.assertEqual(season["official"]["rates"], {"era": 5.0, "whip": 1.0})  # 자책 2+3, (5+3 안타 + 1 볼넷)/9이닝
        self.assertIsNone(season["calc"]["totals"]["outs"])  # 한 경기라도 미확정이면 모른다
        self.assertEqual(season["calc"]["outs_lower_bound"], 0)
        through = v2.player_season(self.conn, 90, 2025, "pitcher", date(2025, 4, 1), None)["data"]["roles"]["pitcher"]
        self.assertEqual(through["official"]["games"], 1)

    def test_batter_avg_only_when_exact(self):
        season = v2.player_season(self.conn, 1, 2025, "batter", None, None)["data"]["roles"]["batter"]
        self.assertEqual(season["official"]["rates"]["avg"], round(2 / 7, 3))
        self.assertFalse(season["calc"]["stats_exact"])
        self.assertIsNone(season["calc"]["rates"]["avg"])  # 결과 불명 타석이 있으면 비율을 만들지 않는다

    def test_unknown_player(self):
        self.assertIsNone(v2.player_season(self.conn, 999, 2025, None, None, None))


class LeadersTest(V2Base):
    def lead(self, **kw):
        args = dict(season=2025, role="pitcher", stat="so", basis="official", min_outs=0, min_ab=0, qualified=False,
                    through=None, as_of=None, limit=20, offset=0)
        args.update(kw)
        return v2.leaders(self.conn, **args)

    def test_order_and_rate_direction(self):
        so = [(r["player_id"], r["value"]) for r in self.lead()["data"]["leaders"]]
        self.assertEqual(so, [(90, 9), (91, 7)])
        era = [(r["player_id"], r["value"]) for r in self.lead(stat="era")["data"]["leaders"]]
        self.assertEqual(era, [(91, 1.5), (90, 5.0)])  # 낮을수록 위. 투수B 는 G1 최신 원본에 없어 G2 만

    def test_qualification_rules(self):
        # 팀 완료 경기 2 → 규정이닝 아웃 6. 둘 다 넘는다. min_outs 20 이면 투수B(18) 탈락.
        self.assertEqual(len(self.lead(stat="era", qualified=True)["data"]["leaders"]), 2)
        self.assertEqual([r["player_id"] for r in self.lead(stat="era", min_outs=20)["data"]["leaders"]], [90])
        bat = self.lead(role="batter", stat="avg", min_ab=5)["data"]["leaders"]
        self.assertEqual([r["player_id"] for r in bat], [1])  # 타자2 는 타수 0 — 비율 없음

    def test_calc_basis_ranks_only_exact_values(self):
        out = self.lead(basis="calc", stat="so")
        self.assertEqual(out["data"]["leaders"], [])  # 투수A 아웃 미확정 → 제외
        self.assertEqual(out["data"]["criteria"]["excluded_not_exact"], 1)

    def test_team_sum_mismatch_is_not_ranked(self):
        """Codex P2-A 2차: 원본 팀 합계가 어긋난 항목(여기선 SO)은 순위에서 빼고, 관계없는 항목은 그대로."""
        from sqlalchemy import text

        tx = self.conn.begin()
        try:
            self.conn.execute(text("UPDATE official.game_pitcher_line SET team_sum_mismatch = 'BBHP,SO' "
                                   "WHERE player_id = 91 AND game_id = :g"), {"g": G2})
            so = self.lead()
            self.assertEqual([r["player_id"] for r in so["data"]["leaders"]], [90])
            self.assertEqual(so["data"]["criteria"]["excluded_team_sum_mismatch"], 1)
            self.assertEqual(len(self.lead(stat="h")["data"]["leaders"]), 2)  # 안타는 검사 통과
            season = v2.player_season(self.conn, 91, 2025, "pitcher", None, None)["data"]["roles"]["pitcher"]
            self.assertEqual(season["official"]["team_sum_mismatch_games"], {"bbhp": 1, "so": 1})
        finally:
            tx.rollback()

    def test_missing_value_makes_total_and_rate_unknown(self):
        """Codex P2-B 2차: 한 경기 자책이 비면 시즌 자책·ERA 는 모른다 — 남은 경기만 더한 값을 내지 않는다."""
        from sqlalchemy import text

        self.conn.rollback()
        tx = self.conn.begin()
        try:
            self.conn.execute(text("UPDATE official.game_pitcher_line SET er = NULL WHERE player_id = 90 AND game_id = :g"),
                              {"g": G2})
            season = v2.player_season(self.conn, 90, 2025, "pitcher", None, None)["data"]["roles"]["pitcher"]
            self.assertIsNone(season["official"]["totals"]["er"])
            self.assertIsNone(season["official"]["rates"]["era"])
            self.assertEqual(season["official"]["totals"]["outs"], 27)  # 다른 항목은 그대로
            era = self.lead(stat="era")
            self.assertEqual([r["player_id"] for r in era["data"]["leaders"]], [91])
            self.assertEqual(era["data"]["criteria"]["excluded_missing_value"], 1)
        finally:
            tx.rollback()

    def test_team_games_follow_as_of(self):
        """Codex P2-B 3차: 규정이닝 분모는 그 시점에 가진 경기만 — 나중에 들어온 경기를 세지 않는다."""
        from sqlalchemy import text

        self.assertEqual(v2._team_games(self.conn, 2025, None, T(3)), {"LG": 2, "두산": 2})
        self.conn.rollback()
        tx = self.conn.begin()
        try:
            self.conn.execute(text("""INSERT INTO ref.game (game_id, season, game_date, dh, away_team, home_team, status,
                                      source, updated_at) VALUES ('20250403LGOB0', 2025, '2025-04-03', 0, 'LG', '두산',
                                      'final', 'kbo_schedule', :at)"""), {"at": T(9)})
            self.conn.execute(text("""INSERT INTO ingest.raw_record (raw_file, source, season, game_id, url, fetched_at,
                                      sha256, payload, loaded_at) VALUES ('2025/G3/a.json', 'naver_boxscore', 2025,
                                      '20250403LGOB0', 'u', :at, 'q', '{}', :at)"""), {"at": T(9)})
            self.assertEqual(v2._team_games(self.conn, 2025, None, T(3))["LG"], 2)  # 그때는 2경기
            self.assertEqual(v2._team_games(self.conn, 2025, None, None)["LG"], 3)
        finally:
            tx.rollback()

    def test_calc_basis_cannot_use_team_qualification(self):
        with self.assertRaises(ValueError):
            self.lead(basis="calc", qualified=True)

    def test_ranking_kind_is_explicit(self):
        self.assertEqual(self.lead(role="batter", stat="avg", min_ab=1)["data"]["criteria"]["ranking"], "reference")
        self.assertEqual(self.lead(stat="era", qualified=True)["data"]["criteria"]["ranking"], "qualified_innings_computed")

    def test_pagination(self):
        page = self.lead(limit=1, offset=1)
        self.assertEqual([r["rank"] for r in page["data"]["leaders"]], [2])
        self.assertEqual(page["page"]["total"], 2)


class DataQualityTest(V2Base):
    def test_counts(self):
        dq = v2.data_quality(self.conn, 2025, None)["data"]
        self.assertEqual(dq["coverage"], {"final_games": 2, "official_raw_games": 2, "calc_games": 2,
                                          "final_games_basis": "current_schedule_unversioned"})
        self.assertEqual(dq["verification"]["by_metric"]["pitcher.Outs"], {"naver_verified": 1})
        self.assertEqual(dq["exceptions"], {"walkoff": 1})
        self.assertEqual(dq["kbo_verified"], 0)

    def test_as_of_does_not_mix_time_points(self):
        """Codex 재검증: 과거 as_of 에 현재 일정 수·다른 시즌/나중의 KBO 원본이 섞이지 않는다."""
        from sqlalchemy import text

        early = v2.data_quality(self.conn, 2025, datetime(2025, 12, 31))["data"]
        self.assertEqual(early["coverage"]["final_games"], None)
        self.assertEqual(early["coverage"]["official_raw_games"], 0)
        self.conn.rollback()  # 위 조회가 자동으로 연 트랜잭션을 닫고 새로 연다
        tx = self.conn.begin()
        try:
            for season, at in ((2026, T(1)), (2025, T(9))):  # 다른 시즌 · as_of 이후 수집
                self.conn.execute(text("""INSERT INTO ingest.raw_record (raw_file, source, season, game_id, url, fetched_at,
                                          sha256, payload, loaded_at) VALUES (:f, 'kbo_gamecenter', :s, :g, 'u', :at,
                                          'k', '{}', :at)"""), {"f": f"kbo/{season}/{at.hour}", "s": season, "g": G1, "at": at})
            self.assertEqual(v2.meta(self.conn, 2025, T(8))["kbo_direct_verification"], "not_available")
            self.assertEqual(v2.meta(self.conn, 2025, None)["kbo_direct_verification"], "available")
        finally:
            tx.rollback()


class RouterTest(V2Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import main  # import 만으로는 DB 에 접속하지 않는다
        from routers import v2 as router

        def conn():
            with cls.engine.connect() as c:
                yield c

        main.app.dependency_overrides[router.connection] = conn
        cls.client = TestClient(main.app)
        cls.addClassCleanup(main.app.dependency_overrides.clear)

    def test_validation_and_errors(self):
        c = self.client
        self.assertEqual(c.get("/api/v2/games/BAD/box").status_code, 422)
        self.assertEqual(c.get("/api/v2/games/20990101ZZZZ0/box").status_code, 404)
        self.assertEqual(c.get(f"/api/v2/games/{G1}/box?as_of=2026-10-23T03:00:00").status_code, 422)  # 시간대 없음
        self.assertEqual(c.get("/api/v2/leaders?season=2025&role=batter&stat=era").status_code, 422)
        self.assertEqual(c.get("/api/v2/leaders?season=2025&role=batter&stat=avg&qualified=true").status_code, 422)
        self.assertEqual(c.get("/api/v2/leaders?season=2025&role=pitcher&stat=so&basis=calc&qualified=true")
                         .status_code, 422)
        self.assertEqual(c.get("/api/v2/players/90/games?season=2025&limit=0").status_code, 422)
        self.assertEqual(c.get("/api/v2/players/90/games?season=2025&date_from=2025-05-01&date_to=2025-04-01")
                         .status_code, 422)
        self.assertEqual(c.get("/api/v2/players/999/season?season=2025").status_code, 404)
        ok = c.get(f"/api/v2/games/{G1}/box")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["meta"]["sources"][0]["source"], "naver_boxscore")


if __name__ == "__main__":
    unittest.main()
