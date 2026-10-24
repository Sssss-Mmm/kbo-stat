"""build_player_games 회귀 테스트.

고정 입력(손으로 만든 투구 행)으로 정규시즌 필터·중복 제거·더블헤더·미확인 타석·
투수 아웃 수를 확인하고, 2025 원본이 있으면 공식 시즌 누적과의 오차가 기존 조사
기준선보다 커지지 않았는지 본다(data/ 는 git 에 없어 그때만 돈다).

실행: python -m unittest discover -s src -p "test_build_player_games.py" -v
"""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_player_games as b

GAME = "20250401LGOB0"


def pa(game, inning, half, batter, pitcher, out, text, results, clock):
    """한 타석의 투구 행들. half: 0=초(원정 공격), 1=말(홈 공격).

    batter·pitcher·text 는 공마다 다르게 줄 수 있다(리스트) — 타석 중 교체용.
    Ball/Strike 는 원본처럼 그 공을 던진 *뒤* 카운트다.
    """
    batting, fielding = ("LG", "두산") if half == 0 else ("두산", "LG")
    each = lambda v, i: v[i] if isinstance(v, list) else v  # noqa: E731
    rows, ball, strike = [], 0, 0
    for i, r in enumerate(results):
        ball += r == "B"
        strike += r in ("T", "S", "W", "V") or (r == "F" and strike < 2)
        rows.append(dict(
            Season=2025, GameId=f"{game}2025", Inning=inning, HomeAway=half, AwayTeam="LG", HomeTeam="두산",
            BatterTeam=batting, PitcherTeam=fielding, BatterId=each(batter, i), BatterName=f"타자{each(batter, i)}",
            PitcherId=each(pitcher, i), PitcherName=f"투수{each(pitcher, i)}", PitchNo=i + 1,
            PitchId=f"250401_{clock:04d}{i:02d}", PitchResult=r, IsInPlay=r == "H", IsBall=r == "B",
            Ball=float(ball), Strike=float(strike), Out=float(out), AtBatText=each(text, i),
        ))
    return rows


def schedule(*games, home_score=5, away_score=3, status="final"):
    return pd.DataFrame([dict(GameId=g, Date="2025-04-01", status=status, home_score=home_score,
                              away_score=away_score) for g in games])


def one_game(game=GAME):
    """1회초 3아웃(투수 90) + 1회말 홈팀 끝내기 안타(투수 80, 아웃 미확정)."""
    rows = []
    rows += pa(game, 1, 0, 1, 90, 0, "삼진 아웃", ["T", "S", "S"], 1)
    rows += pa(game, 1, 0, 2, 90, 1, "중견수 플라이 아웃", ["B", "H"], 2)
    rows += pa(game, 1, 0, 3, 90, 2, "좌익수 앞 1루타", ["H"], 3)
    rows += pa(game, 1, 0, 4, 90, 2, "볼넷", ["B", "B", "B", "B"], 4)
    rows += pa(game, 1, 0, 5, 90, 2, "유격수 땅볼 아웃 (유격수->1루수 송구아웃)", ["H"], 5)
    rows += pa(game, 1, 1, 11, 80, 0, "우익수 뒤 홈런", ["H"], 6)
    return rows


def build(rows, sched=None):
    raw = pd.DataFrame(rows).assign(_File="naver_kbo_pitches_2025-04-01.csv")
    return b.build_frame(b.pick_one_file_per_game(raw, 2025), sched if sched is not None else schedule(GAME))


def row(out, role, pid):
    return out[(out["Role"] == role) & (out["PlayerId"] == pid)].iloc[0]


class ClassifyTest(unittest.TestCase):
    def test_known_and_unknown_results(self):
        cases = {
            "삼진 아웃": "SO", "포수 스트라이크 낫아웃 폭투": "SO", "포수 쓰리번트 아웃": "SO",
            "자동 고의4구": "BB", "몸에 맞는 볼": "HBP", "중견수 희생플라이 아웃": "SF",
            "투수 희생번트 아웃 (투수->2루수 1루 터치아웃)": "SH", "좌익수 왼쪽 2루타": "2B",
            "우중간 3루타": "3B", "우익수 뒤 홈런 (홈런거리:110M)": "HR", "유격수 앞 내야안타": "1B",
            "유격수 병살타 아웃 (유격수->2루수->1루수 송구아웃)": "OUT", "유격수 땅볼 실책으로 출루": "REACH",
            "야수선택으로 출루": "REACH", "포수 타격방해로 출루": "INT",
            # 주자 이벤트·교체 문구는 타자 결과가 아니다 — 짐작하지 않는다.
            "홈인": "UNKNOWN", "2루까지 진루": "UNKNOWN", "도루실패아웃 (포수->유격수 태그아웃)": "UNKNOWN",
            "포스아웃 (유격수->2루수 2루 터치아웃)": "UNKNOWN", "타구맞음 아웃": "UNKNOWN",
            "대타 홍길순 (으)로 교체": "UNKNOWN", "": "UNKNOWN",
        }
        for text, expected in cases.items():
            self.assertEqual(b.classify(text), expected, text)


