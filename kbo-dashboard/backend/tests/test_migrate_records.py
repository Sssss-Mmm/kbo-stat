"""migrate_records(P1-A) 재실행 안전성·원본 보존·롤백 테스트. SQLite 메모리 DB 에 스키마 이름만 떼서 돌린다."""
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, event, func, inspect, select
from sqlalchemy.pool import StaticPool

import migrate_records as mr
from database import Base
from models import Team
from models.records import (SCHEMAS, Build, Game, GamePitcherLine, OutsUncertain, PlayerGame, PlayerName, RawRecord,
                            ScheduleGame, SeasonStanding)

GAME = "20250401LGOB0"


def make_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
    return engine.execution_options(schema_translate_map={s: None for s in SCHEMAS})


def write_raw(data: Path, stamp: str, kk=1) -> str:
    pitcher = {"pcode": "90", "name": "투수", "inn": "1", "pa": 3, "ab": 3, "hit": 0, "hr": 0, "bb": 0, "bbhp": 0,
               "kk": kk, "r": 0, "er": 0, "bf": 12, "wls": ""}
    batter = {"playerCode": "1", "name": "타자", "batOrder": 1, "pos": "중", "ab": 3, "hit": 1, "hr": 0, "bb": 0,
              "kk": 1, "run": 0, "rbi": 0, "sb": 0}
    payload = {"recordData": {
        "gameInfo": {"aName": "LG", "hName": "두산", "statusCode": "4"},
        "pitchersBoxscore": {"away": [pitcher], "home": []},
        "teamPitchingBoxscore": {"away": {"inn": "1", "pa": 3, "hit": 0, "hr": 0, "bbhp": 0, "kk": kk, "r": 0}},
        "battersBoxscore": {"away": [batter], "home": [], "awayTotal": {"ab": 3, "hit": 1, "run": 0, "rbi": 0, "sb": 0}},
    }}
    env = {"source": "naver_boxscore", "url": "u", "game_id": GAME, "season": 2025,
           "fetched_at": f"2026-10-23T00:00:{stamp}Z", "sha256": mr.payload_hash(payload), "payload": payload}
    rel = f"2025/{GAME}/20261023T0000{stamp}000000Z.json"
    path = data / "raw" / "naver" / "record" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(env, ensure_ascii=False), encoding="utf-8")
    return rel


def write_inputs(data: Path, raw_file: str, calc_rule="rule1", so=1):
    official = data / "raw" / "kbo_official"
    processed = data / "processed"
    official.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([dict(Season=2025, Date="2025-04-01", away_team="LG", home_team="두산", away_score=3,
                       home_score=5, status="final", Ballpark="잠실", GameId=GAME)]) \
        .to_csv(official / "kbo_schedule_2025.csv", index=False)
    env = json.loads((data / "raw" / "naver" / "record" / raw_file).read_text(encoding="utf-8"))
    pitchers, batters = mr.nbp.parse_envelope(env, raw_file)  # build_naver_box_games 와 같은 방식
    pd.DataFrame(pitchers).to_csv(processed / "naver_box_pitchers_2025.csv", index=False)
    pd.DataFrame(batters).to_csv(processed / "naver_box_batters_2025.csv", index=False)
    pd.DataFrame([dict(Season=2025, Date="2025-04-01", GameId=GAME, DH=0, Role="pitcher", PlayerId=90,
                       Player="투수", Team="LG", Opponent="두산", HomeAway="away", PA=None, AB=None, H=0,
                       **{"2B": None, "3B": None}, HR=None, BB=0, HBP=0, SF=None, SH=None, SO=so, BF=3,
                       ResultUnknown=0, PAUncertain=0, AttributionUncertain=0, PAComplete=True,
                       StatsComplete=True, Outs=3, OutsComplete=True, CalcRule=calc_rule)]) \
        .to_csv(processed / "kbo_player_games_2025.csv", index=False)
    pd.DataFrame([dict(Season=2025, GameId=GAME, Role="pitcher", PlayerId=90, Player="투수", Metric="Outs",
                       CalcValue=3, CalcProven=True, ExternalValue=3, ExternalSource="naver_boxscore",
                       ExternalFetchedAt=env["fetched_at"], ExternalRawFile=raw_file,
                       Status="observed_naver_match", CalcRule=calc_rule, CheckedAt="2026-10-23T01:00:00Z")]) \
        .to_csv(processed / "kbo_player_games_check_2025.csv", index=False)
    pd.DataFrame([dict(Season=2025, Date="2025-04-01", GameId=GAME, PlayerId=80, Player="투수2", Team="두산",
                       Halves="1B", Reasons="final_half_unproven", LastResults="홈런", LastOuts="0", OutsRaw=3,
                       NaverOuts=None, NaverStatus="unverified", ExternalFetchedAt=None, ExternalRawFile=None,
                       CalcRule=calc_rule, CheckedAt="2026-10-23T01:00:00Z")]) \
        .to_csv(processed / "kbo_outs_uncertain_2025.csv", index=False)
    pd.DataFrame([dict(Season=2025, GameId=GAME, Kind="tie", Role="", PlayerId=None, Player="", Count=1, Detail="",
                       CalcRule=calc_rule, CheckedAt="2026-10-23T01:00:00Z"),
                  dict(Season=2025, GameId=GAME, Kind="pinch_runner", Role="batter", PlayerId=7, Player="주자",
                       Count=1, Detail="주", CalcRule=calc_rule, CheckedAt="2026-10-23T01:00:00Z")]) \
        .to_csv(processed / "kbo_verify_exceptions_2025.csv", index=False)


class MigrateRecordsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.engine = make_engine()
        Base.metadata.create_all(self.engine)  # 기존 public 테이블
        with self.engine.begin() as conn:
            conn.execute(Team.__table__.insert().values(name="LG"))

    def tearDown(self):
        self.tmp.cleanup()

    def load(self):
        with self.engine.begin() as conn:
            mr.load_season(conn, 2025, self.data)
            return mr.counts(conn)

    def test_rerun_is_idempotent_and_existing_tables_are_untouched(self):
        raw = write_raw(self.data, "01")
        write_inputs(self.data, raw)
        first = self.load()
        self.assertEqual(self.load(), first)
        self.assertEqual(first["ingest.raw_record"], 1)
        self.assertEqual(first["official.game_pitcher_line"], 1)
        self.assertEqual(first["derived.player_game"], 1)
        self.assertEqual(first["verify.exception"], 2)
        self.assertEqual(first["derived.build"], 4)
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(select(Team.name)).scalars().all(), ["LG"])
            names = conn.execute(select(PlayerName.source).where(PlayerName.player_id == 90)).scalars().all()
        self.assertEqual(sorted(names), ["naver_boxscore", "pitch_relay"])

    def test_new_raw_version_adds_rows_and_keeps_old(self):
        old = write_raw(self.data, "01")
        write_inputs(self.data, old)
        self.load()
        new = write_raw(self.data, "02", kk=2)
        write_inputs(self.data, new, so=2)
        counts = self.load()
        self.assertEqual(counts["ingest.raw_record"], 2)
        with self.engine.connect() as conn:
            lines = conn.execute(select(GamePitcherLine.raw_file, GamePitcherLine.so)
                                 .order_by(GamePitcherLine.raw_file)).all()
        self.assertEqual([tuple(x) for x in lines], [(old, 1), (new, 2)])  # 옛 원본의 값이 그대로 남는다

    def test_fresh_load_keeps_lines_of_every_raw_version(self):
        """Codex P2-B 3차: 빈 DB 에 두 판본을 한 번에 적재해도 옛 판본의 줄이 남는다(as_of 조회용)."""
        old = write_raw(self.data, "01")
        new = write_raw(self.data, "02", kk=2)
        write_inputs(self.data, new, so=2)  # 가공 CSV 는 최신 판본 기준
        self.load()
        with self.engine.connect() as conn:
            lines = conn.execute(select(GamePitcherLine.raw_file, GamePitcherLine.so)
                                 .order_by(GamePitcherLine.raw_file)).all()
        self.assertEqual([tuple(x) for x in lines], [(old, 1), (new, 2)])

    def test_new_calc_rule_keeps_previous_derived_rows(self):
        raw = write_raw(self.data, "01")
        write_inputs(self.data, raw, calc_rule="rule1")
        self.load()
        write_inputs(self.data, raw, calc_rule="rule2", so=0)
        self.load()
        with self.engine.connect() as conn:
            rows = conn.execute(select(PlayerGame.calc_rule, PlayerGame.so).order_by(PlayerGame.calc_rule)).all()
        self.assertEqual([tuple(r) for r in rows], [("rule1", 1), ("rule2", 0)])

    def builds(self, model):
        with self.engine.connect() as conn:
            rows = conn.execute(select(model.build_id, model.player_id)).all()
        by_build = {}
        for build_id, pid in rows:
            by_build.setdefault(build_id, set()).add(pid)
        return by_build

    def test_changed_input_with_same_rule_is_a_new_build(self):
        """Codex P1-A: 계산 코드가 같아도 입력이 바뀌면 옛 값을 덮어쓰지 않고 새 빌드로 쌓는다."""
        raw = write_raw(self.data, "01")
        write_inputs(self.data, raw, so=1)
        self.load()
        write_inputs(self.data, raw, so=0)
        self.load()
        with self.engine.connect() as conn:
            values = sorted(conn.execute(select(PlayerGame.so)).scalars().all())
            builds = conn.execute(select(Build.kind)).scalars().all()
        self.assertEqual(values, [0, 1])
        self.assertEqual(builds.count("player_game"), 2)

    def test_row_missing_from_new_build_stays_only_in_old_build(self):
        """Codex P1-A: 새 산출물에서 사라진 행은 옛 빌드에만 남는다(현재 뷰는 최신 빌드만 본다)."""
        raw = write_raw(self.data, "01")
        write_inputs(self.data, raw)
        path = self.data / "processed" / "kbo_player_games_2025.csv"
        two = pd.read_csv(path)
        pd.concat([two, two.assign(PlayerId=91, Player="투수3")]).to_csv(path, index=False)
        self.load()
        write_inputs(self.data, raw)  # 91 이 빠진 새 산출물
        self.load()
        self.assertEqual(sorted(map(sorted, self.builds(PlayerGame).values())), [[90], [90, 91]])

    def test_reverification_with_new_raw_keeps_previous_result(self):
        """Codex P1-A: 새 원본으로 다시 대조해도 이전 아웃 미확정 대조 결과가 남는다."""
        old = write_raw(self.data, "01")
        write_inputs(self.data, old)
        self.load()
        new = write_raw(self.data, "02", kk=2)
        write_inputs(self.data, new)
        uncertain = self.data / "processed" / "kbo_outs_uncertain_2025.csv"
        fetched = json.loads((self.data / "raw" / "naver" / "record" / new).read_text())["fetched_at"]
        pd.read_csv(uncertain).assign(NaverOuts=3, NaverStatus="naver_verified", ExternalRawFile=new,
                                      ExternalFetchedAt=fetched) \
            .to_csv(uncertain, index=False)
        self.load()
        with self.engine.connect() as conn:
            rows = conn.execute(select(OutsUncertain.naver_status).order_by(OutsUncertain.naver_status)).all()
        self.assertEqual([r[0] for r in rows], ["naver_verified", "unverified"])

    def test_box_csv_row_must_match_its_raw_record(self):
        """Codex P1-A 3차: 가공 CSV 의 해시·수집시각이 원본과 다르면 적재하지 않는다."""
        raw = write_raw(self.data, "01")
        write_inputs(self.data, raw)
        path = self.data / "processed" / "naver_box_pitchers_2025.csv"
        for col, value in (("Sha256", "0" * 64), ("FetchedAt", "2026-10-23T09:00:00Z")):
            write_inputs(self.data, raw)
            pd.read_csv(path).assign(**{col: value}).to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "원본"):
                self.load()

    def test_box_csv_values_must_match_reparsed_raw(self):
        """Codex P1-B 사전검증: 해시·시각은 그대로 두고 기록 값만 바꾼 CSV, 빠진 행도 적재하지 않는다."""
        raw = write_raw(self.data, "01")
        path = self.data / "processed" / "naver_box_pitchers_2025.csv"
        for change in (lambda df: df.assign(SO=9), lambda df: df.iloc[0:0]):
            write_inputs(self.data, raw)
            change(pd.read_csv(path)).to_csv(path, index=False)
            with self.assertRaises(ValueError):
                self.load()

    def test_check_row_pointing_at_another_games_raw_is_refused(self):
        """Codex P1-B 사전검증: 대조 행이 다른 경기의 (존재하는) 원본을 가리키면 적재하지 않는다."""
        raw = write_raw(self.data, "01")
        write_inputs(self.data, raw)
        path = self.data / "processed" / "kbo_player_games_check_2025.csv"
        pd.read_csv(path).assign(GameId="20250402LGOB0").to_csv(path, index=False)
        with self.assertRaisesRegex(ValueError, "다른 원본"):
            self.load()

    def test_rows_from_another_season_are_refused(self):
        """Codex P1-A 3차: --season 과 다른 시즌 행이 섞인 CSV 는 적재하지 않는다."""
        raw = write_raw(self.data, "01")
        for name in ("kbo_player_games_2025.csv", "kbo_player_games_check_2025.csv", "naver_box_batters_2025.csv"):
            write_inputs(self.data, raw)
            path = self.data / "processed" / name
            pd.read_csv(path).assign(Season=2024).to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "--season 2025", msg=name):
                self.load()
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(select(func.count()).select_from(PlayerGame)).scalar_one(), 0)

    def test_tampered_raw_rolls_back_everything(self):
        raw = write_raw(self.data, "01")
        write_inputs(self.data, raw)
        path = self.data / "raw" / "naver" / "record" / raw
        env = json.loads(path.read_text(encoding="utf-8"))
        env["payload"]["recordData"]["pitchersBoxscore"]["away"][0]["kk"] = 9
        path.write_text(json.dumps(env), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "무결성"):
            self.load()
        # 반쯤 적재된 상태가 남지 않는다. (pysqlite 는 DDL 을 자동 커밋해 빈 테이블은 남을 수 있다 —
        # PostgreSQL 은 DDL 도 롤백된다.)
        tables = inspect(self.engine).get_table_names()
        with self.engine.connect() as conn:
            for model in (Game, RawRecord, PlayerGame):
                if model.__tablename__ in tables:
                    self.assertEqual(conn.execute(select(func.count()).select_from(model)).scalar_one(), 0,
                                     model.__tablename__)
            self.assertEqual(conn.execute(select(Team.name)).scalars().all(), ["LG"])

    def test_reference_schedule_and_standings(self):
        ref = self.data / "raw" / "kbo_official"
        ref.mkdir(parents=True)
        cols = "Season,Date,Weekday,Time,away_team,home_team,away_score,home_score,status,GameCenter,Highlight,TV,Radio,Ballpark,Note,GameId"
        (ref / "kbo_schedule_2025.csv").write_text("\n".join([cols,
            "2025,2025-04-01,화,18:30,LG,두산,3,1,final,,,,,잠실,-,20250401LGOB0",
            "2025,2025-04-02,수,18:30,LG,두산,2,2,final,,,,,잠실,-,20250402LGOB0",
            "2025,2025-04-03,목,18:30,LG,두산,,,scheduled,,,,,잠실,우천취소,",
            "2025,2025-04-05,토,14:00,두산,LG,1,0,final,,,,,잠실,-,20250405OBLG2"]), encoding="utf-8-sig")
        (ref / "kbo_team_rank_2025.csv").write_text(
            "Season,순위,팀명,경기,승,패,무,승률,게임차,최근10경기,연속,홈,방문\n"
            "2025,1,LG,3,1,1,1,0.5,0,1승1무1패,1패,0-0-1,1-1-0\n", encoding="utf-8-sig")
        for _ in range(2):  # 같은 CSV 를 다시 적재해도 같은 빌드 — 행이 늘지 않는다
            with self.engine.begin() as conn:
                mr.ensure_schema(conn)
                self.assertEqual(mr.load_reference(conn, self.data, 2025), {"schedule": 4, "season_standing": 1})
        with self.engine.connect() as conn:
            rows = conn.execute(select(ScheduleGame).order_by(ScheduleGame.row_no)).all()
            self.assertEqual([(r.status, r.cancel_reason, r.game_id, r.dh) for r in rows],
                             [("final", None, "20250401LGOB0", 0), ("tie", None, "20250402LGOB0", 0),
                              ("canceled", "우천취소", None, None), ("final", None, "20250405OBLG2", 2)])
            self.assertEqual(conn.execute(select(func.count()).select_from(SeasonStanding)).scalar_one(), 1)
        self.assertEqual(mr.load_reference(None, self.data, 2024), {})  # 파일 없는 시즌은 건너뛴다
        # 헤더만 남은 CSV 는 빈 빌드를 만들지 않는다 — 기존 빌드가 그대로 최신
        (ref / "kbo_schedule_2025.csv").write_text(cols + "\n", encoding="utf-8-sig")
        (ref / "kbo_team_rank_2025.csv").write_text("Season,순위,팀명,경기,승,패,무,승률,게임차,최근10경기,연속,홈,방문\n",
                                                   encoding="utf-8-sig")
        with self.engine.begin() as conn:
            self.assertEqual(mr.load_reference(conn, self.data, 2025), {})
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(select(func.count()).select_from(Build)).scalar_one(), 2)
            self.assertEqual(conn.execute(select(func.count()).select_from(ScheduleGame)).scalar_one(), 4)

    def test_records_tables_are_not_created_by_init_db(self):
        """기존 init_db(create_all)는 새 스키마를 모른다 — DB 없이 뜨는 API 기동 경로가 그대로다."""
        self.assertNotIn(RawRecord.__table__, Base.metadata.sorted_tables)


if __name__ == "__main__":
    unittest.main()
