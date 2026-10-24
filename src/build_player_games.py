"""
Build per-player, per-game batting and pitching lines from the Naver pitch CSVs.

    data/processed/kbo_player_games_{season}.csv

한 행 = (Role, PlayerId, GameId). Role 은 batter / pitcher 둘이고, 투수가 타석에
선 경기는 같은 선수·같은 경기라도 역할별로 한 행씩이다.

원본은 투구 1구 = 1행이고 타석 결과 문구(AtBatText)가 그 타석의 모든 행에 실려
온다. 여기서는 투구를 타석으로 묶고, 문구를 **화이트리스트**로만 분류한다.
크롤러는 타자 이름이 안 맞으면 마지막 텍스트 줄로 떨어지는데(at_bat_result),
그 줄이 '홈인'·'2루까지 진루'·'포스아웃' 같은 주자 이벤트일 때가 있다
(2025 정규시즌 약 660타석). 이런 타석의 결과는 안타·아웃으로 짐작하지 않는다.

타석 하나는 세 가지를 따로 판정한다.
  존재  — 투구 행이 있는 타석 블록. 원본에 행이 아예 없는 타석은 여기서 알 수 없다.
  완료  — 결과 문구를 인식했거나, 문구는 몰라도 마지막 공이 인플레이·볼 4개·
          스트라이크 3개면 완료. 반이닝 마지막 블록이고 같은 타자가 다음 이닝 첫
          타자로 다시 나오면 미완료(주자 아웃으로 이닝 종료) — 타석으로 세지 않는다.
          둘 다 아니면 완료 여부 불명.
  귀속  — 타석 중 투수·타자가 바뀌면 공식 기록 규칙(아래)으로 정하고, 볼카운트를
          복원할 수 없거나 규칙상 결과에 따라 갈리는데 결과를 모르면 정하지 않는다.

데이터 계약(소비자는 이것만 믿는다):
  PA / BF            완료되고 그 선수에게 귀속이 확정된 타석 수. 결과 불명 타석 포함.
  AB, H, BB, …       결과까지 인식된 타석에서만 센 값.
  ResultUnknown      PA/BF 에 들어갔지만 결과를 모르는 타석 수.
  PAUncertain        완료 여부를 알 수 없거나 완료·미완료 신호가 충돌하는 타석 수
                     (PA/BF 에 안 들어감). 같은 타석인지 불확실하게 합친 대타 블록
                     (_SubUncertain)은 합친 타석 하나는 완료라 PA/BF 에 들어가고, 앞 구간이
                     따로 한 타석이었을 가능성 하나를 여기에 더한다 — 실제 값은
                     [PA, PA + PAUncertain] 안에 있다.
  AttributionUncertain  완료됐지만 이 선수 몫인지 확정하지 못한 타석 수(PA/BF 에 안 들어감).
  PAComplete         PAUncertain == AttributionUncertain == 0 → 관측된 타석 블록 기준으로 PA/BF 가 확정값.
                     투구 행이 하나도 없는 타석(자동 고의4구 — 2025 박스스코어 대조에서 확인)은
                     원본에 없어 여기서 알 수 없다. 공식 값과의 차이는 verify_player_games 의
                     대조 결과로만 드러나며, 계산 플래그를 외부 기록으로 고치지 않는다.
  StatsComplete      PAComplete 이고 ResultUnknown == 0 → AB·H·BB 와 그 비율이 확정값.
StatsComplete=False 인 행의 타율·출루율 같은 비율은 하한/근사일 뿐이다 — 정확한
값으로 표시하지 말 것. 경기를 합쳐 구간 비율을 낼 때도 구간 안에 False 가 하나라도
있으면 마찬가지다.

타석 중 교체의 귀속 규칙(공식야구규칙 9.15(b)·9.16(h), KBO 는 같은 조항을 쓴다):
  투수 교체  교체 시 카운트가 2-0·2-1·3-0·3-1·3-2 이고 결과가 볼넷이면 앞 투수,
             그 밖의 모든 결과(카운트 불문)는 구원 투수. 볼넷·결과불명인데 카운트를
             복원할 수 없으면 미확정.
  대타      앞 타자가 2스트라이크에서 물러나고 대타가 삼진이면 삼진·타수는 앞 타자,
             그 밖의 결과(볼넷 포함)는 대타. 삼진·결과불명인데 카운트를 복원할 수
             없거나 2스트라이크인데 결과를 모르면 미확정.

투구 정렬은 PitchId(시각) 단독으로 하지 않는다. 원본 파일은 타석 순서가 섞여
있고(타석 안의 공은 오름차순), PitchId 가 "-1" 인 공이 경기당 최대 6개 있어
정렬하면 맨 앞으로 튄다. 그래서 파일 순서대로 타석을 묶은 뒤, 타석을 그 안의
유효한 첫 PitchId 로 정렬한다. 같은 이유로 load_pitches() 의 (GameId, PitchId)
중복 제거는 쓰지 않는다 — 같은 경기의 "-1" 공들이 서로 다른 공인데도 하나로
합쳐진다(2025 원본 19구). 중복은 경기를 파일 하나에서만 읽는 것으로 없앤다.

투수 아웃 수는 Out(그 공을 던지기 *전* 아웃 수)의 증가분으로 센다. 도루자·견제사
같은 주자 아웃도 그때 마운드의 투수 몫으로 잡힌다. 반이닝이 0아웃에서 시작해
정확히 3아웃으로 끝나지 않거나, 마지막 아웃을 입증할 수 없거나(경기 마지막 반이닝인데
마지막 공 문구가 남은 아웃을 보여 주지 않음 — 끝내기·콜드, pitch_outs), 순서를
정할 수 없는 타석이 낀 반이닝, 투수 교체 순간 아웃의 주인을 가릴 수 없는 반이닝(pitch_outs)을
던진 투수-경기는 OutsComplete=False 이고 Outs 를 비운다. 이닝(IP)·ERA·WHIP 은 만들지 않는다.

Usage:
    python src/build_player_games.py --year 2025
    python src/build_player_games.py --year 2025 --compare   # 공식 시즌 누적과 대조
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import re
from pathlib import Path

import pandas as pd

import csv_guard
from build_count_metrics import HBP_TEXT, WALK_TEXT
from build_pitch_arsenal import STRIKEOUT_TEXT
from build_zone_metrics import PROCESSED_DIR, RAW_DIR, _file_covers_season, current_kbo_year, ensure_teams
from crawl_naver_pitch_zones import is_hit_description

SCHEDULE_DIR = RAW_DIR.parent / "kbo_official"

# STRIKEOUT_TEXT 는 "낫 아웃"(띄어쓰기)만 잡는다. 원본에는 "낫아웃 폭투"·"낫아웃 포일"
# 처럼 붙여 쓴 문구와 2스트라이크 번트 파울 삼진("쓰리번트 아웃")도 있다(2025 44타석).
STRIKEOUT_PATTERN = f"{STRIKEOUT_TEXT}|낫아웃|쓰리번트"
OUT_PATTERN = r"(플라이|땅볼|라인드라이브|병살타|삼중살|번트).*아웃"
# 타자 출루지만 안타가 아닌 경우(실책·야수선택). 타수에는 들어간다.
REACH_PATTERN = r"실책으로 출루|야수선택으로 출루|땅볼로 출루|병살타로 출루"
# 타구가 실제로 나간 타석이어야 성립하는 분류. 인플레이 공이 없는데 이 문구면
# 다른 타석의 문구가 붙은 것이라 믿지 않는다.
NEEDS_IN_PLAY = {"1B", "2B", "3B", "HR", "SF", "SH", "OUT", "REACH"}
# 타석 중 대타가 들어오면 앞 타자 구간의 문구가 이 줄이 된다(크롤러 fallback).
# 2025 원본의 형태는 "대타 {이름} (으)로 교체" 하나뿐이다. 공백 유무와 "(으)로" 생략만
# 허용한다 — 괄호 없는 "로/으로"는 이름 끝 글자와 구분이 안 돼 받지 않는다(예: "김도로").
# 이름은 공백·괄호가 없는 가장 짧은 덩어리라 "(으)로"·"교체"가 이름에 붙지 않는다.
# 이 문구 하나만으로 합치지는 않는다(_substitution_boundary).
SUBSTITUTION_NOTE = re.compile(r"대타\s*(?P<name>[^\s()]+?)\s*(?:\(으\)로)?\s*교체")


def substitute_name(text) -> str | None:
    """교체 줄에서 대타 이름을 뽑는다. 형태가 다르면 None(문구 신호 없음)."""
    if not isinstance(text, str):
        return None
    match = SUBSTITUTION_NOTE.fullmatch(" ".join(text.split()))
    return match.group("name") if match else None
# 9.16(h): 투수 교체 시 이 카운트(볼-스트라이크)에서 볼넷이면 앞 투수 몫.
WALK_TO_PRECEDING = {(2, 0), (2, 1), (3, 0), (3, 1), (3, 2)}
HITS = ["1B", "2B", "3B", "HR"]

UNCERTAIN_COUNTS = ["ResultUnknown", "PAUncertain", "AttributionUncertain"]
BATTER_COUNTS = ["PA", "AB", "H", "2B", "3B", "HR", "BB", "HBP", "SF", "SH", "SO", *UNCERTAIN_COUNTS]
PITCHER_COUNTS = ["BF", "H", "BB", "HBP", "SO", *UNCERTAIN_COUNTS]
COLUMNS = [
    "Season", "Date", "GameId", "DH", "Role", "PlayerId", "Player", "Team", "Opponent", "HomeAway",
    "PA", "AB", "H", "2B", "3B", "HR", "BB", "HBP", "SF", "SH", "SO", "BF", *UNCERTAIN_COUNTS,
    "PAComplete", "StatsComplete", "Outs", "OutsComplete",
]


def classify(text: str) -> str:
    """타석 결과 문구 → 분류 코드. 규칙에 없는 문구는 UNKNOWN(짐작하지 않는다)."""
    if not text:
        return "UNKNOWN"
    if "타격방해" in text:
        return "INT"
    if re.search(WALK_TEXT, text):
        return "BB"
    if HBP_TEXT in text:
        return "HBP"
    if re.search(STRIKEOUT_PATTERN, text):
        return "SO"
    if is_hit_description(text):
        if "홈런" in text:
            return "HR"
        if "3루타" in text:
            return "3B"
        if "2루타" in text:
            return "2B"
        return "1B"
    if "희생플라이" in text:
        return "SF"
    if "희생번트" in text:
        return "SH"
    if re.search(OUT_PATTERN, text):
        return "OUT"
    if re.search(REACH_PATTERN, text):
        return "REACH"
    return "UNKNOWN"


def load_season_pitches(season: int) -> pd.DataFrame:
    """시즌 투구 원본을 읽되, 경기마다 파일 하나만 쓴다(행이 가장 많은 파일, 같으면 뒤 파일).

    날짜 구간 파일이 같은 경기를 통째로 다시 담고 있어 경기 단위로 고르면 중복이
    사라지고, 파일 안의 행 순서(타석 묶음의 근거)도 섞이지 않는다.
    """
    files = [p for p in sorted(glob.glob(str(RAW_DIR / "naver_kbo_pitches_*.csv"))) if _file_covers_season(p, season)]
    if not files:
        return pd.DataFrame()
    frames = [pd.read_csv(path).assign(_File=Path(path).name) for path in files]
    return pick_one_file_per_game(pd.concat(frames, ignore_index=True), season)


def pick_one_file_per_game(raw: pd.DataFrame, season: int) -> pd.DataFrame:
    # 같은 파일 안에서 모든 컬럼이 같은 행은 진짜 중복이다(2025 8행). 파일 크기를 재기 전에
    # 없애야 중복으로 부풀려진 불완전 파일이 뽑히지 않는다.
    raw = raw[raw["Season"] == season].drop_duplicates().copy()
    raw["_Pos"] = range(len(raw))
    sizes = raw.groupby(["GameId", "_File"]).size().rename("_N").reset_index()
    chosen = sizes.sort_values(["_N", "_File"]).drop_duplicates("GameId", keep="last")
    df = raw.merge(chosen[["GameId", "_File"]], on=["GameId", "_File"]).sort_values("_Pos", kind="mergesort")
    return df.drop(columns=["_File", "_Pos"]).reset_index(drop=True)


def regular_season(pitches: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    """정규시즌 완료 경기만 남긴다. 투구 GameId 는 일정 GameId(13자) 뒤에 시즌이 붙어 있다.

    13번째 자리가 더블헤더 번호(0=단일, 1·2=1·2차전)라 같은 날 같은 팀 경기도 갈린다.
    일정에 없는 경기(포스트시즌·올스타)와 미완료 경기는 여기서 빠진다.
    """
    final = schedule[schedule["status"] == "final"].dropna(subset=["GameId"])
    final = final.assign(GameId=final["GameId"].astype(str)).set_index("GameId")
    df = pitches.assign(_Game=pitches["GameId"].astype(str).str[:13])
    df = df[df["_Game"].isin(final.index)].copy()
    df["Date"] = df["_Game"].map(final["Date"])
    df["DH"] = df["_Game"].str[12].astype(int)
    return df.drop(columns=["GameId"]).rename(columns={"_Game": "GameId"})


def order_plate_appearances(pitches: pd.DataFrame) -> pd.DataFrame:
    """파일 순서대로 타석(PaId)을 묶고, 타석을 시간순으로 정렬한다.

    새 블록: 1구이거나 투구 번호가 이어지지 않거나 경기·이닝·공수·타자가 바뀔 때.
    단 같은 타자의 번호 건너뜀(타석이 안 끝난 채 공 하나 누락)은 같은 블록으로 둔다.
    타석 중 대타는 원본에서 두 블록으로 온다 — 앞 타자 구간에는 "대타 X (으)로 교체"
    줄이, 대타 구간에는 결과 줄이 붙고, 파일에서는 두 구간이 붙어 있지도 않다.
    그래서 시간순 정렬 뒤 이웃한 두 블록의 경계를 _substitution_boundary 로 판정해
    같은 타석이면 합친다. 확실하지 않은 경계도 합치되 _SubUncertain 으로 표시해
    귀속·PA 를 확정하지 않게 한다(plate_appearances, player_stats).

    _CountOk: 타석 첫 공부터 그 공까지 볼카운트가 투구 결과대로 움직였는가(_count_ok).
    교체 시점 카운트·볼 4개/스트라이크 3개 완료 판정은 이 값이 참일 때만 쓴다.
    """
    df = pitches.reset_index(drop=True)
    half = ["GameId", "Inning", "HomeAway"]

    def changed(frame: pd.DataFrame, cols: list[str]) -> pd.Series:
        return frame[cols].ne(frame[cols].shift()).any(axis=1)

    prev = df.shift()
    # 같은 타자인데 번호만 건너뛰었고(앞 공이 타석을 끝내지 않음) → 원본에서 공 하나가 빠진 같은
    # 타석이다(2025 50건, 모두 1구 누락). 나누면 볼넷·삼진이 두 번 세어진다. 빠진 공 때문에 카운트
    # 검증(_count_ok)은 그 지점부터 실패하므로 카운트에 기대는 판정은 하지 않는다.
    same_batter = ~changed(df, [*half, "BatterId"])
    skipped = same_batter & df["PitchNo"].gt(prev["PitchNo"] + 1) & ~_ends_pa(prev)
    new = df["PitchNo"].eq(1) | (df["PitchNo"].ne(prev["PitchNo"] + 1) & ~skipped) | ~same_batter
    df["PaId"] = new.cumsum()
    pitch_id = df["PitchId"].astype(str)
    df["_PaKey"] = pitch_id.where(pitch_id != "-1").groupby(df["PaId"]).transform("min")
    df["_Pos"] = range(len(df))
    df = df.sort_values(["GameId", "_PaKey", "_Pos"], kind="mergesort", na_position="last").reset_index(drop=True)
    df = _place_unkeyed_blocks(df, half)

    sure, unsure = _substitution_boundary(df, ~changed(df, half))
    first = df["PaId"].ne(df["PaId"].shift())
    df["PaId"] = (first & ~(sure | unsure)).cumsum()
    df["_SubUncertain"] = unsure.groupby(df["PaId"]).transform("any")

    df["_CountOk"] = _count_ok(df)
    return df


def _substitution_boundary(df: pd.DataFrame, same_half: pd.Series) -> tuple[pd.Series, pd.Series]:
    """블록 첫 공마다 '앞 블록과 같은 타석인가'를 (확실, 불확실) 두 마스크로 낸다.

    구조 신호(전부 참이어야 함): 같은 반이닝 · 타자가 바뀜 · 투구 번호가 +1 ·
    앞 블록 마지막 공이 타석을 끝내지 않음(인플레이·볼 4개·스트라이크 3개 아님) ·
    앞 블록 카운트에서 이 공의 결과만큼 움직인 카운트.
    문구 신호: 앞 블록 문구에서 뽑은 대타 이름(substitute_name)이 새 타자 이름과 전체 일치.
    시간 근거: 두 블록 모두 유효한 PitchId 가 있어 정렬 위치를 믿을 수 있음(_KeyMissing 아님).

    구조+문구+시간 → 확실(합친다). 구조+문구인데 시간 근거가 없음, 또는 시간 근거는
    있는데 구조·문구 중 하나만 → 불확실(합치고 표시). 그 밖 → 다른 타석.
    2025 원본: 구조+문구 13건, 구조·문구 모두 없음(앞 타석 인플레이 + 다음 타석 1구
    누락으로 번호만 이어진 경우) 19건, 한쪽만 있는 경계 0건.
    """
    prev = df.shift()
    first = df["PaId"].ne(prev["PaId"])
    boundary = first & same_half & df["BatterId"].ne(prev["BatterId"])
    structural = boundary & _continues(prev, df)
    announced = boundary & _names_substitute(prev["AtBatText"], df["BatterName"])
    keyed = ~prev["_KeyMissing"].fillna(True).astype(bool) & ~df["_KeyMissing"].astype(bool)
    both = structural & announced
    return both & keyed, (both & ~keyed) | ((structural ^ announced) & keyed)


def _continues(before: pd.DataFrame, after: pd.DataFrame) -> pd.Series:
    """after 의 공이 before 의 공 바로 다음 공일 수 있는가(번호 +1, 타석 미종료, 카운트 연속)."""
    return (after["PitchNo"].eq(before["PitchNo"] + 1) & ~_ends_pa(before)
            & _count_step_ok(after, before["Ball"], before["Strike"]))


def _ends_pa(pitch: pd.DataFrame) -> pd.Series:
    """그 공으로 타석이 끝났는가(인플레이·볼 4개·스트라이크 3개)."""
    return pitch["IsInPlay"].fillna(False).astype(bool) | pitch["Ball"].ge(4) | pitch["Strike"].ge(3)


def _names_substitute(note: pd.Series, batter_name: pd.Series) -> pd.Series:
    """교체 줄이 지목한 이름 == 다음 타자 이름(공백 정규화 후 전체 일치). 부분 일치는 안 된다."""
    named = note.map(substitute_name)
    actual = batter_name.map(lambda n: " ".join(n.split()) if isinstance(n, str) else None)
    return named.notna() & named.eq(actual)


def _place_unkeyed_blocks(df: pd.DataFrame, half: list[str]) -> pd.DataFrame:
    """PitchId 가 모두 "-1" 이라 _PaKey 가 없는 블록은 시간 위치를 몰라 경기 끝으로 밀린다.

    그 블록과 같은 반이닝에 대타 교체로 이어질 짝(구조+문구 신호 모두)이 정확히 하나
    있으면 짝 옆으로 옮긴다. 그래도 시간 근거가 없으므로 _substitution_boundary 가
    불확실 병합으로 표시한다. 짝이 없거나 여럿이면 옮기지 않는다(병합 안 함).
    _PaKey 자체는 바꾸지 않는다 — 투수 아웃 수의 반이닝 신뢰 판정이 그 값을 본다.
    """
    df["_KeyMissing"] = df["_PaKey"].isna()
    df["_SortKey"], df["_Order"] = df["_PaKey"], 0
    missing = df.loc[df["_KeyMissing"], "PaId"].unique()
    if not len(missing):
        return df
    firsts = df.groupby("PaId", sort=False).head(1).set_index("PaId")
    lasts = df.groupby("PaId", sort=False).tail(1).set_index("PaId")

    def joins(pre: int, post: int) -> bool:
        a, b = lasts.loc[[pre]].reset_index(drop=True), firsts.loc[[post]].reset_index(drop=True)
        return bool((_continues(a, b) & a["BatterId"].ne(b["BatterId"])
                     & _names_substitute(a["AtBatText"], b["BatterName"])).iloc[0])

    for block in missing:
        peers = firsts.index[(firsts[half] == firsts.loc[block, half]).all(axis=1) & (firsts.index != block)]
        pairs = [(p, block) for p in peers if joins(p, block)] + [(block, p) for p in peers if joins(block, p)]
        if len(pairs) != 1:
            continue
        pre, post = pairs[0]
        partner = post if pre == block else pre
        if firsts.at[partner, "_KeyMissing"]:
            continue  # 양쪽 다 시간 근거가 없으면 순서를 정할 수 없다
        df.loc[df["PaId"] == block, "_SortKey"] = firsts.at[partner, "_PaKey"]
        df.loc[df["PaId"] == post, "_Order"] = 1
    return df.sort_values(["GameId", "_SortKey", "_Order", "_Pos"], kind="mergesort",
                          na_position="last").reset_index(drop=True)


def _count_ok(df: pd.DataFrame) -> pd.Series:
    """공마다 '타석 첫 공부터 여기까지 카운트가 규칙대로 움직였나'.

    Ball/Strike 는 그 공을 던진 *뒤* 카운트다. 2025 원본에서 결과 코드별로 잰 증가량:
      B 볼                         볼 +1 (사구도 B 로 온다)
      T 스트라이크 · S 헛스윙       스트라이크 +1
      W 번트파울 · V 번트헛스윙     스트라이크 +1 (2스트라이크 번트파울은 삼진)
      F 파울                        2스트라이크 미만이면 스트라이크 +1, 2스트라이크면 그대로
      H 타격(인플레이)              그대로
    증가량이 이와 다르거나(볼인데 스트라이크도 늘었다 등), 코드가 목록에 없거나,
    IsBall/IsInPlay 플래그가 코드와 어긋나거나, 이미 볼 4개·스트라이크 3개인데 공이
    이어지면 그 공은 틀렸다. 한 번 틀리면 그 타석의 이후 공도 모두 틀린 것으로 둔다 —
    뒤에서 숫자가 맞아 보여도 기준점이 오염돼 있다.
    """
    first = df["PaId"].ne(df["PaId"].shift())
    pre_ball = df["Ball"].shift().where(~first, 0)
    pre_strike = df["Strike"].shift().where(~first, 0)
    step_ok = _count_step_ok(df, pre_ball, pre_strike)
    return step_ok.astype(int).groupby(df["PaId"]).cummin().astype(bool)


def _count_step_ok(df: pd.DataFrame, pre_ball: pd.Series, pre_strike: pd.Series) -> pd.Series:
    """(pre_ball, pre_strike) 에서 이 공의 결과대로 움직이면 지금 카운트가 되는가(_count_ok 규칙)."""
    result = df["PitchResult"]
    is_ball = result.eq("B")
    adds_strike = result.isin(["T", "S", "W", "V"]) | (result.eq("F") & pre_strike.lt(2))
    return (
        result.isin(["B", "T", "S", "W", "V", "F", "H"])
        & df["IsBall"].fillna(False).astype(bool).eq(is_ball)
        & df["IsInPlay"].fillna(False).astype(bool).eq(result.eq("H"))
        & pre_ball.lt(4) & pre_strike.lt(3)
        & (df["Ball"] - pre_ball).eq(is_ball.astype(int))
        & (df["Strike"] - pre_strike).eq(adds_strike.astype(int))
    )


def plate_appearances(pitches: pd.DataFrame) -> pd.DataFrame:
    """타석 1개 = 1행. 결과 분류·완료 여부·타자/투수 귀속을 붙인다.

    Batters/Pitchers 는 그 타석에 나온 선수를 등장 순서대로 담고, Charged* 는
    기록이 귀속되는 선수(확정 못 하면 NA)다.
    """
    g = pitches.groupby("PaId", sort=False)
    pa = g.tail(1).set_index("PaId")[[
        "GameId", "Inning", "HomeAway", "AtBatText", "Ball", "Strike", "_CountOk",
    ]].copy()
    in_play = pitches["IsInPlay"].fillna(False).astype(bool)
    last = pitches["PaId"].ne(pitches["PaId"].shift(-1))
    pa["LastInPlay"] = in_play[last].groupby(pitches["PaId"]).any()
    # 인플레이 뒤에 공이 더 있으면 블록이 두 타석을 섞었거나 원본이 틀렸다.
    pa["EarlyInPlay"] = (in_play & ~last).groupby(pitches["PaId"]).any()
    pa["Category"] = pa["AtBatText"].fillna("").astype(str).map(classify)
    untrusted = pa["Category"].isin(NEEDS_IN_PLAY) & ~pa["LastInPlay"]
    pa.loc[untrusted, "Category"] = "UNKNOWN"
    pa["Batters"] = g["BatterId"].unique()
    pa["Pitchers"] = g["PitcherId"].unique()
    pa["SubUncertain"] = g["_SubUncertain"].any()
    pa["Completed"] = _completion(pa)

    pa["ChargedBatter"] = pa["Batters"].str[0].astype("Int64")
    pa["ChargedPitcher"] = pa["Pitchers"].str[0].astype("Int64")
    # 같은 타석인지 불확실한 병합이면 교체 시점 카운트를 쓰지 않는다 — 카운트가 갈리는
    # 결과(삼진·볼넷·결과불명)는 미확정이 되고, 어느 해석이든 같은 결과만 귀속된다.
    for pa_id in pa.index[pa["Batters"].str.len() > 1]:
        count = None if pa.at[pa_id, "SubUncertain"] else _count_at_change(pitches[pitches["PaId"] == pa_id], "BatterId")
        pa.loc[pa_id, "ChargedBatter"] = _charge_batter(pa.at[pa_id, "Category"], pa.at[pa_id, "Batters"], count)
    for pa_id in pa.index[pa["Pitchers"].str.len() > 1]:
        count = None if pa.at[pa_id, "SubUncertain"] else _count_at_change(pitches[pitches["PaId"] == pa_id], "PitcherId")
        pa.loc[pa_id, "ChargedPitcher"] = _charge_pitcher(pa.at[pa_id, "Category"], pa.at[pa_id, "Pitchers"], count)
    return pa.reset_index()


def _completion(pa: pd.DataFrame) -> pd.Series:
    """yes / no / unknown / conflict.

    완료 신호: 결과 문구 인식, 마지막 공 인플레이, 검증된 카운트의 볼 4개·스트라이크 3개.
    미완료 신호: 다음 이닝 첫 타자로 재등장(resumed).
    두 신호가 함께 있거나 인플레이 뒤에 공이 이어지면 conflict — 어느 쪽으로도
    확정하지 않고 PAUncertain 으로 센다(우선순위로 한쪽을 이기게 하지 않는다).
    """
    known = pa["Category"].ne("UNKNOWN")
    ended = pa["LastInPlay"] | (pa["_CountOk"] & (pa["Ball"].ge(4) | pa["Strike"].ge(3)))
    # 반이닝 마지막 블록의 타자가 같은 팀 다음 이닝 첫 타자로 다시 나오면, 그 타석은
    # 주자 아웃으로 이닝이 끝나 완료되지 않은 것이다(결과 인식 타석 중 이 패턴 0건).
    half = ["GameId", "Inning", "HomeAway"]
    last_in_half = ~pa.duplicated(half, keep="last")
    leadoff = pa[~pa.duplicated(half, keep="first")].set_index(half)["Batters"].str[0]
    next_leadoff = pd.Series(
        [leadoff.get((game, inning + 1, side)) for game, inning, side in pa[half].itertuples(index=False)],
        index=pa.index,
    )
    resumed = last_in_half & pa["Batters"].str[-1].eq(next_leadoff)
    done = known | ended
    status = pd.Series("unknown", index=pa.index)
    status[resumed & ~done] = "no"
    status[done & ~resumed] = "yes"
    status[(done & resumed) | pa["EarlyInPlay"]] = "conflict"
    return status


def _count_at_change(rows: pd.DataFrame, col: str) -> tuple[int, int] | None:
    """col(타자/투수)이 처음 바뀌기 직전 공을 던진 뒤의 볼카운트. 복원 불가면 None."""
    changed = rows[col].ne(rows[col].iloc[0]).to_numpy().argmax()
    before = rows.iloc[changed - 1]
    if not bool(before["_CountOk"]) or pd.isna(before["Ball"]) or pd.isna(before["Strike"]):
        return None
    return int(before["Ball"]), int(before["Strike"])


def _charge_pitcher(category: str, pitchers, count):
    """9.16(h). 볼넷만 카운트에 따라 앞 투수 몫이 될 수 있고, 나머지는 구원 투수."""
    if len(pitchers) != 2:
        return pd.NA
    preceding, relief = pitchers
    if category in ("BB", "UNKNOWN"):
        if count is None:
            return pd.NA
        if count in WALK_TO_PRECEDING:
            return preceding if category == "BB" else pd.NA
    return relief


def _charge_batter(category: str, batters, count):
    """9.15(b). 2스트라이크에서 물러난 타자의 삼진만 앞 타자 몫, 나머지는 대타."""
    if len(batters) != 2:
        return pd.NA
    first, substitute = batters
    if category in ("SO", "UNKNOWN"):
        if count is None:
            return pd.NA
        if count[1] == 2:
            return first if category == "SO" else pd.NA
    return substitute


def pitch_outs(pitches: pd.DataFrame) -> pd.DataFrame:
    """공마다 그 공 이후 늘어난 아웃 수(_Outs)와 그 공이 속한 반이닝의 신뢰 여부(_HalfOk)."""
    df = pitches.copy()
    half = ["GameId", "Inning", "HomeAway"]
    nxt = df.groupby(half, sort=False)["Out"].shift(-1)
    last = nxt.isna()
    df["_Outs"] = (nxt - df["Out"]).where(~last, 3 - df["Out"])

    # 반이닝 마지막 공에 남은 아웃(3 - Out)을 주는 근거:
    #  - 뒤에 반이닝이 더 있으면 이 반이닝은 끝났다. 단 타자가 살아 나간 결과(안타·볼넷 등)
    #    하나로 아웃이 2개 이상 나왔다면 믿지 않는다 — 원본이 끊긴 것으로 본다(2025 1반이닝).
    #  - 경기의 마지막 반이닝은 끝내기·콜드(2025 20250719HHKT0 6회초 1아웃 종료)로 3아웃 전에
    #    끝날 수 있어, 마지막 공 문구가 남은 아웃만큼의 아웃을 보여 줄 때만 준다. 그래서
    #    끝내기·단축 경기 정상 종료·9회 정상 종료를 승패가 아니라 문구로 가른다.
    # ponytail: 경기 중간 반이닝 끝의 타석이 원본에서 통째로 빠지면 구분 못 한다 — 공식 이닝 대조 테스트가 잡는다.
    order = df["Inning"] * 2 + df["HomeAway"].astype(int)
    final_half = order.eq(order.groupby(df["GameId"]).transform("max"))
    remaining = 3 - df["Out"]
    safe = df["AtBatText"].fillna("").astype(str).map(classify).isin([*HITS, "BB", "HBP", "INT"])
    final_unproven = last & final_half & _evident_outs(df).lt(remaining)
    safe_short = last & ~final_half & safe & remaining.ge(2)
    # 투수 교체 순간의 아웃: 앞 투수 마지막 공 → 다음 투수 첫 공 사이에 Out 이 늘면, 그 공의 플레이에서
    # 아웃이 났다는 근거(타석을 끝낸 공 + 아웃 문구)가 있을 때만 앞 투수 몫이다. 근거가 없으면(안타·사사구·
    # 주자 문구·타석 도중 교체) 앞 투수 공의 도루자인지 새 투수의 견제사인지 투구 데이터로 가를 수 없어
    # 반이닝을 믿지 않는다(2025 17반이닝. 이 중 네이버와 어긋났던 3곳은 모두 새 투수 몫이었다).
    nxt_pitcher = df.groupby(half, sort=False)["PitcherId"].shift(-1)
    ends_pa = df.groupby(half, sort=False)["PaId"].shift(-1).ne(df["PaId"])
    change_unclear = (nxt_pitcher.notna() & nxt_pitcher.ne(df["PitcherId"]) & df["_Outs"].gt(0)
                      & ~(ends_pa & _play_shows_outs(df, df["_Outs"])))
    # _OutsRaw: 근거 없이 채운 값까지 그대로 둔 아웃 수. 외부 기록 대조(verify_player_games)
    # 전용이며 확정값이 아니다 — 출력 CSV 에는 내보내지 않는다.
    df["_OutsRaw"] = df["_Outs"]
    df.loc[final_unproven | safe_short, "_Outs"] = float("nan")

    h = df.groupby(half, sort=False)
    # 반이닝을 믿지 못하는 사유. 여러 개면 앞의 것 하나(_HalfReason). 전부 통과해야 _HalfOk.
    checks = {
        "final_half_unproven": ~h["_Outs"].transform(lambda s: final_unproven[s.index].any()),
        "safe_result_short": ~h["_Outs"].transform(lambda s: safe_short[s.index].any()),
        "pitcher_change_out": ~h["_Outs"].transform(lambda s: change_unclear[s.index].any()),
        "start_not_zero": h["Out"].transform("first").eq(0),
        "negative_step": h["_Outs"].transform("min").ge(0),
        "missing_out": h["_Outs"].transform(lambda s: s.notna().all()),
        "sum_not_3": h["_Outs"].transform("sum").eq(3),
        "unordered_pa": h["_PaKey"].transform(lambda s: s.notna().all()),
    }
    reason = pd.Series("", index=df.index)
    for name, passed in reversed(checks.items()):
        reason = reason.where(passed, name)
    df["_HalfReason"] = reason
    df["_HalfOk"] = reason.eq("")
    return df


def _evident_outs(df: pd.DataFrame) -> pd.Series:
    """공마다 그 타석 문구가 입증하는 최소 아웃 수.

    2025 원본에서 반이닝 중간 타석의 실제 Out 증가로 확인한 근거:
      진짜 삼진(낫아웃 제외) · 인플레이 타자 아웃(OUT·SF·SH)  1 이상 (21,998/22,045)
      병살타 아웃 2 (389/392) · 삼중살 3
      포스아웃·태그아웃·도루실패아웃·견제사아웃 줄              1 이상 (34/34)
    "땅볼로 출루"는 11% 가 아웃 없이 끝나 근거가 아니다. 안타·볼넷·결과불명은 0.
    """
    text = df["AtBatText"].fillna("").astype(str)
    category = text.map(classify)
    in_play = df["IsInPlay"].fillna(False).astype(bool)
    batter_out = ((category.eq("SO") & df["Strike"].ge(3) & ~text.str.contains("낫 ?아웃"))
                  | (category.isin(["OUT", "SF", "SH"]) & in_play))
    evident = (batter_out | text.str.match("포스아웃|태그아웃|도루실패아웃|견제사아웃")).astype(int)
    evident[batter_out & text.str.contains("병살타")] = 2
    evident[batter_out & text.str.contains("삼중살")] = 3
    return evident


def _play_shows_outs(df: pd.DataFrame, outs: pd.Series) -> pd.Series:
    """그 공의 플레이에서 outs 만큼 아웃이 났다는 문구 근거가 있나(투수 교체 순간 귀속용).
    _evident_outs 에 더해, 아웃이 실제로 늘어난 공에 한해 '땅볼로 출루'(포스아웃 야수선택)와
    '낫 아웃 (…아웃)'(낫아웃 뒤 타자 아웃)을 아웃 1개 근거로 본다."""
    text = df["AtBatText"].fillna("").astype(str)
    in_play = df["IsInPlay"].fillna(False).astype(bool)
    one = outs.eq(1) & ((in_play & text.str.contains("땅볼로 출루"))
                        | (df["Strike"].ge(3) & text.str.contains(r"낫 ?아웃 \(.*아웃\)")))
    return _evident_outs(df).ge(outs) | one


def _side(home_away: pd.Series, batting: bool) -> pd.Series:
    """HomeAway==1 은 홈팀 공격. 타자는 그대로, 투수는 반대편이다."""
    home = home_away.astype(int).eq(1) if batting else home_away.astype(int).eq(0)
    return home.map({True: "home", False: "away"})


def _counts(category: pd.Series, role: str) -> pd.DataFrame:
    """귀속이 확정된 완료 타석 1개가 그 선수에게 더하는 값."""
    c = category
    common = {"H": c.isin(HITS), "BB": c.eq("BB"), "HBP": c.eq("HBP"), "SO": c.eq("SO"),
              "ResultUnknown": c.eq("UNKNOWN")}
    if role == "pitcher":
        cols = {"BF": True, **common}
    else:
        cols = {"PA": True, "AB": c.isin([*HITS, "SO", "OUT", "REACH"]), **common,
                "2B": c.eq("2B"), "3B": c.eq("3B"), "HR": c.eq("HR"), "SF": c.eq("SF"), "SH": c.eq("SH")}
    return pd.DataFrame(cols, index=c.index).astype(int)


def player_stats(pa: pd.DataFrame, role: str) -> pd.DataFrame:
    """(GameId, PlayerId) 별 기록 합. 확정 못 한 타석은 0 이 아니라 불확실 카운터로 남긴다."""
    involved, charged = ("Batters", "ChargedBatter") if role == "batter" else ("Pitchers", "ChargedPitcher")
    done = pa[pa["Completed"] == "yes"]
    sure = done[done[charged].notna()]
    attributed = _counts(sure["Category"], role).assign(GameId=sure["GameId"], PlayerId=sure[charged])

    def flag(rows: pd.DataFrame, column: str) -> pd.DataFrame:
        exploded = rows[["GameId", involved]].explode(involved).rename(columns={involved: "PlayerId"})
        return exploded.assign(**{column: 1})

    # 같은 타석인지 불확실하게 합친 블록은, 따로였다면 앞 타자 구간이 별개 타석(예: 사구)
    # 이었을 수도 있어 관련 선수 모두의 PA/BF 를 확정하지 않는다.
    parts = [attributed, flag(done[done[charged].isna()], "AttributionUncertain"),
             flag(pa[pa["Completed"].isin(["unknown", "conflict"]) | pa["SubUncertain"]], "PAUncertain")]
    stats = pd.concat(parts, ignore_index=True).fillna(0)
    stats["PlayerId"] = stats["PlayerId"].astype(int)
    return stats.groupby(["GameId", "PlayerId"]).sum()


def batter_games(pa: pd.DataFrame, pitches: pd.DataFrame) -> pd.DataFrame:
    # 행은 투구 원본에 나온 모든 타자-경기로 만든다(대타에게 넘긴 앞 타자도 PA 0 으로 남는다).
    keys = ["GameId", "BatterId"]
    out = pitches.groupby(keys).agg(
        Season=("Season", "first"), Date=("Date", "first"), DH=("DH", "first"),
        Player=("BatterName", "first"), Team=("BatterTeam", "first"), Opponent=("PitcherTeam", "first"),
        _HA=("HomeAway", "first"),
    ).rename_axis(["GameId", "PlayerId"])
    out = out.join(player_stats(pa, "batter"), how="left").fillna({c: 0 for c in BATTER_COUNTS}).reset_index()
    out["HomeAway"] = _side(out.pop("_HA"), batting=True)
    return out.assign(Role="batter")


def pitcher_games(pa: pd.DataFrame, pitches: pd.DataFrame) -> pd.DataFrame:
    keys = ["GameId", "PitcherId"]
    out = pitches.groupby(keys).agg(
        Season=("Season", "first"), Date=("Date", "first"), DH=("DH", "first"),
        Player=("PitcherName", "first"), Team=("PitcherTeam", "first"), Opponent=("BatterTeam", "first"),
        _HA=("HomeAway", "first"), Outs=("_Outs", "sum"), OutsComplete=("_HalfOk", "all"),
    ).rename_axis(["GameId", "PlayerId"])
    out = out.join(player_stats(pa, "pitcher"), how="left").fillna({c: 0 for c in PITCHER_COUNTS}).reset_index()
    out["Outs"] = out["Outs"].where(out["OutsComplete"])
    out["HomeAway"] = _side(out.pop("_HA"), batting=False)
    return out.assign(Role="pitcher")


def build_frame(pitches: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    """투구 원본(파일 하나/경기로 고른 것) + 일정 → 선수-경기 표. 저장은 하지 않는다."""
    df = order_plate_appearances(regular_season(ensure_teams(pitches), schedule))
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    df = pitch_outs(df)
    pa = plate_appearances(df)
    out = pd.concat([batter_games(pa, df), pitcher_games(pa, df)], ignore_index=True)
    out["PlayerId"] = out["PlayerId"].astype(int)
    out["PAComplete"] = out["PAUncertain"].eq(0) & out["AttributionUncertain"].eq(0)
    out["StatsComplete"] = out["PAComplete"] & out["ResultUnknown"].eq(0)
    out = out.reindex(columns=COLUMNS).sort_values(["Date", "GameId", "Role", "PlayerId"]).reset_index(drop=True)
    # 역할에 없는 칸은 비워 두되 정수로 저장한다("4.0" 대신 "4").
    counts = list(dict.fromkeys(BATTER_COUNTS + PITCHER_COUNTS + ["Outs"]))
    out[counts] = out[counts].astype("Int64")
    dup = out.duplicated(["Role", "PlayerId", "GameId"])
    if dup.any():
        raise ValueError(f"선수-경기 중복 {int(dup.sum())}행: {out[dup].head(3).to_dict('records')}")
    return out


def load_schedule(season: int) -> pd.DataFrame:
    return pd.read_csv(SCHEDULE_DIR / f"kbo_schedule_{season}.csv", encoding="utf-8-sig")


def calc_rule() -> str:
    """계산 규칙 판본 = 이 파일 내용 해시. 규칙이 바뀌면 자동으로 달라진다(대조·DB 적재의 키)."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12]