class BuildTest(unittest.TestCase):
    def test_batter_counts(self):
        out = build(one_game())
        self.assertEqual(row(out, "batter", 1)[["PA", "AB", "SO"]].tolist(), [1, 1, 1])
        self.assertEqual(row(out, "batter", 3)[["AB", "H"]].tolist(), [1, 1])
        self.assertEqual(row(out, "batter", 4)[["PA", "AB", "BB"]].tolist(), [1, 0, 1])
        self.assertEqual(row(out, "batter", 11)[["H", "HR", "HomeAway", "Team"]].tolist(), [1, 1, "home", "두산"])
        pitcher = row(out, "pitcher", 90)
        self.assertEqual(pitcher[["BF", "H", "BB", "SO", "HomeAway", "Team"]].tolist(), [5, 1, 1, 1, "home", "두산"])

    def test_postseason_and_unfinished_games_are_dropped(self):
        rows = one_game() + one_game("20251020LGOB0")  # 일정에 없는 경기(포스트시즌)
        out = build(rows)
        self.assertEqual(out["GameId"].unique().tolist(), [GAME])
        self.assertTrue(build(one_game(), schedule(GAME, status="scheduled")).empty)

    def test_duplicate_files_and_rows(self):
        """같은 경기가 날짜 구간 파일에 다시 실려도 한 번만, 같은 파일 안 완전 중복 행은 하나로."""
        day = pd.DataFrame(one_game()).assign(_File="naver_kbo_pitches_2025-04-01.csv")
        span = pd.DataFrame(one_game()).assign(_File="naver_kbo_pitches_2025-03-22_2025-04-01.csv")
        doubled = pd.concat([day, day.head(1), span], ignore_index=True)
        picked = b.pick_one_file_per_game(doubled, 2025)
        self.assertEqual(len(picked), len(day))
        out = b.build_frame(picked, schedule(GAME))
        self.assertEqual(row(out, "batter", 1)["PA"], 1)

    def test_duplicates_do_not_make_partial_file_win(self):
        """불완전 파일이 중복 행으로 부풀어도 고유 행이 더 많은 완전한 파일을 고른다."""
        full = pd.DataFrame(one_game()).assign(_File="naver_kbo_pitches_2025-04-01.csv")
        partial = pd.DataFrame(one_game()[:3]).assign(_File="naver_kbo_pitches_2025-04-02.csv")
        picked = b.pick_one_file_per_game(pd.concat([full] + [partial] * 6, ignore_index=True), 2025)
        self.assertEqual(len(picked), len(full))

    def test_distinct_pitches_with_missing_pitch_id_are_kept(self):
        """PitchId "-1" 은 경기당 여러 개일 수 있다 — (GameId, PitchId) 로 합치면 공이 사라진다."""
        rows = one_game()
        for r in rows[3:5]:  # 타자2 의 두 공
            r["PitchId"] = "-1"
        out = build(rows)
        self.assertEqual(row(out, "batter", 2)[["PA", "AB"]].tolist(), [1, 1])
        self.assertEqual(row(out, "pitcher", 90)["BF"], 5)

    def test_doubleheader_games_stay_separate(self):
        rows = one_game("20250401LGOB1") + one_game("20250401LGOB2")
        out = build(rows, schedule("20250401LGOB1", "20250401LGOB2"))
        batter = out[(out["Role"] == "batter") & (out["PlayerId"] == 1)]
        self.assertEqual(sorted(batter["DH"].tolist()), [1, 2])
        self.assertEqual(batter["PA"].tolist(), [1, 1])

    def test_one_row_per_player_game_and_role(self):
        rows = one_game()
        rows += pa(GAME, 2, 0, 90, 80, 0, "삼진 아웃", ["S", "S", "S"], 7)  # 투수 90 이 타석에도 선다
        out = build(rows)
        self.assertFalse(out.duplicated(["Role", "PlayerId", "GameId"]).any())
        self.assertEqual(sorted(out.loc[out["PlayerId"] == 90, "Role"]), ["batter", "pitcher"])

    def test_unknown_results_are_not_counted_as_hits_or_outs(self):
        rows = one_game()
        rows += pa(GAME, 2, 0, 6, 90, 0, "홈인", ["B", "H"], 7)              # 주자 문구가 붙은 타석
        rows += pa(GAME, 2, 0, 7, 90, 0, "좌익수 앞 1루타", ["B", "T"], 8)   # 안타 문구인데 인플레이 공 없음
        out = build(rows)
        # 타자6: 마지막 공이 인플레이라 타석은 끝났다 → PA 에는 넣되 결과는 모른다.
        six = row(out, "batter", 6)
        self.assertEqual(six[["PA", "AB", "H", "ResultUnknown", "PAUncertain"]].tolist(), [1, 0, 0, 1, 0])
        # 타자7: 1-1 에서 끝난 블록이라 완료 여부도 모른다 → PA 에도 안 넣는다.
        seven = row(out, "batter", 7)
        self.assertEqual(seven[["PA", "AB", "H", "ResultUnknown", "PAUncertain"]].tolist(), [0, 0, 0, 0, 1])
        pitcher = row(out, "pitcher", 90)
        self.assertEqual(pitcher[["BF", "H", "ResultUnknown", "PAUncertain"]].tolist(), [6, 1, 1, 1])
        self.assertFalse(pitcher["PAComplete"] or pitcher["StatsComplete"])

    def test_pitcher_outs_only_when_half_inning_is_verified(self):
        out = build(one_game())
        complete = row(out, "pitcher", 90)
        self.assertTrue(complete["OutsComplete"])
        self.assertEqual(complete["Outs"], 3)
        walkoff = row(out, "pitcher", 80)  # 끝내기 반이닝: 마지막 아웃 수를 알 수 없다
        self.assertFalse(walkoff["OutsComplete"])
        self.assertTrue(pd.isna(walkoff["Outs"]))

    def test_home_loss_in_final_half_is_still_three_outs(self):
        rows = one_game()[:-1]
        rows += pa(GAME, 1, 1, 11, 80, 0, "삼진 아웃", ["S", "S", "S"], 6)
        rows += pa(GAME, 1, 1, 12, 80, 1, "삼진 아웃", ["S", "S", "S"], 7)
        rows += pa(GAME, 1, 1, 13, 80, 2, "삼진 아웃", ["S", "S", "S"], 8)
        out = build(rows, schedule(GAME, home_score=1, away_score=3))
        self.assertEqual(row(out, "pitcher", 80)[["Outs", "OutsComplete"]].tolist(), [3, True])

    def test_shortened_game_final_half_ending_on_out_is_three_outs(self):
        """홈 리드 단축 경기(5회말 삼진으로 3아웃 종료)는 끝내기가 아니다(2025 20250613HTNC0)."""
        rows = one_game()[:-1]
        rows += pa(GAME, 1, 1, 11, 80, 0, "삼진 아웃", ["S", "S", "S"], 6)
        rows += pa(GAME, 1, 1, 12, 80, 1, "좌익수 앞 1루타", ["H"], 7)
        rows += pa(GAME, 1, 1, 13, 80, 1, "중견수 플라이 아웃", ["H"], 8)
        rows += pa(GAME, 1, 1, 14, 80, 2, "삼진 아웃", ["S", "S", "S"], 9)
        out = build(rows)  # 홈 5:3 승
        self.assertEqual(row(out, "pitcher", 80)[["Outs", "OutsComplete"]].tolist(), [3, True])
        # 2아웃 낫아웃은 타자가 살아 끝내기일 수 있어 여전히 미확정.
        rows[-1]["AtBatText"] = rows[-2]["AtBatText"] = rows[-3]["AtBatText"] = "포수 스트라이크 낫아웃 폭투"
        self.assertFalse(row(build(rows), "pitcher", 80)["OutsComplete"])

    def test_half_inning_cut_off_after_a_hit_is_not_trusted(self):
        """무사 1루타 한 구로 끝난 반이닝은 원본이 잘린 것이다 — 3아웃으로 채우지 않는다."""
        rows = pa(GAME, 1, 0, 1, 90, 0, "좌익수 앞 1루타", ["H"], 1)
        out = build(rows, schedule(GAME, home_score=1, away_score=3))
        self.assertEqual(row(out, "pitcher", 90)["OutsComplete"], False)
        self.assertTrue(pd.isna(row(out, "pitcher", 90)["Outs"]))
        # 경기 중간 반이닝이어도 1아웃 1루타로 끝났다면 믿지 않는다.
        rows += pa(GAME, 1, 1, 11, 80, 0, "삼진 아웃", ["S", "S", "S"], 2)
        rows += pa(GAME, 1, 1, 12, 80, 1, "삼진 아웃", ["S", "S", "S"], 3)
        rows += pa(GAME, 1, 1, 13, 80, 2, "삼진 아웃", ["S", "S", "S"], 4)
        rows[0]["Out"] = 1.0
        self.assertFalse(row(build(rows), "pitcher", 90)["OutsComplete"])

    def final_half(self, out, text, results, home_score=1, away_score=3):
        """1회초 정상 3아웃 + 경기 마지막 반이닝(1회말)이 아웃 out 에서 text 로 끝난 경기 → 투수 80."""
        rows = one_game()[:-1]
        rows += pa(GAME, 1, 1, 11, 80, 0, "삼진 아웃", ["S", "S", "S"], 6)
        if out == 2:
            rows += pa(GAME, 1, 1, 12, 80, 1, "삼진 아웃", ["S", "S", "S"], 7)
        rows += pa(GAME, 1, 1, 13, 80, out, text, results, 8)
        built = build(rows, schedule(GAME, home_score=home_score, away_score=away_score))
        return row(built, "pitcher", 80)[["Outs", "OutsComplete"]].tolist(), row(built, "pitcher", 90)

    def test_final_half_needs_evidence_for_remaining_outs(self):
        """경기 마지막 반이닝은 마지막 공 문구가 남은 아웃을 보여 줄 때만 3아웃 완결."""
        proven = [
            (1, "유격수 병살타 아웃 (유격수->2루수->1루수 송구아웃)", ["H"]),
            (2, "도루실패아웃 (포수->유격수 태그아웃)", ["B"]),
            (2, "중견수 플라이 아웃", ["H"]),
        ]
        for out, text, results in proven:
            self.assertEqual(self.final_half(out, text, results)[0], [3, True], text)
        unproven = [
            (2, "좌익수 앞 1루타", ["H"]),          # 주자 아웃으로 끝났는지, 콜드인지 모른다
            (2, "유격수 앞 땅볼로 출루", ["H"]),    # 야수선택은 아웃 없이 끝나기도 한다
            (1, "좌익수 플라이 아웃", ["H"]),       # 아웃 1개만 입증, 2개 필요
            (1, "", ["B"]),                          # 콜드(2025 20250719HHKT0)
            (2, "포수 스트라이크 낫아웃 폭투", ["S", "S", "S"]),
        ]
        for out, text, results in unproven:
            outs, complete = self.final_half(out, text, results)[0]
            self.assertFalse(complete, text)
            self.assertTrue(pd.isna(outs), text)

    def test_normal_halves_before_the_final_one_are_unchanged(self):
        """2아웃 1루타(주자 아웃)로 끝난 중간 반이닝은 다음 반이닝이 있어 그대로 3아웃."""
        rows = one_game()[:4]                                                     # 1회초 2아웃까지
        rows += pa(GAME, 1, 0, 5, 90, 2, "좌익수 앞 1루타", ["H"], 5)
        rows += pa(GAME, 1, 1, 11, 80, 0, "삼진 아웃", ["S", "S", "S"], 6)
        rows += pa(GAME, 1, 1, 12, 80, 1, "삼진 아웃", ["S", "S", "S"], 7)
        rows += pa(GAME, 1, 1, 13, 80, 2, "삼진 아웃", ["S", "S", "S"], 8)
        out = build(rows, schedule(GAME, home_score=1, away_score=3))
        self.assertEqual(row(out, "pitcher", 90)[["Outs", "OutsComplete"]].tolist(), [3, True])
        self.assertEqual(row(out, "pitcher", 80)[["Outs", "OutsComplete"]].tolist(), [3, True])

    def test_runner_event_only_final_half_is_not_filled(self):
        """Codex 3차 재현: 0아웃 '홈인' 볼 한 개로 끝난 반이닝에 아웃 3개를 만들지 않는다."""
        out = build(pa(GAME, 1, 0, 1, 90, 0, "홈인", ["B"], 1), schedule(GAME, home_score=1, away_score=3))
        self.assertEqual(row(out, "pitcher", 90)["OutsComplete"], False)

    def change_half(self, last_text, last_results, next_out=2):
        """1회초: 투수 90 삼진(0→1) → 90 마지막 타석(last_text) → 교체 후 91 이 Out=next_out 에서 시작해 3아웃."""
        rows = pa(GAME, 1, 0, 1, 90, 0, "삼진 아웃", ["S", "S", "S"], 1)
        rows += pa(GAME, 1, 0, 2, 90, 1, last_text, last_results, 2)
        rows += pa(GAME, 1, 0, 3, 91, next_out, "삼진 아웃", ["S", "S", "S"], 3)
        if next_out == 1:
            rows += pa(GAME, 1, 0, 4, 91, 2, "삼진 아웃", ["S", "S", "S"], 4)
        rows += pa(GAME, 1, 1, 11, 80, 0, "우익수 뒤 홈런", ["H"], 6)
        out = build(rows)
        return [row(out, "pitcher", pid)[["Outs", "OutsComplete"]].tolist() for pid in (90, 91)]

    def test_out_at_pitching_change_needs_evidence_on_previous_pitch(self):
        """교체 순간 Out 이 늘었는데 앞 투수 마지막 공이 아웃을 보여 주지 않으면(사구) 반이닝을 미확정으로."""
        (outs90, done90), (outs91, done91) = self.change_half("몸에 맞는 볼", ["B", "B", "B", "B"])
        self.assertFalse(done90)
        self.assertFalse(done91)
        self.assertTrue(pd.isna(outs90) and pd.isna(outs91))

    def test_out_on_previous_pitchers_play_stays_his(self):
        """앞 투수 공에서 땅볼 아웃·야수선택(포스아웃)으로 아웃이 났으면 앞 투수 몫으로 확정."""
        for text in ("유격수 땅볼 아웃 (유격수->1루수 송구아웃)", "유격수 앞 땅볼로 출루"):
            self.assertEqual(self.change_half(text, ["B", "H"]), [[2, True], [1, True]], text)

    def test_no_out_at_pitching_change_is_unaffected(self):
        self.assertEqual(self.change_half("볼넷", ["B", "B", "B", "B"], next_out=1), [[1, True], [2, True]])

    def test_missing_pitch_does_not_split_plate_appearance(self):
        """같은 타자 타석에서 공 하나가 원본에 없으면(번호 1→3) 한 타석이다 — 볼넷 두 번이 아니다."""
        rows = one_game()
        walk = [r for r in rows if r["BatterId"] == 4]
        rows.remove(walk[1])  # 2구 누락: PitchNo 1, 3, 4
        out = build(rows)
        self.assertEqual(row(out, "batter", 4)[["PA", "BB", "PAUncertain"]].tolist(), [1, 1, 0])
        self.assertEqual(row(out, "pitcher", 90)[["BF", "BB"]].tolist(), [5, 1])

    def test_half_reason_names_why_outs_are_untrusted(self):
        df = b.pitch_outs(b.order_plate_appearances(b.regular_season(
            b.ensure_teams(b.pick_one_file_per_game(pd.DataFrame(one_game()).assign(_File="f.csv"), 2025)),
            schedule(GAME))))
        reasons = df.groupby(["Inning", "HomeAway"])["_HalfReason"].first().to_dict()
        self.assertEqual(reasons, {(1, 0): "", (1, 1): "final_half_unproven"})
        last = df[df["HomeAway"] == 1].iloc[-1]
        self.assertTrue(pd.isna(last["_Outs"]))
        self.assertEqual(last["_OutsRaw"], 3)  # 대조용 원값은 남기되 확정값(_Outs)은 비운다

    def test_runner_out_counts_for_pitcher_on_the_mound(self):
        """타석 도중 도루자(Out 0→1)는 그 공을 던진 투수의 아웃이다."""
        rows = pa(GAME, 1, 0, 1, 90, 0, "삼진 아웃", ["S", "S", "S"], 1)           # 0 → 1
        rows += pa(GAME, 1, 0, 2, 90, 1, "중견수 플라이 아웃", ["B", "H"], 2)
        rows[4]["Out"] = 2.0                                                    # 1구 뒤 도루자: 1 → 2, 플라이로 3
        rows += pa(GAME, 1, 1, 11, 80, 0, "우익수 뒤 홈런", ["H"], 3)
        out = build(rows)
        self.assertEqual(row(out, "pitcher", 90)[["BF", "Outs", "OutsComplete"]].tolist(), [2, 3, True])

    def test_completed_unknown_plate_appearance(self):
        """문구는 주자 줄이지만 볼 4개로 끝난 타석: 완료 → PA/BF 포함, 결과는 불명."""
        rows = one_game()
        rows += pa(GAME, 2, 0, 6, 90, 0, "2루까지 진루", ["B", "B", "B", "B"], 7)
        out = build(rows)
        six = row(out, "batter", 6)
        self.assertEqual(six[["PA", "AB", "BB", "ResultUnknown"]].tolist(), [1, 0, 0, 1])
        self.assertTrue(six["PAComplete"])
        self.assertFalse(six["StatsComplete"])
        self.assertEqual(row(out, "pitcher", 90)[["BF", "BB", "ResultUnknown"]].tolist(), [6, 1, 1])

    def test_runner_event_only_block_is_not_a_plate_appearance(self):
        """반이닝 마지막 블록이 도루자로 끝나고 같은 타자가 다음 이닝 첫 타자 → 미완료 타석."""
        rows = one_game()
        rows += pa(GAME, 2, 0, 6, 90, 2, "도루실패아웃 (포수->유격수 태그아웃)", ["B"], 7)
        rows += pa(GAME, 3, 0, 6, 90, 0, "삼진 아웃", ["S", "S", "S"], 8)
        out = build(rows)
        six = row(out, "batter", 6)
        self.assertEqual(six[["PA", "SO", "ResultUnknown", "PAUncertain"]].tolist(), [1, 1, 0, 0])
        self.assertTrue(six["StatsComplete"])

    def test_normal_plate_appearance_has_no_uncertainty(self):
        out = build(one_game())
        pitcher = row(out, "pitcher", 90)
        self.assertEqual(pitcher[["BF", "H", "BB", "SO"] + b.UNCERTAIN_COUNTS].tolist(), [5, 1, 1, 1, 0, 0, 0])
        self.assertTrue(pitcher["PAComplete"] and pitcher["StatsComplete"])

    def _relief(self, results, text, change_at, bad_count=False):
        """투수 90 → 91 로 change_at 번째 공부터 교체된 타석 하나를 2회초에 붙인다."""
        pitchers = [90 if i < change_at else 91 for i in range(len(results))]
        rows = one_game() + pa(GAME, 2, 0, 6, pitchers, 0, text, results, 7)
        if bad_count:
            rows[-len(results)]["Ball"] = 0.0  # 1구 볼인데 카운트가 0 → 이후 카운트를 믿을 수 없다
        return build(rows)

    def test_walk_after_relief_at_hitters_count_goes_to_preceding_pitcher(self):
        out = self._relief(["B", "B", "B", "B"], "볼넷", change_at=2)      # 교체 시 2-0
        self.assertEqual(row(out, "pitcher", 90)[["BF", "BB"]].tolist(), [6, 2])
        self.assertEqual(row(out, "pitcher", 91)[["BF", "BB", "AttributionUncertain"]].tolist(), [0, 0, 0])

    def test_walk_after_relief_at_even_count_goes_to_relief_pitcher(self):
        out = self._relief(["B", "T", "B", "B", "B"], "볼넷", change_at=2)  # 교체 시 1-1
        self.assertEqual(row(out, "pitcher", 90)[["BF", "BB"]].tolist(), [5, 1])
        self.assertEqual(row(out, "pitcher", 91)[["BF", "BB"]].tolist(), [1, 1])

    def test_strikeout_after_relief_goes_to_relief_pitcher(self):
        out = self._relief(["B", "B", "T", "S", "S"], "삼진 아웃", change_at=3)  # 교체 시 2-1
        self.assertEqual(row(out, "pitcher", 90)[["BF", "SO"]].tolist(), [5, 1])
        self.assertEqual(row(out, "pitcher", 91)[["BF", "SO"]].tolist(), [1, 1])

    def test_three_pitchers_in_one_plate_appearance(self):
        """A→B→C. 9.16(h) 는 투수 둘 사이 규칙이라 셋이면 누구에게도 확정하지 않는다."""
        for results, text in ((["B", "B", "B", "B"], "볼넷"), (["B", "T", "S", "S"], "삼진 아웃"),
                              (["B", "T", "H"], "유격수 땅볼 아웃")):
            pitchers = [90, 91, 92, 92][:len(results)]
            out = build(one_game() + pa(GAME, 2, 0, 6, pitchers, 0, text, results, 7))
            for pitcher, bf in ((90, 5), (91, 0), (92, 0)):
                line = row(out, "pitcher", pitcher)
                self.assertEqual(line["AttributionUncertain"], 1, (text, pitcher))
                self.assertEqual(line["BF"], bf, (text, pitcher))
                self.assertFalse(line["PAComplete"] or line["StatsComplete"], (text, pitcher))
            self.assertEqual(row(out, "pitcher", 90)[["BB", "SO"]].tolist(), [1, 1], text)  # one_game 몫만
            self.assertEqual(row(out, "pitcher", 92)[["BB", "SO"]].tolist(), [0, 0], text)
            self.assertEqual(row(out, "batter", 6)[["PA", "PAComplete"]].tolist(), [1, True], text)

    def test_walk_after_relief_without_count_is_unattributed(self):
        out = self._relief(["B", "B", "B", "B"], "볼넷", change_at=2, bad_count=True)
        for pitcher in (90, 91):
            line = row(out, "pitcher", pitcher)
            self.assertEqual(line["AttributionUncertain"], 1, pitcher)
            self.assertFalse(line["PAComplete"] or line["StatsComplete"], pitcher)
        self.assertEqual(row(out, "pitcher", 90)[["BF", "BB"]].tolist(), [5, 1])  # 볼넷이 어디에도 안 붙는다
        self.assertEqual(row(out, "pitcher", 91)[["BF", "BB"]].tolist(), [0, 0])
        self.assertEqual(row(out, "batter", 6)[["PA", "BB", "PAComplete"]].tolist(), [1, 1, True])

    def _pinch(self, results, change_at, bad_count=False):
        batters = [6 if i < change_at else 7 for i in range(len(results))]
        texts = ["대타 타자7 (으)로 교체" if i < change_at else "삼진 아웃" for i in range(len(results))]
        plate = pa(GAME, 2, 0, batters, 90, 0, texts, results, 7)
        if bad_count:
            plate[0]["Ball"] = 1.0  # 1구 스트라이크인데 볼 1 → 카운트 복원 불가
        # 원본 파일처럼 대타 구간이 앞 타자 구간보다 먼저 실려 온다(붙어 있지도 않다).
        return build(one_game()[:3] + plate[change_at:] + one_game()[3:] + plate[:change_at])

    def test_pinch_hitter_strikeout_after_two_strikes_goes_to_first_batter(self):
        out = self._pinch(["T", "S", "S"], change_at=2)
        self.assertEqual(row(out, "batter", 6)[["PA", "AB", "SO"]].tolist(), [1, 1, 1])
        self.assertEqual(row(out, "batter", 7)[["PA", "SO"]].tolist(), [0, 0])

    def test_pinch_hitter_strikeout_before_two_strikes_goes_to_substitute(self):
        out = self._pinch(["T", "S", "S"], change_at=1)
        self.assertEqual(row(out, "batter", 6)[["PA", "SO"]].tolist(), [0, 0])
        self.assertEqual(row(out, "batter", 7)[["PA", "AB", "SO"]].tolist(), [1, 1, 1])

    def test_pinch_hitter_strikeout_without_count_is_unattributed(self):
        out = self._pinch(["T", "S", "S"], change_at=2, bad_count=True)
        for batter in (6, 7):
            line = row(out, "batter", batter)
            self.assertEqual(line[["PA", "SO", "AttributionUncertain"]].tolist(), [0, 0, 1], batter)
            self.assertFalse(line["PAComplete"] or line["StatsComplete"], batter)
        self.assertEqual(row(out, "pitcher", 90)[["BF", "SO", "PAComplete"]].tolist(), [6, 2, True])

    def test_uncertain_rows_never_claim_completeness(self):
        rows = one_game()
        rows += pa(GAME, 2, 0, 6, 90, 0, "홈인", ["B", "H"], 7)
        rows += pa(GAME, 2, 0, 7, 90, 0, "2루까지 진루", ["B"], 8)
        out = build(rows)
        uncertain = out[out[b.UNCERTAIN_COUNTS].fillna(0).sum(axis=1) > 0]
        self.assertFalse(uncertain["StatsComplete"].any())
        self.assertFalse(out.loc[out["PAUncertain"].fillna(0) > 0, "PAComplete"].any())
        self.assertTrue(out.loc[out[b.UNCERTAIN_COUNTS].fillna(0).sum(axis=1) == 0, "StatsComplete"].all())

    def test_unordered_half_inning_is_not_trusted(self):
        rows = one_game()
        for r in rows:
            if r["BatterId"] == 3:
                r["PitchId"] = "-1"  # 순서를 정할 근거가 없는 타석
        out = build(rows)
        self.assertFalse(row(out, "pitcher", 90)["OutsComplete"])


