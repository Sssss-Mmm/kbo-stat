"""P3-A 타자 고급 지표(services/batting_advanced.py). 픽스처는 합성 데이터만 쓴다(가상 선수·숫자).

RealDataTest 는 로컬 수집 자료를 읽기만 하는 검증이다 — `KBO_DATA_DIR`(기본: 저장소 data/)에 자료가 없으면 건너뛴다.
실제 이름·값은 출력하지 않고 개수·비율만 확인한다.
"""
import math
import os
import unittest
from pathlib import Path

from services import batting_advanced as ba
from utils import PROCESSED_DIR

PROV = {"season": 2099, "scope": "player_season", "source": "test"}


def row(pid=1, name="가상타자", team="팀A", season=2099, **kw):
    base = {"Season": season, "PlayerId": pid, "선수명": name, "팀명": team, "AB": 100, "H": 30, "2B": 5, "3B": 1,
            "HR": 4, "BB": 10, "HBP": 2, "SO": 20, "BABIP": 0.315}
    return base | kw


def kbo(name="가상타자", team="팀A", season=2099, **kw):
    base = {"Season": season, "선수명": name, "팀명": team, "AB": 100, "H": 30, "BB": 10, "SO": 20, "HBP": 2, "PA": 115}
    return base | kw


def calc(games=10, complete=10, **kw):
    return {"games": games, "complete_games": complete, "AB": 100, "HBP": 2, "SF": 2, "SH": 1} | kw


