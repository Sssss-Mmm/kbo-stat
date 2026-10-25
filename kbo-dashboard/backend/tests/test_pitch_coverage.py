"""/api/pitch-coverage — 투구 원본이 담은 경기 범위·정규시즌 수집률 (임시 디렉터리, 실데이터 무관)."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from routers import zones

HEAD = "Date,GameId,Season,PitchId,PlateX,PlateZ,TopSz,BottomSz,IsInPlay,IsHit\n"


def pitch_rows(*games):
    """(날짜, KBO 경기ID) 마다 투구 두 개(둘째는 좌표 없음 → 존 집계에서 빠진다).
    원본 GameId 는 경기ID 뒤에 시즌이 붙는다."""
    return "".join(f"{d},{g}{d[:4]},{d[:4]},{d}_{i},{xz},3.4,1.6,False,False\n"
                   for d, g in games for i, xz in ((1, "0.1,2.5"), (2, ",")))


class PitchCoverageTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.raw = Path(tmp.name) / "raw"
        self.processed = Path(tmp.name) / "processed"
        self.raw.mkdir()
        self.processed.mkdir()
        for name, value in (("RAW_DIR", self.raw), ("PROCESSED_DIR", self.processed)):
            patcher = patch.object(zones, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        zones._raw_stats.cache_clear()

    def write_pitches(self, name, *games):
        (self.raw / f"naver_kbo_pitches_{name}.csv").write_text(HEAD + pitch_rows(*games), encoding="utf-8-sig")

    def write_schedule(self, season, *game_ids):
        rows = "".join(f"{season},{g},T\n{season},{g},U\n" for g in game_ids)  # 팀 기준 2행/경기
        (self.processed / f"kbo_team_games_{season}.csv").write_text("Season,GameId,Team\n" + rows, encoding="utf-8-sig")

    def write_analysis(self, season, first, last, days, zone_pitches):
        """빌더 산출물 흉내: 아스널·볼카운트는 날짜 메타, 존은 Pitches 만."""
        for name in ("pitcher_arsenal", "batter_vs_pitch", "count_baseball"):
            (self.processed / f"kbo_{name}_{season}.csv").write_text(
                f"Season,Days,FirstDate,LastDate\n{season},{days},{first},{last}\n{season},{days},{first},{last}\n",
                encoding="utf-8-sig")
        for name in ("batter_zones", "pitcher_zones"):
            (self.processed / f"kbo_{name}_{season}.csv").write_text(
                f"Season,Zone,Pitches\n{season},1-1,{zone_pitches - 1}\n{season},2-2,1\n", encoding="utf-8-sig")

    def api(self, season):
        return asyncio.run(zones.pitch_coverage_api(season=season))

    def test_range_games_and_rate(self):
        # 겹치는 범위 파일(같은 경기 중복)은 한 번만 센다. 다른 시즌 파일은 열지 않는다.
        self.write_pitches("2026-03-28_2026-03-29", ("2026-03-28", "20260328KTLG0"), ("2026-03-29", "20260329KTLG0"))
        self.write_pitches("2026-03-29", ("2026-03-29", "20260329KTLG0"))
        self.write_pitches("2026-09-24", ("2026-09-24", "20260924HTSK0"))
        self.write_pitches("2025-10-01", ("2025-10-01", "20251001HTSK0"))
        self.write_schedule(2026, "20260328KTLG0", "20260329KTLG0", "20260924HTSK0", "20261012LTSS0")
        body = self.api(2026)
        self.assertEqual(body["status"], "success")
        data = dict(body["data"])
        self.assertEqual(data.pop("analysis"), dict.fromkeys(zones.ANALYSIS_FILES))  # 분석 CSV 없음
        self.assertEqual(data, {
            "season": 2026, "first_date": "2026-03-28", "last_date": "2026-09-24", "days": 3,
            "games": 3, "regular_games": 3, "regular_total": 4, "rate": 0.75,
            "unscheduled_games": 0, "other_games": 0,
        })

    def test_postseason_games_are_counted_apart(self):
        self.write_pitches("2025-10-04", ("2025-10-04", "20251004HTSK0"))
        self.write_pitches("2025-10-31", ("2025-10-31", "33331031SSSK0"))
        self.write_schedule(2025, "20251004HTSK0")
        data = self.api(2025)["data"]
        self.assertEqual((data["games"], data["regular_games"], data["regular_total"], data["rate"],
                          data["unscheduled_games"], data["other_games"]), (2, 1, 1, 1.0, 0, 1))
        self.assertEqual(data["last_date"], "2025-10-31")

    def test_lagging_schedule_is_not_called_postseason(self):
        # 일정 CSV 가 하루 늦은 상황: 09-25 정규시즌 경기는 원본에만 있다. 포스트시즌 코드 경기와 따로 센다.
        self.write_pitches("2026-09-24", ("2026-09-24", "20260924HTSK0"))
        self.write_pitches("2026-09-25", ("2026-09-25", "20260925HTSK0"))
        self.write_pitches("2026-10-06", ("2026-10-06", "44441006NCSS0"))
        self.write_schedule(2026, "20260924HTSK0")
        data = self.api(2026)["data"]
        self.assertEqual((data["games"], data["regular_games"], data["regular_total"],
                          data["unscheduled_games"], data["other_games"]), (3, 1, 1, 1, 1))

    def test_missing_schedule_leaves_rate_empty(self):
        self.write_pitches("2026-04-01", ("2026-04-01", "20260401KTLG0"))
        data = self.api(2026)["data"]
        self.assertEqual(data["games"], 1)
        self.assertIsNone(data["regular_total"])
        self.assertIsNone(data["rate"])
        self.assertIsNone(data["unscheduled_games"])
        self.assertIsNone(data["other_games"])

    def test_no_pitch_files_returns_null(self):
        self.write_schedule(2026, "20260328KTLG0")
        self.assertIsNone(self.api(2026)["data"])

    def test_files_without_season_rows_return_null(self):
        self.write_pitches("2026-04-01")  # 헤더만
        self.assertIsNone(self.api(2026)["data"])

    def test_new_file_invalidates_cache(self):
        self.write_pitches("2026-04-01", ("2026-04-01", "20260401KTLG0"))
        self.assertEqual(self.api(2026)["data"]["games"], 1)
        self.write_pitches("2026-04-02", ("2026-04-02", "20260402KTLG0"))
        self.assertEqual(self.api(2026)["data"]["games"], 2)

    def test_analysis_matching_raw_is_fresh(self):
        self.write_pitches("2026-03-28", ("2026-03-28", "20260328KTLG0"))
        self.write_pitches("2026-03-29", ("2026-03-29", "20260329KTLG0"))
        self.write_analysis(2026, "2026-03-28", "2026-03-29", 2, zone_pitches=2)
        analysis = self.api(2026)["data"]["analysis"]
        self.assertEqual(analysis["pitcher_arsenal"],
                         {"first_date": "2026-03-28", "last_date": "2026-03-29", "days": 2, "stale": False})
        self.assertEqual(analysis["batter_zones"], {"pitches": 2, "raw_pitches": 2, "stale": False})
        self.assertFalse(any(entry["stale"] for entry in analysis.values()))

    def test_raw_newer_than_analysis_is_stale(self):
        # 분석 CSV 는 03-28 까지로 빌드됐는데 원본에 03-29 가 추가됐고 빌더가 다시 돌지 않은 상황.
        self.write_pitches("2026-03-28", ("2026-03-28", "20260328KTLG0"))
        self.write_analysis(2026, "2026-03-28", "2026-03-28", 1, zone_pitches=1)
        self.assertFalse(self.api(2026)["data"]["analysis"]["count_baseball"]["stale"])
        self.write_pitches("2026-03-29", ("2026-03-29", "20260329KTLG0"))
        analysis = self.api(2026)["data"]["analysis"]
        for key in ("pitcher_arsenal", "batter_vs_pitch", "count_baseball"):
            self.assertEqual(analysis[key],
                             {"first_date": "2026-03-28", "last_date": "2026-03-28", "days": 1, "stale": True})
        for key in ("batter_zones", "pitcher_zones"):
            self.assertEqual(analysis[key], {"pitches": 1, "raw_pitches": 2, "stale": True})

    def test_schedule_update_without_new_raw_is_seen(self):
        # 원본 캐시는 원본 파일만 본다. 일정 CSV 가 나중에 갱신돼도 바로 반영돼야 한다.
        self.write_pitches("2026-03-28", ("2026-03-28", "20260328KTLG0"))
        self.assertIsNone(self.api(2026)["data"]["regular_total"])
        self.write_schedule(2026, "20260328KTLG0", "20260329KTLG0")
        self.assertEqual(self.api(2026)["data"]["rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