def count_ok(rows):
    return b._count_ok(pd.DataFrame(rows).assign(PaId=1)).tolist()


class CountValidationTest(unittest.TestCase):
    """_count_ok: 투구 결과 코드대로 볼·스트라이크가 움직였는지, 한 번 틀리면 계속 틀린지."""

    def test_ball_pitch_with_strike_increment_is_rejected(self):
        rows = pa(GAME, 1, 0, 1, 90, 0, "볼넷", ["B", "B"], 1)
        rows[1]["Strike"] = 1.0  # 볼인데 스트라이크도 +1
        self.assertEqual(count_ok(rows), [True, False])

    def test_strike_pitch_without_strike_increment_is_rejected(self):
        rows = pa(GAME, 1, 0, 1, 90, 0, "삼진 아웃", ["T", "S"], 1)
        rows[1]["Strike"] = 1.0  # 헛스윙인데 그대로
        self.assertEqual(count_ok(rows), [True, False])

    def test_foul_with_two_strikes_keeps_count(self):
        rows = pa(GAME, 1, 0, 1, 90, 0, "삼진 아웃", ["T", "S", "F", "F", "S"], 1)
        self.assertEqual([r["Strike"] for r in rows], [1, 2, 2, 2, 3])
        self.assertTrue(all(count_ok(rows)))
        rows[2]["Strike"] = 3.0  # 2스트라이크 파울에 스트라이크가 늘면 틀렸다
        self.assertEqual(count_ok(rows), [True, True, False, False, False])

    def test_normal_walk(self):
        rows = pa(GAME, 1, 0, 1, 90, 0, "볼넷", ["B", "T", "B", "F", "B", "B"], 1)
        self.assertTrue(all(count_ok(rows)))
        self.assertEqual((rows[-1]["Ball"], rows[-1]["Strike"]), (4, 2))

    def test_normal_strikeout(self):
        rows = pa(GAME, 1, 0, 1, 90, 0, "삼진 아웃", ["B", "T", "F", "S"], 1)
        self.assertTrue(all(count_ok(rows)))
        self.assertEqual((rows[-1]["Ball"], rows[-1]["Strike"]), (1, 3))

    def test_contaminated_count_stays_invalid(self):
        """2구가 틀린 뒤 3구는 2구 값 기준으로는 맞아 보여도 믿지 않는다."""
        rows = pa(GAME, 1, 0, 1, 90, 0, "볼넷", ["B", "B", "B"], 1)
        rows[1]["Strike"] = 1.0                            # 2구: 볼인데 2-1
        rows[2]["Ball"], rows[2]["Strike"] = 3.0, 1.0      # 3구: 2-1 → 3-1, 단독으로는 정상
        self.assertEqual(count_ok(rows), [True, False, False])

    def test_flag_mismatch_and_unknown_code_are_rejected(self):
        rows = pa(GAME, 1, 0, 1, 90, 0, "볼넷", ["B", "B"], 1)
        rows[1]["IsBall"] = False
        self.assertEqual(count_ok(rows), [True, False])
        rows = pa(GAME, 1, 0, 1, 90, 0, "볼넷", ["B", "B"], 1)
        rows[1]["PitchResult"] = "X"
        self.assertEqual(count_ok(rows), [True, False])

    def test_codex_case_wrong_two_two_does_not_charge_reliever(self):
        """실제 2-0 인데 볼 두 개가 1-1·2-2 로 기록된 뒤 교체, 구원이 볼 둘로 볼넷.

        예전 검증은 '볼 +1, 스트라이크 0~1' 이라 2-2 를 믿고 구원 투수에게 볼넷을 줬다
        (9.16(h) 대로면 2-0 은 앞 투수 몫). 카운트를 믿을 수 없으니 미확정이어야 한다.
        """
        rows = one_game() + pa(GAME, 2, 0, 6, [90, 90, 91, 91], 0, "볼넷", ["B", "B", "B", "B"], 7)
        plate = rows[-4:]
        for r, (ball, strike) in zip(plate, [(1, 1), (2, 2), (3, 2), (4, 2)]):
            r["Ball"], r["Strike"] = float(ball), float(strike)
        out = build(rows)
        for pitcher in (90, 91):
            self.assertEqual(row(out, "pitcher", pitcher)["AttributionUncertain"], 1, pitcher)
        self.assertEqual(row(out, "pitcher", 90)[["BF", "BB"]].tolist(), [5, 1])
        self.assertEqual(row(out, "pitcher", 91)[["BF", "BB"]].tolist(), [0, 0])
        self.assertEqual(row(out, "batter", 6)[["PA", "BB"]].tolist(), [1, 1])  # 타자 쪽은 확정


    def test_bunt_foul_bunt_miss_and_in_play(self):
        rows = pa(GAME, 1, 0, 1, 90, 0, "포수 쓰리번트 아웃", ["V", "F", "W"], 1)  # 번트헛스윙·파울·2S 번트파울
        self.assertEqual([r["Strike"] for r in rows], [1, 2, 3])
        self.assertTrue(all(count_ok(rows)))
        rows = pa(GAME, 1, 0, 1, 90, 0, "좌익수 앞 1루타", ["B", "H"], 1)
        self.assertTrue(all(count_ok(rows)))
        rows[1]["Strike"] = 1.0  # 인플레이는 카운트를 바꾸지 않는다
        self.assertEqual(count_ok(rows), [True, False])

    def test_pitch_after_terminal_count_is_rejected(self):
        rows = pa(GAME, 1, 0, 1, 90, 0, "볼넷", ["B", "B", "B", "B", "B"], 1)
        rows[4]["Ball"] = 4.0  # 볼 4개 뒤에 공이 또 있다
        self.assertEqual(count_ok(rows), [True, True, True, True, False])