class FormulaTest(unittest.TestCase):
    def test_iso_from_counts(self):
        m = ba.iso(row(), PROV)
        self.assertEqual((m["status"], m["display"]), (ba.CALCULATED, 0.19))   # (5 + 2·1 + 3·4) / 100
        self.assertEqual(m["provenance"], PROV)

    def test_babip_needs_sf_and_keeps_precision(self):
        m = ba.babip(row(AB=7, H=3, HR=0, SO=1, SF=0, **{"2B": 0, "3B": 0}), PROV)  # 3 / 6
        self.assertEqual(m["value"], 0.5)
        m = ba.babip(row(AB=10, H=3, HR=0, SO=1, SF=0, **{"2B": 0, "3B": 0}), PROV)  # 3 / 9 — 정밀값은 그대로, 반올림은 display 만
        self.assertAlmostEqual(m["value"], 1 / 3, places=12)
        self.assertEqual(m["display"], 0.333)
        missing = ba.babip(row(), PROV)  # SF 없음 — 0 으로 가정하지 않는다
        self.assertEqual((missing["status"], missing["value"]), (ba.UNAVAILABLE, None))
        self.assertIn("SF", missing["reason"])

    def test_rates_per_pa(self):
        pa = {"value": 115, "basis": ba.PA_KBO, "reason": None}
        bb, k = ba.rate_per_pa("bb_pct", "BB", row(), pa, PROV), ba.rate_per_pa("k_pct", "SO", row(), pa, PROV)
        self.assertAlmostEqual(bb["value"], 1000 / 115, places=10)
        self.assertEqual((bb["display"], k["display"]), (8.7, 17.4))
        self.assertEqual(bb["provenance"]["pa_basis"], ba.PA_KBO)

    def test_round_half_up_boundaries(self):
        # ISO 0.0005 → 0.001 (은행가 반올림이면 0.000)
        m = ba.iso(row(AB=2000, H=1, **{"2B": 0, "3B": 0}, HR=0) | {"2B": 1, "H": 1}, PROV)
        self.assertEqual((m["value"], m["display"]), (0.0005, 0.001))
        # BB% 0.25 → 0.3, 12.5 → 12.5
        pa = {"value": 400, "basis": ba.PA_KBO, "reason": None}
        self.assertEqual(ba.rate_per_pa("bb_pct", "BB", row(BB=1, AB=300), pa, PROV)["display"], 0.3)
        pa = {"value": 8, "basis": ba.PA_KBO, "reason": None}
        self.assertEqual(ba.rate_per_pa("bb_pct", "BB", row(AB=6, H=1, BB=1, SO=1, HBP=0, **{"2B": 0, "3B": 0}, HR=0), pa,
                                        PROV)["display"], 12.5)

    def test_zero_denominators(self):
        self.assertEqual(ba.iso(row(AB=0, H=0, **{"2B": 0, "3B": 0}, HR=0, SO=0), PROV)["status"], ba.ZERO_DENOMINATOR)
        z = ba.babip(row(AB=5, H=1, HR=1, SO=4, SF=0, **{"2B": 0, "3B": 0}), PROV)  # 5 − 4 − 1 + 0 = 0
        self.assertEqual((z["status"], z["value"], z["display"]), (ba.ZERO_DENOMINATOR, None, None))
        pa0 = {"value": 0, "basis": ba.PA_KBO, "reason": None}
        self.assertEqual(ba.rate_per_pa("k_pct", "SO", row(AB=0, H=0, BB=0, SO=0, HBP=0, **{"2B": 0, "3B": 0}, HR=0), pa0,
                                        PROV)["status"], ba.ZERO_DENOMINATOR)

    def test_missing_inputs_give_null_and_reason(self):
        for value in (None, "", float("nan")):
            m = ba.iso(row(**{"3B": value}), PROV)
            self.assertEqual((m["status"], m["value"]), (ba.UNAVAILABLE, None))
            self.assertEqual(m["reason"], "입력 없음: 3B")
        no_pa = {"value": None, "basis": None, "reason": "PA 자료 없음"}
        m = ba.rate_per_pa("bb_pct", "BB", row(), no_pa, PROV)
        self.assertEqual((m["status"], m["value"], m["reason"]), (ba.UNAVAILABLE, None, "PA 자료 없음"))

    def test_impossible_combinations_are_not_computed(self):
        cases = {"H > AB": row(H=101), "HR > H": row(H=3, HR=4, **{"2B": 0, "3B": 0}),
                 "2B+3B+HR > H": row(H=8, **{"2B": 5, "3B": 1}, HR=4), "H+SO > AB": row(SO=80),
                 "음수": row(HR=-1), "정수가 아닌": row(AB=100.5)}
        for text, r in cases.items():
            m = ba.iso(r, PROV) if text not in ("H+SO > AB",) else ba.babip(r | {"SF": 0}, PROV)
            self.assertEqual(m["status"], ba.UNAVAILABLE, text)
            self.assertIn(text, m["reason"])
        pa = {"value": 100, "basis": ba.PA_KBO, "reason": None}  # AB 100 + BB 10 + HBP 2 > PA 100
        self.assertIn("AB+BB+HBP > PA", ba.rate_per_pa("bb_pct", "BB", row(), pa, PROV)["reason"])
        # 이름 같은 다른 열은 개수로 보지 않는다
        self.assertEqual(ba.iso(row(선수명="문자열 이름"), PROV)["status"], ba.CALCULATED)

    def test_source_value_is_never_calculated(self):
        s = ba.source_value("babip", 0.315, PROV | {"source": "naver"})
        self.assertEqual((s["status"], s["value"], s["display"]), (ba.SOURCE, 0.315, 0.315))
        for bad in (None, "", "abc", float("nan"), float("inf")):
            self.assertEqual(ba.source_value("babip", bad, PROV)["status"], ba.UNAVAILABLE)


class SourceBabipTest(unittest.TestCase):
    def test_source_zero_for_undefined_denominator_is_not_used(self):
        z = ba.source_babip(row(AB=0, H=0, HR=0, SO=0, BABIP=0.0, **{"2B": 0, "3B": 0}), PROV)
        self.assertEqual((z["status"], z["value"]), (ba.UNAVAILABLE, None))
        self.assertIn("분모 0", z["reason"])
        z = ba.source_babip(row(AB=3, H=0, HR=0, SO=3, BABIP=0.0, **{"2B": 0, "3B": 0}), PROV)  # AB−SO−HR = 0
        self.assertEqual(z["status"], ba.UNAVAILABLE)
        real_zero = ba.source_babip(row(AB=10, H=0, HR=0, SO=2, BABIP=0.0, **{"2B": 0, "3B": 0}), PROV)  # 인플레이 8타수 무안타
        self.assertEqual((real_zero["status"], real_zero["value"]), (ba.SOURCE, 0.0))
        self.assertEqual(ba.source_babip(row(), PROV)["status"], ba.SOURCE)