def build(season: int) -> pd.DataFrame:
    pitches = load_season_pitches(season)
    if pitches.empty:
        raise SystemExit(f"[player-games] {season} 투구 원본이 없습니다")
    out = build_frame(pitches, load_schedule(season)).assign(CalcRule=calc_rule())
    games = out["GameId"].nunique()
    bat, pit = out[out["Role"] == "batter"], out[out["Role"] == "pitcher"]
    csv_guard.save_csv(out, PROCESSED_DIR / f"kbo_player_games_{season}.csv", prefix="[player-games]", extra=(
        f"games={games} result_unknown_pa={bat['ResultUnknown'].sum()} pa_uncertain={bat['PAUncertain'].sum()} "
        f"pitcher_attribution_uncertain={pit['AttributionUncertain'].sum()} "
        f"pitcher_games_outs_unknown={(~pit['OutsComplete'].astype(bool)).sum()}"))
    return out


def _official_outs(ip) -> int:
    """'180 2/3' → 542. 공식 이닝 표기는 아웃 수로만 비교한다."""
    whole, frac = 0, 0
    for part in str(ip).split():
        if "/" in part:
            frac = int(part.split("/")[0])
        else:
            whole = int(part)
    return whole * 3 + frac


def compare_official(games: pd.DataFrame, season: int) -> dict[str, pd.DataFrame]:
    """선수-경기 표의 시즌 합을 네이버 시즌 누적 CSV 와 PlayerId 로 맞춰 본다."""
    report = {}
    for role, file, cols in (
        ("batter", "kbo_naver_hitters_{}.csv", ["AB", "H", "2B", "3B", "HR", "BB", "HBP", "SO"]),
        ("pitcher", "kbo_naver_pitchers_{}.csv", ["H", "BB", "HBP", "SO", "Outs"]),
    ):
        official = pd.read_csv(PROCESSED_DIR / file.format(season), encoding="utf-8-sig").set_index("PlayerId")
        mine = games[games["Role"] == role]
        if role == "pitcher":
            official["Outs"] = official["IP"].map(_official_outs)
            complete = mine.groupby("PlayerId")["OutsComplete"].all()
        summed = mine.groupby("PlayerId")[cols].sum(min_count=1)
        joined = official[cols].join(summed, rsuffix="_built", how="inner")
        rows = []
        for col in cols:
            sub = joined
            if col == "Outs":  # 아웃 수는 모든 경기가 확인된 투수끼리만 비교한다.
                sub = joined[joined.index.isin(complete[complete].index)]
            diff = sub[f"{col}_built"] - sub[col]
            rows.append({
                "stat": col, "players": len(sub), "official": int(sub[col].sum()),
                "built": int(sub[f"{col}_built"].sum()),
                "diff_pct": round((sub[f"{col}_built"].sum() / sub[col].sum() - 1) * 100, 2),
                "exact_pct": round(diff.eq(0).mean() * 100, 1),
                "abs_diff_gt2": int(diff.abs().gt(2).sum()),
            })
        report[role] = pd.DataFrame(rows)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=current_kbo_year())
    parser.add_argument("--compare", action="store_true", help="저장된 결과를 공식 시즌 누적과 대조")
    args = parser.parse_args()
    if args.compare:
        games = pd.read_csv(PROCESSED_DIR / f"kbo_player_games_{args.year}.csv", encoding="utf-8-sig")
        for role, table in compare_official(games, args.year).items():
            print(f"[{role}]\n{table.to_string(index=False)}")
        return
    build(args.year)


if __name__ == "__main__":
    main()