class SubstituteNameTest(unittest.TestCase):
    def test_extracts_whole_name_only(self):
        cases = {
            "대타 홍길동 (으)로 교체": "홍길동",           # 2025 원본 형태
            "대타 타자7(으)로 교체": "타자7",
            "대타타자7 교체": "타자7",
            "대타  김가나다   (으)로   교체": "김가나다",
            "대타 김도로 교체": "김도로",                  # 괄호 없는 '로'는 조사로 떼지 않는다
            "대타 (으)로 교체": None, "대타 교체": None, "대타 김가나다 (으)로 투입": None,
            "2루까지 진루": None, "": None, None: None,
        }
        for text, expected in cases.items():
            self.assertEqual(b.substitute_name(text), expected, text)


class SubstitutionTest(unittest.TestCase):
    """타석 중 대타: 원본은 앞 타자 구간(교체 줄)과 대타 구간(결과 줄)이 따로, 순서도 뒤바뀌어 온다."""

    def _split(self, results, change_at, texts, batters=(6, 7), pitchers=None, sub_name=None, missing_key=None):
        """2회초 한 타석을 change_at 번째 공에서 나눠 파일에 '뒤 구간 먼저' 싣는다.

        sub_name: 대타(7)의 BatterName. missing_key: "pre"/"post" 구간의 PitchId 를 모두 "-1" 로.
        """
        n = len(results)
        bat = [batters[0] if i < change_at else batters[1] for i in range(n)]
        pit = pitchers or 90
        text = [texts[0] if i < change_at else texts[1] for i in range(n)]
        plate = pa(GAME, 2, 0, bat, pit, 0, text, results, 7)
        pre, post = plate[:change_at], plate[change_at:]
        for r in post:
            r["BatterName"] = sub_name or r["BatterName"]
        for r in {"pre": pre, "post": post}.get(missing_key, []):
            r["PitchId"] = "-1"
        return one_game()[:3] + post + one_game()[3:] + pre

    def assert_uncertain(self, line):
        self.assertFalse(line["PAComplete"])
        self.assertFalse(line["StatsComplete"])

    def test_observed_and_spacing_variants_merge(self):
        for note in ("대타 타자7 (으)로 교체", "대타 타자7(으)로 교체", "대타타자7 교체"):
            out = build(self._split(["B", "T", "S", "S"], 2, [note, "삼진 아웃"]))
            self.assertEqual(row(out, "batter", 7)[["PA", "AB", "SO", "PAComplete"]].tolist(), [1, 1, 1, True], note)
            self.assertEqual(row(out, "batter", 6)[["PA", "PAUncertain"]].tolist(), [0, 0], note)
            self.assertEqual(row(out, "pitcher", 90)[["BF", "SO", "PAComplete"]].tolist(), [6, 2, True], note)

    def test_note_naming_someone_else_is_not_trusted(self):
        out = build(self._split(["B", "T", "S", "S"], 2, ["대타 타자8 (으)로 교체", "삼진 아웃"]))
        for batter in (6, 7):
            self.assertEqual(row(out, "batter", batter)["SO"], 0, batter)  # 1-1 교체라 대타 몫이지만
            self.assert_uncertain(row(out, "batter", batter))             # 같은 타석인지 확신 못 함

    def test_missing_note_or_runner_event_instead_of_note(self):
        for note in ("", "2루까지 진루"):
            out = build(self._split(["B", "T", "S", "S"], 2, [note, "삼진 아웃"]))
            # 같은 타석인지 모르면 교체 시점 카운트를 쓰지 않으므로 삼진의 주인을 정하지 않는다.
            for batter in (6, 7):
                line = row(out, "batter", batter)
                self.assertEqual(line[["PA", "SO", "AttributionUncertain", "PAUncertain"]].tolist(),
                                 [0, 0, 1, 1], (note, batter))
                self.assert_uncertain(line)
            # 투수는 한 명이라 삼진·BF 는 그의 것이지만, 따로였다면 BF 가 하나 더였을 수 있다.
            pitcher = row(out, "pitcher", 90)
            self.assertEqual(pitcher[["BF", "SO", "PAUncertain"]].tolist(), [6, 2, 1], note)
            self.assert_uncertain(pitcher)

    def test_normal_consecutive_plate_appearances_are_not_merged(self):
        """앞 타석이 1구 인플레이로 끝나고 다음 타석 1구 행이 없어 번호만 이어진 경우(2025 19건)."""
        rows = one_game()
        rows += pa(GAME, 2, 0, 6, 90, 0, "좌익수 앞 1루타", ["H"], 7)
        # 1구 누락: 2구(번호 2)부터 — 앞 타석 1구 다음 번호라 '이어져' 보인다.
        nxt = pa(GAME, 2, 0, 7, 90, 0, "볼넷", ["B", "B", "B", "B"], 8)[1:]
        out = build(rows + nxt)
        self.assertEqual(row(out, "batter", 6)[["PA", "H", "PAComplete"]].tolist(), [1, 1, True])
        self.assertEqual(row(out, "batter", 7)[["PA", "BB", "PAComplete"]].tolist(), [1, 1, True])
        self.assertEqual(row(out, "pitcher", 90)["BF"], 7)

    def test_two_strike_pinch_hitter_strikeout_goes_to_first_batter(self):
        out = build(self._split(["T", "S", "F", "S"], 2, ["대타 타자7 (으)로 교체", "삼진 아웃"]))
        self.assertEqual(row(out, "batter", 6)[["PA", "AB", "SO", "PAComplete"]].tolist(), [1, 1, 1, True])
        self.assertEqual(row(out, "batter", 7)[["PA", "SO"]].tolist(), [0, 0])

    def test_pitcher_and_batter_change_on_the_same_pitch(self):
        """2025 실제 1건: 1-0 에서 대타와 구원 투수가 함께 들어왔다."""
        out = build(self._split(["B", "S", "F", "H"], 1, ["대타 타자7 (으)로 교체", "3루까지 진루"],
                                pitchers=[90, 91, 91, 91]))
        self.assertEqual(row(out, "batter", 7)[["PA", "ResultUnknown", "PAComplete"]].tolist(), [1, 1, True])
        self.assertEqual(row(out, "pitcher", 91)[["BF", "ResultUnknown"]].tolist(), [1, 1])
        self.assertEqual(row(out, "pitcher", 90)[["BF", "AttributionUncertain"]].tolist(), [5, 0])
        walk = build(self._split(["B", "B", "B", "B"], 2, ["대타 타자7 (으)로 교체", "볼넷"],
                                 pitchers=[90, 90, 91, 91]))
        self.assertEqual(row(walk, "batter", 7)[["PA", "BB"]].tolist(), [1, 1])     # 볼넷은 대타 몫
        self.assertEqual(row(walk, "pitcher", 90)[["BF", "BB"]].tolist(), [6, 2])  # 2-0 교체 볼넷은 앞 투수

    def test_partial_name_is_not_a_match(self):
        """Codex 재현: 새 타자는 '김가나'인데 교체 줄은 '김가나다'. 부분 일치로 확정하면 안 된다."""
        rows = self._split(["B", "T", "S", "S"], 2, ["대타 김가나다 (으)로 교체", "삼진 아웃"], sub_name="김가나")
        out = build(rows)
        for batter in (6, 7):
            line = row(out, "batter", batter)
            self.assertEqual(line[["PA", "SO", "AttributionUncertain"]].tolist(), [0, 0, 1], batter)
            self.assert_uncertain(line)
        self.assert_uncertain(row(out, "pitcher", 90))

    def test_full_name_match_merges(self):
        rows = self._split(["B", "T", "S", "S"], 2, ["대타 김가나다 (으)로 교체", "삼진 아웃"], sub_name="김가나다")
        out = build(rows)
        self.assertEqual(row(out, "batter", 7)[["PA", "SO", "PAComplete", "StatsComplete"]].tolist(), [1, 1, True, True])
        self.assertEqual(row(out, "batter", 6)[["PA", "PAUncertain", "AttributionUncertain"]].tolist(), [0, 0, 0])

    def test_unparseable_note_with_good_structure_is_uncertain(self):
        out = build(self._split(["B", "T", "S", "S"], 2, ["대타 교체", "삼진 아웃"]))
        for batter in (6, 7):
            self.assert_uncertain(row(out, "batter", batter))
        self.assertEqual(row(out, "pitcher", 90)[["BF", "PAUncertain"]].tolist(), [6, 1])

    def test_note_naming_someone_else_with_in_play_result(self):
        """결과가 땅볼이면 어느 해석이든 대타 몫이지만, 같은 타석인지 확신이 없어 확정 표시는 안 한다."""
        out = build(self._split(["B", "T", "H"], 2, ["대타 타자8 (으)로 교체", "유격수 땅볼 아웃"]))
        seven = row(out, "batter", 7)
        self.assertEqual(seven[["PA", "AB", "PAUncertain"]].tolist(), [1, 1, 1])
        self.assert_uncertain(seven)
        self.assertEqual(row(out, "batter", 6)[["PA", "PAUncertain"]].tolist(), [0, 1])

    def test_missing_time_key_on_either_side_is_never_a_sure_merge(self):
        for side in ("pre", "post"):
            rows = self._split(["B", "T", "S", "S"], 2, ["대타 타자7 (으)로 교체", "삼진 아웃"], missing_key=side)
            out = build(rows)
            for batter in (6, 7):
                line = row(out, "batter", batter)
                self.assertEqual(line[["PA", "SO", "AttributionUncertain", "PAUncertain"]].tolist(),
                                 [0, 0, 1, 1], (side, batter))
                self.assert_uncertain(line)
            pitcher = row(out, "pitcher", 90)
            self.assertEqual(pitcher[["BF", "SO", "PAUncertain"]].tolist(), [6, 2, 1], side)  # 두 타석으로 안 셈
            self.assert_uncertain(pitcher)

    def test_several_substitutions_in_one_plate_appearance(self):
        plate = pa(GAME, 2, 0, [6, 7, 8, 8], 90, 0,
                   ["대타 타자7 (으)로 교체", "대타 타자8 (으)로 교체", "삼진 아웃", "삼진 아웃"],
                   ["T", "S", "F", "S"], 7)
        out = build(one_game()[:3] + plate[2:] + plate[1:2] + one_game()[3:] + plate[:1])
        for batter in (6, 7, 8):
            line = row(out, "batter", batter)
            self.assertEqual(line[["PA", "SO", "AttributionUncertain"]].tolist(), [0, 0, 1], batter)
            self.assert_uncertain(line)
        self.assertEqual(row(out, "pitcher", 90)[["BF", "SO", "PAComplete"]].tolist(), [6, 2, True])