class LinkTest(unittest.TestCase):
    def ids(self, *rows):
        return list(rows)

    def test_same_name_same_team_split_by_ab_h(self):
        ids = [row(pid=1, AB=446, H=120), row(pid=2, AB=16, H=3)]  # 같은 팀 동명이인
        links = ba.link_kbo_records([kbo(AB=446, H=120)], ids, 2099)
        self.assertEqual((links[0]["status"], links[0]["player_id"]), (ba.LINKED, 1))

    def test_duplicate_candidates_are_ambiguous(self):
        ids = [row(pid=1), row(pid=2)]  # 이름·팀·AB·H 가 모두 같은 두 ID
        link = ba.link_kbo_records([kbo()], ids, 2099)[0]
        self.assertEqual((link["status"], link["player_id"]), (ba.AMBIGUOUS, None))

    def test_one_id_claimed_by_two_records_is_ambiguous(self):
        links = ba.link_kbo_records([kbo(), kbo()], [row(pid=1)], 2099)
        self.assertEqual([(lk["status"], lk["player_id"]) for lk in links], [(ba.AMBIGUOUS, None)] * 2)

    def test_team_missing_and_transfers_are_not_linked(self):
        self.assertEqual(ba.link_kbo_records([kbo(team=None)], [row()], 2099)[0]["status"], ba.TEAM_MISSING)
        self.assertEqual(ba.link_kbo_records([kbo()], [row(team=float("nan"))], 2099)[0]["status"], ba.UNMATCHED)
        moved = ba.link_kbo_records([kbo(team="팀B")], [row(team="팀A")], 2099)[0]  # 이적 — 소속이 다르게 잡힘
        self.assertEqual((moved["status"], moved["player_id"]), (ba.UNMATCHED, None))

    def test_season_and_record_checks(self):
        self.assertEqual(ba.link_kbo_records([kbo(season=2098)], [row()], 2099)[0]["status"], ba.UNMATCHED)
        self.assertEqual(ba.link_kbo_records([kbo()], [row(season=2098)], 2099)[0]["status"], ba.UNMATCHED)
        bad = ba.link_kbo_records([kbo(BB=11)], [row()], 2099)[0]
        self.assertEqual((bad["status"], bad["reason"]), (ba.RECORD_MISMATCH, "연결 후 기록 불일치: BB"))
        self.assertEqual(ba.link_kbo_records([kbo(선수명=" 가상 타자 ")], [row()], 2099)[0]["status"], ba.LINKED)


class PaSelectionTest(unittest.TestCase):
    def test_priority_kbo_then_assembled_then_none(self):
        linked = {"status": ba.LINKED, "player_id": 1}
        self.assertEqual(ba.select_pa(kbo(), linked, row(), calc())["basis"], ba.PA_KBO)
        mismatch = {"status": ba.RECORD_MISMATCH, "player_id": 1}
        pa = ba.select_pa(kbo(), mismatch, row(), calc())
        self.assertEqual((pa["basis"], pa["value"]), (ba.PA_ASSEMBLED, 100 + 10 + 2 + 2 + 1))
        none = ba.select_pa(None, None, row(), None)
        self.assertEqual((none["value"], none["basis"]), (None, None))
        self.assertIn("규정 미달", none["reason"])

    def test_assembled_pa_conditions(self):
        self.assertIn("미완결 경기 2개", ba.assembled_pa(row(), calc(complete=8))[1])
        self.assertIn("경기 없음", ba.assembled_pa(row(), calc(games=0, complete=0))[1])
        self.assertIn("AB·HBP", ba.assembled_pa(row(), calc(AB=99))[1])
        self.assertIn("AB·HBP", ba.assembled_pa(row(), calc(HBP=3))[1])
        self.assertIn("SF", ba.assembled_pa(row(), calc(SF=None))[1])
        self.assertIsNone(ba.kbo_pa(kbo(PA=100), {"status": ba.LINKED}))  # PA < AB+BB+HBP — 검증 실패


