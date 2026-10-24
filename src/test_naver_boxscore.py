"""네이버 박스스코어 보존·해석·대조 회귀 테스트(네트워크 없음).

실행: python -m unittest discover -s src -p "test_naver_boxscore.py" -v
"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_naver_box_games as nb
import crawl_naver_boxscore as cb
import crawl_naver_pitch_zones as cz
import verify_player_games as vp

GAME = "20250401LGOB0"


def record(inn="1", team_inn="1", team_bbhp=0):
    """투수 한 명·타자 한 명씩인 최소 record payload."""
    pitcher = {"pcode": "90", "name": "투수", "inn": inn, "pa": 3, "ab": 3, "hit": 0, "hr": 0, "bb": 0,
               "bbhp": 0, "kk": 1, "r": 0, "er": 0, "bf": 12, "wls": ""}
    batter = {"playerCode": "1", "name": "타자", "batOrder": 1, "pos": "중", "ab": 3, "hit": 1, "hr": 0,
              "bb": 0, "kk": 1, "run": 0, "rbi": 0, "sb": 0}
    team_p = {"inn": team_inn, "pa": 3, "hit": 0, "hr": 0, "bbhp": team_bbhp, "kk": 1, "r": 0, "er": 0}
    team_b = {"ab": 3, "hit": 1, "run": 0, "rbi": 0, "sb": 0}
    return {"recordData": {
        "gameInfo": {"aName": "LG", "hName": "두산", "statusCode": "4"},
        "pitchersBoxscore": {"away": [pitcher], "home": [dict(pitcher, pcode="80")]},
        "teamPitchingBoxscore": {"away": team_p, "home": team_p},
        "battersBoxscore": {"away": [batter], "home": [dict(batter, playerCode="11")],
                            "awayTotal": team_b, "homeTotal": team_b},
    }}


def _append_many(root, n):
    for i in range(50):
        cb.append_log({"run_id": f"p{n}", "game_id": GAME, "status": "saved", "error": "x" * 2000}, root)


class SaveRecordTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def at(self, second):
        return datetime(2026, 10, 23, 0, 0, second, tzinfo=timezone.utc)

    def test_never_overwrites_and_skips_identical_payload(self):
        status, first, _ = cb.save_record(GAME, 2025, record(), "u", self.at(1), self.root)
        self.assertEqual(status, "saved")
        before = first.read_bytes()
        self.assertEqual(cb.save_record(GAME, 2025, record(), "u", self.at(2), self.root)[0], "unchanged")
        status, second, _ = cb.save_record(GAME, 2025, record(inn="2"), "u", self.at(3), self.root)
        self.assertEqual(status, "saved")
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), before)  # 기존 원본은 그대로
        envelope = json.loads(second.read_text(encoding="utf-8"))
        self.assertEqual(envelope["source"], "naver_boxscore")
        self.assertEqual(envelope["fetched_at"], "2026-10-23T00:00:03Z")
        self.assertEqual(envelope["sha256"], cb.payload_hash(envelope["payload"]))

    def test_failed_write_leaves_no_partial_file(self):
        _, first, _ = cb.save_record(GAME, 2025, record(), "u", self.at(1), self.root)

        def half_written(obj, handle, **kwargs):
            handle.write('{"source": "naver')
            raise OSError("disk full")

        with mock.patch.object(cb.json, "dump", side_effect=half_written), self.assertRaises(OSError):
            cb.save_record(GAME, 2025, record(inn="2"), "u", self.at(2), self.root)
        self.assertEqual(list(cb.game_dir(GAME, 2025, self.root).iterdir()), [first])  # 반쪽 파일·임시 파일 없음

    def test_fetch_failure_is_logged_and_writes_nothing(self):
        cb.save_record(GAME, 2025, record(), "u", self.at(1), self.root)
        kept = cb.saved_files(GAME, 2025, self.root)
        with mock.patch.object(cb, "fetch_record", side_effect=RuntimeError("boom")):
            counts = cb.collect([GAME, "20250402LGOB0"], 2025, refresh=True, pause=0, root=self.root)
        self.assertEqual(counts, {"error": 2})
        self.assertEqual(cb.saved_files(GAME, 2025, self.root), kept)
        self.assertEqual(cb.saved_files("20250402LGOB0", 2025, self.root), [])
        log = pd.read_csv(self.root / "ingest_log.csv")
        # 경기마다 재시도 2번(retry) 뒤 실패(error) — 시도마다 한 줄
        self.assertEqual(log["status"].tolist()[-6:], ["retry", "retry", "error"] * 2)

    def test_transient_failure_is_retried_then_saved(self):
        responses = iter([RuntimeError("timeout"), {"recordData": {}}, record()])

        def flaky(*_):
            value = next(responses)
            if isinstance(value, Exception):
                raise value
            return value

        with mock.patch.object(cb, "fetch_record", side_effect=flaky), mock.patch.object(cb.time, "sleep") as sleep:
            self.assertEqual(cb.collect([GAME], 2025, pause=0.5, root=self.root), {"saved": 1})
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1.0, 2.0])  # pause×2, ×4
        log = pd.read_csv(self.root / "ingest_log.csv")
        self.assertEqual(log["status"].tolist(), ["retry", "retry", "saved"])
        self.assertEqual(len(cb.saved_files(GAME, 2025, self.root)), 1)

    def test_existing_game_is_not_refetched(self):
        cb.save_record(GAME, 2025, record(), "u", self.at(1), self.root)
        with mock.patch.object(cb, "fetch_record") as fetch:
            self.assertEqual(cb.collect([GAME], 2025, pause=0, root=self.root), {"skipped_existing": 1})
        fetch.assert_not_called()

    def test_empty_response_is_not_saved_and_does_not_block_refetch(self):
        """Codex 1차: 빈 응답이 '이미 받음'으로 남아 재수집을 막으면 안 된다."""
        hollow = {"recordData": {k: {} for k in cb.REQUIRED_KEYS}}
        one_side = record()
        one_side["recordData"]["battersBoxscore"]["home"] = []
        for empty in ({}, {"recordData": {}}, {"recordData": None}, hollow, one_side):
            self.assertEqual(cb.keep(GAME, 2025, empty, "r", self.root), "error")
            with mock.patch.object(cz, "get_json", return_value=empty), \
                    mock.patch.object(cb, "RECORD_DIR", self.root):  # 실제 data/ 에 쓰지 않게
                cz.fetch_name_map(f"{GAME}2025", keep_raw=True)
        self.assertEqual(cb.saved_files(GAME, 2025, self.root), [])
        with mock.patch.object(cb, "fetch_record", return_value=record()) as fetch:
            self.assertEqual(cb.collect([GAME], 2025, pause=0, root=self.root), {"saved": 1})
        fetch.assert_called_once()

    def test_game_id_cannot_escape_the_record_folder(self):
        """Codex 2차: GameId 는 경로가 된다 — 형식이 틀리면 요청·저장 전에 거부."""
        for bad in ("../escape", "/tmp/escape", "2025/../../x", "20250401LGOB0/../x", "20250401lgob0", ""):
            with self.assertRaises(ValueError, msg=bad):
                cb.save_record(bad, 2025, record(), "u", self.at(1), self.root)
            with mock.patch.object(cb, "fetch_record") as fetch, self.assertRaises(ValueError, msg=bad):
                cb.collect([GAME, bad], 2025, pause=0, root=self.root)
            fetch.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_same_timestamp_never_replaces_existing_file(self):
        """Codex 2차: 같은 이름으로 두 번 저장(동시 실행)해도 먼저 쓴 원본은 그대로."""
        _, first, _ = cb.save_record(GAME, 2025, record(), "u", self.at(1), self.root)
        before = first.read_bytes()
        with mock.patch.object(cb, "saved_files", return_value=[]), self.assertRaises(FileExistsError):
            cb.save_record(GAME, 2025, record(inn="2"), "u", self.at(1), self.root)
        self.assertEqual(first.read_bytes(), before)
        self.assertEqual(list(cb.game_dir(GAME, 2025, self.root).iterdir()), [first])

    def test_concurrent_log_appends_keep_one_header(self):
        """Codex 3차: 두 프로세스가 빈 로그에 동시에 써도 헤더는 한 번, 행은 온전하게."""
        import multiprocessing as mp

        ctx = mp.get_context("fork")
        procs = [ctx.Process(target=_append_many, args=(self.root, n)) for n in range(4)]
        for p in procs:
            p.start()
        for p in procs:
            p.join()
        log = pd.read_csv(self.root / "ingest_log.csv")
        self.assertEqual(len(log), 4 * 50)
        self.assertFalse(log["run_id"].eq("run_id").any())  # 중간에 헤더 행이 끼지 않음

    def test_in_progress_game_is_not_saved(self):
        """Codex P2-A 사전검증: 진행 중(statusCode≠4) 기록은 최종본으로 저장하지 않아 종료 뒤 다시 받는다."""
        live = record()
        live["recordData"]["gameInfo"]["statusCode"] = "STARTED"
        self.assertFalse(cb.has_boxscore(live))
        self.assertEqual(cb.keep(GAME, 2025, live, "r", self.root), "error")
        with mock.patch.object(cb, "fetch_record", return_value=record()):
            self.assertEqual(cb.collect([GAME], 2025, pause=0, root=self.root), {"saved": 1})

    def test_corrupted_latest_file_does_not_block_a_good_refetch(self):
        """Codex P2-A 사전검증: 최신 파일 payload 가 손상돼 있으면 같은 해시의 정상 응답을 새 파일로 남긴다."""
        _, first, digest = cb.save_record(GAME, 2025, record(), "u", self.at(1), self.root)
        env = json.loads(first.read_text(encoding="utf-8"))
        env["payload"]["recordData"]["gameInfo"]["aName"] = "변조"
        first.write_text(json.dumps(env, ensure_ascii=False), encoding="utf-8")
        status, second, _ = cb.save_record(GAME, 2025, record(), "u", self.at(2), self.root)
        self.assertEqual(status, "saved")
        self.assertNotEqual(first, second)
        self.assertIn("변조", first.read_text(encoding="utf-8"))  # 손상 파일도 지우지 않는다

    def test_corrupted_only_file_is_refetched_by_default_collect(self):
        """Codex P2-A 2차: 손상된 원본만 있으면 기본 collect 도 건너뛰지 않고 다시 받는다(손상 파일은 남김)."""
        _, first, _ = cb.save_record(GAME, 2025, record(), "u", self.at(1), self.root)
        first.write_text("{not json", encoding="utf-8")
        with mock.patch.object(cb, "fetch_record", return_value=record()) as fetch:
            self.assertEqual(cb.collect([GAME], 2025, pause=0, root=self.root), {"saved": 1})
        fetch.assert_called_once()
        self.assertTrue(first.exists())
        log = pd.read_csv(self.root / "ingest_log.csv")
        self.assertEqual(log["status"].tolist(), ["invalid_existing", "saved"])
        self.assertIsNone(cb.latest_problem(GAME, 2025, self.root))

    def test_keep_swallows_save_errors(self):
        with mock.patch.object(cb, "save_record", side_effect=OSError("disk full")):
            self.assertEqual(cb.keep(GAME, 2025, record(), "r", self.root), "error")
        self.assertIn("disk full", pd.read_csv(self.root / "ingest_log.csv")["error"].iloc[0])

    def test_pitch_crawler_name_map_survives_keep_failure(self):
        """원본 보존이 깨져도 기존 투구 크롤러의 이름 맵은 그대로 나온다."""
        with mock.patch.object(cz, "get_json", return_value=record()), \
                mock.patch.object(cb, "keep", side_effect=RuntimeError("boom")):
            names = cz.fetch_name_map(f"{GAME}2025", keep_raw=True)
        self.assertEqual(names, {"90": "투수", "80": "투수", "1": "타자", "11": "타자"})


class ParseTest(unittest.TestCase):
    def test_inning_outs(self):
        cases = {"5 ⅔": 17, "0 ⅓": 1, "3": 9, "0": 0, "⅔": 2, "1⅓": 4, "": None, "abc": None, "1 1/3": None}
        for text, expected in cases.items():
            self.assertEqual(nb.inning_outs(text), expected, text)

    def parse(self, payload):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, path, _ = cb.save_record(GAME, 2025, payload, "u", root=root)
            return nb.parse_record(path, root)

    def test_rows_carry_provenance_and_team_sum_check(self):
        pitchers, batters = self.parse(record())
        self.assertEqual(len(pitchers), 2)
        self.assertEqual(pitchers[0]["Outs"], 3)
        self.assertEqual(pitchers[0]["Source"], "naver_boxscore")
        self.assertTrue(pitchers[0]["RawFile"].startswith(f"2025/{GAME}/"))
        self.assertEqual([r["TeamSumMismatch"] for r in pitchers + batters], ["", "", "", ""])

    def test_tampered_or_misplaced_raw_file_is_refused(self):
        """Codex P0 재검증: 저장 뒤 바뀐 payload·다른 경기 폴더의 원본은 출처가 맞는 값처럼 쓰지 않는다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, path, _ = cb.save_record(GAME, 2025, record(), "u", root=root)
            envelope = json.loads(path.read_text(encoding="utf-8"))
            envelope["payload"]["recordData"]["pitchersBoxscore"]["away"][0]["kk"] = 9
            path.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "무결성"):
                nb.parse_record(path, root)
            _, good, _ = cb.save_record("20250402LGOB0", 2025, record(), "u", root=root)
            moved = cb.game_dir("20250403LGOB0", 2025, root) / good.name
            moved.parent.mkdir(parents=True)
            good.rename(moved)
            with self.assertRaisesRegex(ValueError, "무결성"):
                nb.parse_record(moved, root)

    def test_build_without_raw_files_stops_with_clear_message(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(nb, "RECORD_DIR", Path(tmp)):
            with self.assertRaises(SystemExit) as ctx:
                nb.build(2025)
        self.assertIn("원본이 없습니다", str(ctx.exception))

    def test_team_sum_mismatch_names_only_the_bad_metric(self):
        pitchers, _ = self.parse(record(team_inn="2", team_bbhp=1))
        self.assertEqual(pitchers[0]["TeamSumMismatch"], "Outs,BBHP")


class VerifyTest(unittest.TestCase):
    def test_status_names(self):
        self.assertEqual(vp.status(3, True, 3, True), "observed_naver_match")
        self.assertEqual(vp.status(3, True, 2, True), "observed_naver_conflict")
        self.assertEqual(vp.status(3, False, 3, True), "naver_verified")
        self.assertEqual(vp.status(5, False, 3, True), "naver_conflict")
        self.assertEqual(vp.status(3, False, 3, False), "naver_unusable")
        self.assertEqual(vp.status(pd.NA, False, 0, True), "calc_missing")
        self.assertEqual(vp.status(3, True, float("nan"), True), "naver_missing")
        # 네이버 대조 결과가 KBO 공식 확인으로 읽히지 않게 한다.
        for args in [(3, True, 3, True), (3, False, 3, True), (5, False, 3, True)]:
            self.assertNotIn("kbo", vp.status(*args))

    def test_compare_keeps_unproven_outs_out_of_calc_columns(self):
        """미확정 아웃은 _OutsRaw 로만 대조하고 Outs/OutsComplete 는 건드리지 않는다."""
        games = pd.DataFrame([
            dict(Role="pitcher", GameId=GAME, PlayerId=90, Player="투수", Outs=3, OutsComplete=True, BF=3,
                 H=0, BB=0, HBP=0, SO=1, PAComplete=True, StatsComplete=True),
            dict(Role="pitcher", GameId=GAME, PlayerId=80, Player="투수", Outs=pd.NA, OutsComplete=False, BF=3,
                 H=0, BB=0, HBP=0, SO=1, PAComplete=True, StatsComplete=True),
        ])
        raw = pd.Series({(GAME, 90): 3.0, (GAME, 80): 3.0})
        box = pd.DataFrame([
            dict(GameId=GAME, PlayerId=90, Player="투수", Outs=3, BF=3, H=0, BB=0, BBHP=0, SO=1,
                 FetchedAt="t", RawFile="r.json", TeamSumMismatch=""),
            dict(GameId=GAME, PlayerId=80, Player="투수", Outs=3, BF=3, H=0, BB=0, BBHP=0, SO=1,
                 FetchedAt="t", RawFile="r.json", TeamSumMismatch=""),
            dict(GameId=GAME, PlayerId=70, Player="투수", Outs=1, BF=1, H=0, BB=0, BBHP=0, SO=0,
                 FetchedAt="t", RawFile="r.json", TeamSumMismatch=""),
        ])
        before = games.copy()
        checks = vp.compare(games, raw, box, "pitcher").set_index(["PlayerId", "Metric"])
        self.assertEqual(checks.loc[(90, "Outs"), "Status"], "observed_naver_match")
        self.assertEqual(checks.loc[(80, "Outs"), "Status"], "naver_verified")
        self.assertEqual(checks.loc[(80, "BF"), "Status"], "observed_naver_match")
        self.assertEqual(checks.loc[(70, "Outs"), "Status"], "calc_missing")
        pd.testing.assert_frame_equal(games, before)


class ExceptionTest(unittest.TestCase):
    def test_exception_kinds(self):
        """자동 고의4구·대주자·대수비·투구 행 없음·콜드를 사유별로 나누고 값은 건드리지 않는다."""
        import build_player_games as bpg
        import test_build_player_games as tb

        rows = tb.one_game()  # 1회초 3아웃(투수 90) + 1회말 끝내기 홈런(투수 80) — 1이닝짜리 경기
        sched = tb.schedule(tb.GAME)
        raw = pd.DataFrame(rows).assign(_File="f.csv")
        pitches = bpg.pick_one_file_per_game(raw, 2025)
        df = bpg.pitch_outs(bpg.order_plate_appearances(bpg.regular_season(bpg.ensure_teams(pitches), sched)))
        games = bpg.build_frame(pitches, sched)
        meta = dict(GameId=tb.GAME, FetchedAt="t", RawFile="r.json", TeamSumMismatch="")
        stats = dict(H=1, BB=1, BBHP=1, SO=1)
        box_p = pd.DataFrame([dict(meta, **stats, Side="home", PlayerId=90, Player="투수90", Outs=3, BF=5),
                              dict(meta, **stats, Side="away", PlayerId=80, Player="투수80", Outs=0, BF=1),
                              dict(meta, **stats, Side="away", PlayerId=81, Player="등판만", Outs=0, BF=0)])
        bat = dict(meta, Side="home", AB=0, BB=0, IBB=0, Pos="")
        box_b = pd.DataFrame([dict(bat, PlayerId=4, Player="타자4", BB=1, IBB=1, Pos="좌"),  # 고4 인데 계산은 일반 볼넷
                              dict(bat, PlayerId=21, Player="주자", Pos="주"),
                              dict(bat, PlayerId=22, Player="대수비", Pos="중"),
                              dict(bat, PlayerId=23, Player="누락", AB=2, Pos="一")])
        checks = vp.compare(games, pd.Series(dtype=float), box_p, "pitcher")
        found = vp.exceptions(df, games, checks, box_p, box_b, sched)
        kinds = found.groupby("Kind")["PlayerId"].apply(lambda s: sorted(s.dropna().astype(int))).to_dict()
        self.assertEqual(kinds["auto_ibb_no_pitch"], [4])
        self.assertEqual(kinds["pinch_runner"], [21])
        self.assertEqual(kinds["defensive_sub"], [22])
        self.assertEqual(kinds["no_pitch_rows"], [23])
        self.assertEqual(kinds["pitcher_no_pitch"], [81])
        self.assertIn("called_game", kinds)  # 홈 투수 아웃 3 < 27
        self.assertNotIn("tie", kinds)


if __name__ == "__main__":
    unittest.main()