class CompletionSignalTest(unittest.TestCase):
    def test_last_pitch_in_play_completes(self):
        rows = one_game() + pa(GAME, 2, 0, 6, 90, 0, "홈인", ["B", "T", "H"], 7)
        six = row(build(rows), "batter", 6)
        self.assertEqual(six[["PA", "ResultUnknown", "PAUncertain"]].tolist(), [1, 1, 0])

    def test_in_play_before_last_pitch_is_a_conflict(self):
        rows = one_game() + pa(GAME, 2, 0, 6, 90, 0, "좌익수 앞 1루타", ["H", "B"], 7)
        out = build(rows)
        six = row(out, "batter", 6)
        self.assertEqual(six[["PA", "H", "PAUncertain"]].tolist(), [0, 0, 1])
        self.assertFalse(six["PAComplete"])
        self.assertEqual(row(out, "pitcher", 90)[["BF", "PAUncertain"]].tolist(), [5, 1])

    def _resumed(self, text, results):
        """2회초 마지막 블록의 타자6이 3회초 첫 타자로 다시 나온다 + 그 블록에 완료 신호."""
        rows = one_game()
        rows += pa(GAME, 2, 0, 6, 90, 2, text, results, 7)
        rows += pa(GAME, 3, 0, 6, 90, 0, "삼진 아웃", ["S", "S", "S"], 8)
        six = row(build(rows), "batter", 6)
        self.assertEqual(six[["PA", "SO", "PAUncertain"]].tolist(), [1, 1, 1])  # 3회 타석만 확정
        self.assertFalse(six["PAComplete"])

    def test_resumed_conflicts_with_four_balls(self):
        self._resumed("2루까지 진루", ["B", "B", "B", "B"])

    def test_resumed_conflicts_with_three_strikes(self):
        self._resumed("도루실패아웃 (포수->유격수 태그아웃)", ["T", "S", "S"])

    def test_resumed_conflicts_with_result_text(self):
        self._resumed("좌익수 앞 1루타", ["B", "H"])