class PlayerSeasonTest(unittest.TestCase):
    def test_complete_player(self):
        out = ba.player_season(row(), 2099, calc=calc())
        self.assertEqual(out["pa"]["basis"], ba.PA_ASSEMBLED)
        self.assertEqual(out["babip"]["status"], ba.CALCULATED)  # (30 − 4) / (100 − 20 − 4 + 2) = 26/78
        self.assertAlmostEqual(out["babip"]["value"], 26 / 78, places=12)
        self.assertEqual(out["babip"]["provenance"]["source"], "naver_season_stats+pitch_calc_sf")
        self.assertEqual((out["babip_source"]["status"], out["babip_source"]["value"]), (ba.SOURCE, 0.315))
        self.assertEqual({out[k]["status"] for k in ("iso", "bb_pct", "k_pct")}, {ba.CALCULATED})
        for k in ("iso", "babip", "bb_pct", "k_pct"):
            self.assertEqual(out[k]["provenance"]["season"], 2099)
            self.assertEqual(out[k]["provenance"]["scope"], "player_season")

    def test_no_pitch_data(self):
        out = ba.player_season(row(), 2099)
        self.assertEqual((out["babip"]["status"], out["bb_pct"]["status"], out["k_pct"]["status"]), (ba.UNAVAILABLE,) * 3)
        self.assertEqual(out["iso"]["status"], ba.CALCULATED)
        self.assertEqual(out["babip_source"]["status"], ba.SOURCE)  # 출처 값은 따로 남는다
        self.assertIsNone(out["babip"]["value"])


class LeagueTest(unittest.TestCase):
    def test_sum_over_sum_not_mean_of_rates(self):
        players = [{"BB": 10, "pa": {"value": 100}}, {"BB": 1, "pa": {"value": 10}}]
        m = ba.league_rate("bb_pct", "BB", players)
        self.assertAlmostEqual(m["value"], 11 / 110 * 100, places=10)  # 10.0 (평균이면 10.0 — 다른 예로 확인)
        players = [{"BB": 20, "pa": {"value": 100}}, {"BB": 0, "pa": {"value": 10}}]
        self.assertAlmostEqual(ba.league_rate("bb_pct", "BB", players)["value"], 20 / 110 * 100, places=10)  # 평균은 10.0

    def test_partial_pa_coverage_is_not_a_league_value(self):
        players = [{"BB": 10, "pa": {"value": 100}}, {"BB": 1, "pa": {"value": None}}]
        m = ba.league_rate("bb_pct", "BB", players)
        self.assertEqual((m["status"], m["value"]), (ba.UNAVAILABLE, None))
        self.assertIn("PA 미확인 선수 1명", m["reason"])
        self.assertEqual(ba.league_rate("bb_pct", "BB", [])["status"], ba.UNAVAILABLE)


DATA = Path(os.environ.get("KBO_DATA_DIR") or PROCESSED_DIR.parent)