RAW_2025 = b.RAW_DIR / "naver_kbo_pitches_2025-03-22.csv"


@unittest.skipUnless(RAW_2025.exists(), "2025 투구 원본이 없다(data/ 는 git 밖)")
class Official2025Test(unittest.TestCase):
    """공식 시즌 누적 대비 리그 합계 오차(%)가 기존 조사 기준선보다 커지면 실패한다.

    기준선 = 이전 조사(load_pitches + PitchNo==1 타석 분할 + 문구 판정)에서 잰 값.
    AB 는 기준선에서 뺀다: 이전 조사는 주자 문구 타석까지 타수로 세서 +0.24% 였고
    (빠진 타석과 우연히 상쇄), 지금은 미확인 타석을 타수에서 빼므로 공식값이
    [AB, AB+Unknown] 구간 안에 있는지를 따로 본다.
    """
    BASELINE = {
        "batter": {"H": 2.04, "2B": 1.88, "3B": 0.0, "HR": 1.85, "BB": 4.69, "HBP": 2.49, "SO": 0.92},
        "pitcher": {"H": 1.86, "BB": 3.88, "SO": 0.72},
    }

    @classmethod
    def setUpClass(cls):
        cls.games = b.build_frame(b.load_season_pitches(2025), b.load_schedule(2025))
        cls.report = {role: t.set_index("stat") for role, t in b.compare_official(cls.games, 2025).items()}

    def test_all_regular_season_games_covered(self):
        self.assertEqual(self.games["GameId"].nunique(), 720)

    def test_error_not_worse_than_baseline(self):
        for role, stats in self.BASELINE.items():
            for stat, limit in stats.items():
                err = abs(self.report[role].loc[stat, "diff_pct"])
                self.assertLessEqual(err, limit, f"{role} {stat} 오차 {err}% > 기준선 {limit}%")

    def test_official_at_bats_within_unknown_range(self):
        bat = self.report["batter"].loc["AB"]
        unknown = self.games.loc[self.games["Role"] == "batter", b.UNCERTAIN_COUNTS].sum().sum()
        self.assertLessEqual(bat["built"], bat["official"])
        self.assertLessEqual(bat["official"], bat["built"] + unknown)

    def test_verified_outs_match_official_innings(self):
        outs = self.report["pitcher"].loc["Outs"]
        self.assertLess(abs(outs["diff_pct"]), 0.5)
        self.assertGreaterEqual(outs["exact_pct"], 95.0)


if __name__ == "__main__":
    unittest.main()