@unittest.skipUnless((DATA / "processed" / "kbo_player_games_2025.csv").exists(), "로컬 수집 자료 없음(data/ 는 git 밖)")
class RealDataTest(unittest.TestCase):
    """로컬 자료 읽기 전용 검증 — 설계 보고서의 교차 검증을 회귀로 고정한다."""

    @classmethod
    def setUpClass(cls):
        cls.s25 = ba.load_season(DATA, 2025)

    def test_iso_matches_source_iso_every_season(self):
        """출처 ISO 는 '반올림 SLG − 반올림 AVG' 다(2007–2026 전원 확인). 우리 값은 개수에서 정확히 계산하므로
        차이는 그 반올림 손실(≤ 0.001)뿐이어야 하고, 출처 ISO 는 우리 SLG·AVG 를 반올림해 뺀 값과 정확히 같아야 한다."""
        from fractions import Fraction
        from services.season_service import round_half_up
        checked = 0
        for season in range(2007, 2027):
            for r in ba.load_season(DATA, season)["naver"]:
                if not r["AB"]:
                    continue
                m = ba.iso(r, PROV)
                self.assertEqual(m["status"], ba.CALCULATED)
                self.assertLessEqual(abs(m["value"] - r["ISO"]), 0.001 + 1e-9)
                tb = r["H"] + r["2B"] + 2 * r["3B"] + 3 * r["HR"]
                rounded = round_half_up(Fraction(tb, r["AB"])) - round_half_up(Fraction(r["H"], r["AB"]))
                self.assertAlmostEqual(rounded, r["ISO"], places=9)
                checked += 1
        self.assertGreater(checked, 4000)

    def test_links_2025(self):
        links = ba.link_kbo_records(self.s25["kbo"], self.s25["naver"], 2025)
        status = [lk["status"] for lk in links]
        self.assertEqual(status.count(ba.AMBIGUOUS), 0)
        self.assertGreaterEqual(status.count(ba.LINKED), 40)
        ids = [lk["player_id"] for lk in links if lk["status"] == ba.LINKED]
        self.assertEqual(len(ids), len(set(ids)))  # 한 ID 에 두 행이 붙지 않는다

    def test_assembled_pa_equals_kbo_pa_for_complete_players(self):
        naver = {int(r["PlayerId"]): r for r in self.s25["naver"]}
        compared = 0
        for lk, k in zip(ba.link_kbo_records(self.s25["kbo"], self.s25["naver"], 2025), self.s25["kbo"]):
            if lk["status"] != ba.LINKED:
                continue
            pa, _ = ba.assembled_pa(naver[lk["player_id"]], self.s25["calc"].get(lk["player_id"]))
            if pa:
                self.assertEqual(pa["value"], int(k["PA"]))
                compared += 1
        self.assertGreaterEqual(compared, 5)

    def test_calculated_babip_equals_source_babip_2025(self):
        compared = 0
        for r in self.s25["naver"]:
            out = ba.player_season(r, 2025, calc=self.s25["calc"].get(int(r["PlayerId"])))
            if out["babip"]["status"] == ba.CALCULATED:
                self.assertEqual(out["babip_source"]["status"], ba.SOURCE)
                self.assertLessEqual(abs(out["babip"]["value"] - out["babip_source"]["value"]), 0.001 + 1e-9)
                compared += 1
        self.assertGreaterEqual(compared, 100)

    def test_source_babip_zero_placeholders_are_dropped(self):
        dropped = 0
        for r in self.s25["naver"]:
            m = ba.source_babip(r, PROV)
            if r["AB"] - r["SO"] - r["HR"] <= 0:
                self.assertEqual(m["status"], ba.UNAVAILABLE)  # 출처는 이 행들에 0.000 을 적는다
                dropped += 1
            else:
                self.assertEqual(m["status"], ba.SOURCE)
        self.assertGreater(dropped, 50)

    def test_no_value_is_silently_zero_filled(self):
        for r in self.s25["naver"]:
            out = ba.player_season(r, 2025, calc=self.s25["calc"].get(int(r["PlayerId"])))
            for k in ("iso", "babip", "bb_pct", "k_pct"):
                m = out[k]
                self.assertEqual(m["value"] is None, m["status"] in (ba.UNAVAILABLE, ba.ZERO_DENOMINATOR))
                if m["value"] is None:
                    self.assertTrue(m["reason"])
                else:
                    self.assertTrue(math.isfinite(m["value"]))


if __name__ == "__main__":
    unittest.main()
