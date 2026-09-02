"""
Build season-cumulative ball/strike-count datasets ("볼카운트 야구").

같은 네이버 투구 원본에서 "카운트가 타석을 어떻게 바꾸는가"를 뽑는다:

    data/processed/kbo_count_baseball_{season}.csv

한 행 = (Scope, 선수, 버킷). Scope 는 둘이다.
  리그  — 12칸 카운트 매트릭스(0-0~3-2) + 이름 붙인 버킷(전체/초구/2S/투수유리/타자유리)
  선수  — 타자별 이름 붙인 버킷만. 12칸 × 선수는 셀당 표본이 무너져서 내지 않는다.

**볼카운트 복원 로직은 여기 없다.** build_pitch_arsenal.annotate() 를 그대로 쓴다
(Ball/Strike 는 투구 *후* 값이라 타석 안에서 한 칸 밀고 PitchNo==1 을 0-0 으로
되돌리는 그 로직). 같은 계산이 두 곳에 있으면 한쪽만 고쳐져 조용히 어긋난다.

두 가지 낟알(grain)이 한 표에 섞여 있다 — 컬럼 이름으로 구분한다.
  투구 단위: Pitches/Swings/Whiffs/Fouls/Strikes/InPlay/Hits  (그 카운트에서 던져진 공)
  타석 단위: PA/K/BB/OnBase                                    (그 카운트를 거친 타석의 결과)
"타석 단위"는 "그 카운트를 한 번이라도 지나간 타석"이라 버킷끼리 겹친다
(3-1 을 거친 타석이 2S 까지 갈 수 있다) — 세로 합이 전체가 되지 않는다.

Usage:
    python src/build_count_metrics.py --year 2026
    python src/build_count_metrics.py --selfcheck
"""

from __future__ import annotations

import argparse

import pandas as pd

import csv_guard
from build_pitch_arsenal import STRIKEOUT_TEXT, _label, annotate
from build_zone_metrics import PROCESSED_DIR, current_kbo_year, ensure_teams, load_pitches

# 타석 결과 판정 문구. 삼진은 아스널과 같은 상수를 쓴다(낫 아웃 포함).
# "자동 고의4구"는 '볼넷'이라는 말이 안 들어가서 따로 잡는다(2026 49타석).
WALK_TEXT = "볼넷|고의4구"
HBP_TEXT = "몸에 맞는"

# 파울(커트). W = 번트 파울 — 2스트라이크 번트 파울은 삼진이지만 "버텼다"는 아니라
# 커트로 세지 않는 편이 맞다. 그래서 F 만 본다.
FOUL_RESULT = "F"

# 이름 붙인 버킷. (PreBall, PreStrike) 조합으로 정의한다.
#   초구     0-0                     첫 공에 손이 나가나
#   2S       스트라이크 2개           몰린 뒤 버티나
#   투수유리 0-2, 1-2                 일찍 깊게 몰린 상태(2S 의 부분집합)
#   타자유리 2-0, 3-0, 3-1            치기 좋은 공을 기다릴 수 있는 상태
# 투수유리 ⊂ 2S 라 버킷은 서로 배타가 아니다.
NAMED_BUCKETS = {
    "초구": [(0, 0)],
    "2S": [(0, 2), (1, 2), (2, 2), (3, 2)],
    "투수유리": [(0, 2), (1, 2)],
    "타자유리": [(2, 0), (3, 0), (3, 1)],
}

# 리그 12칸 매트릭스. 볼 0~3 × 스트라이크 0~2.
COUNT_CELLS = [(b, s) for b in range(4) for s in range(3)]

COLUMNS = [
    "Season", "Scope", "PlayerId", "Player", "Team", "Side", "Bucket",
    "PA", "PaShare", "Pitches", "Swings", "Whiffs", "Fouls", "Strikes",
    "InPlay", "Hits", "K", "BB", "OnBase",
    "SwingRate", "WhiffRate", "FoulRate", "StrikeRate", "BipAvg", "KRate", "OnBaseRate",
    "Days", "FirstDate", "LastDate",
]


def _ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    """분모 0 은 결측으로 둔다 — 0/0 을 .000 으로 찍으면 없는 표본을 있다고 말하게 된다."""
    return (num / den.where(den > 0)).round(4)


def prepare(pitches: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """투구에 타석 번호를, 타석에 결과 분류를 붙여 (투구, 타석) 두 프레임을 만든다.

    카운트가 하나라도 복원되지 않은 타석은 통째로 버린다. 아스널은 그 '공'만
    빼면 됐지만 여기서는 "이 타석이 2S 를 거쳤나"를 봐야 해서, 구멍 난 타석을
    남기면 거치지 않은 것처럼 보인다(2026 41,181타석 중 103타석, 0.25%).
    """
    df = annotate(pitches)
    df["PaId"] = (df["PitchNo"] == 1).cumsum()
    broken = df.loc[df["PreBall"].isna(), "PaId"].unique()
    df = df[~df["PaId"].isin(broken)].copy()
    df["IsFoul"] = df["PitchResult"] == FOUL_RESULT

    # 타석 결과는 모든 투구 행에 같은 문구로 실려 온다. 마지막 행을 대표로 쓴다.
    grouped = df.groupby("PaId")
    text = grouped["AtBatText"].last().astype(str)
    pa = pd.DataFrame({
        "Season": grouped["Season"].last(),
        "BatterId": grouped["BatterId"].last(),
        "K": text.str.contains(STRIKEOUT_TEXT, regex=True),
        "BB": text.str.contains(WALK_TEXT, regex=True),
        "HBP": text.str.contains(HBP_TEXT),
        "Hit": grouped["IsHit"].max().astype(bool),
    })
    # 출루 = 안타 + 볼넷 + 사구. 실책·야수선택 출루는 빼는 통상 출루율 정의를 따른다.
    pa["OnBase"] = pa["Hit"] | pa["BB"] | pa["HBP"]
    return df, pa.reset_index()


def _mask(pitches: pd.DataFrame, counts: list[tuple[int, int]]) -> pd.Series:
    """(볼, 스트라이크) 목록에 해당하는 투구를 고른다."""
    pairs = list(zip(pitches["PreBall"], pitches["PreStrike"]))
    return pd.Series([p in set(counts) for p in pairs], index=pitches.index)


def _counters(pitches: pd.DataFrame, pa: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """투구 단위 + 타석 단위 원시 카운트를 한 행으로 합친다.

    타석 단위는 "이 투구 묶음에 속한 공이 하나라도 있는 타석"의 결과다.
    """
    counts = pitches.groupby(keys, dropna=False).agg(
        Pitches=("PitchId", "count"),
        Swings=("IsSwing", "sum"),
        Whiffs=("IsWhiff", "sum"),
        Fouls=("IsFoul", "sum"),
        Strikes=("IsStrike", "sum"),
        InPlay=("IsInPlay", "sum"),
        Hits=("IsHit", "sum"),
    )
    reached = pa[pa["PaId"].isin(pitches["PaId"].unique())]
    outcomes = reached.groupby(keys, dropna=False).agg(
        PA=("PaId", "count"),
        K=("K", "sum"),
        BB=("BB", "sum"),
        OnBase=("OnBase", "sum"),
    )
    return counts.join(outcomes, how="outer").fillna(0).reset_index()


def summarize(pitches: pd.DataFrame, pa: pd.DataFrame, scope: str,
              buckets: dict[str, list[tuple[int, int]]]) -> pd.DataFrame:
    """한 Scope(리그 또는 선수)의 버킷별 집계를 만든다."""
    keys = ["Season"] if scope == "리그" else ["Season", "BatterId"]
    frames = []
    for bucket, counts in [("전체", None), *buckets.items()]:
        subset = pitches if counts is None else pitches[_mask(pitches, counts)]
        if subset.empty:
            continue
        agg = _counters(subset, pa, keys)
        agg.insert(0, "Bucket", bucket)
        frames.append(agg)
    out = pd.concat(frames, ignore_index=True)

    # 도달률: 이 버킷을 거친 타석 / 그 선수(또는 리그)의 전체 타석.
    total_pa = out[out["Bucket"] == "전체"].set_index(keys)["PA"]
    out["PaShare"] = (out["PA"] / out.set_index(keys).index.map(total_pa).values).round(4)

    out["Scope"] = scope
    if scope == "리그":
        out["PlayerId"], out["Player"], out["Team"], out["Side"] = 0, "리그 전체", "", ""
    else:
        labels = pitches.groupby("BatterId").agg(
            Player=("BatterName", _label), Team=("BatterTeam", _label), Side=("BatterSide", _label)
        ).reset_index()
        out = out.merge(labels, on="BatterId", how="left")
        out = out.dropna(subset=["BatterId"])
        out["PlayerId"] = out["BatterId"].astype(int)
    return out


def _rates(df: pd.DataFrame) -> pd.DataFrame:
    """원시 카운트에서 비율 지표를 만든다. 분모가 0이면 결측이다."""
    df["SwingRate"] = _ratio(df["Swings"], df["Pitches"])
    df["WhiffRate"] = _ratio(df["Whiffs"], df["Swings"])
    df["FoulRate"] = _ratio(df["Fouls"], df["Pitches"])
    df["StrikeRate"] = _ratio(df["Strikes"], df["Pitches"])
    df["BipAvg"] = _ratio(df["Hits"], df["InPlay"])
    df["KRate"] = _ratio(df["K"], df["PA"])
    df["OnBaseRate"] = _ratio(df["OnBase"], df["PA"])
    return df


def build(season: int) -> pd.DataFrame:
    """투구 원본에서 볼카운트 데이터셋 1종을 만든다."""
    pitches = load_pitches(season)
    if pitches.empty:
        print(f"[count] no pitch data for {season}")
        return pd.DataFrame()

    pitches = ensure_teams(pitches)
    raw_pa = (pitches["PitchNo"] == 1).sum()
    pitches, pa = prepare(pitches)

    # 부분 수집 데이터라 표본 기간을 행마다 함께 싣는다(존/아스널과 같은 규칙).
    # PC 가 꺼진 날은 영구 결손이고, 커버리지를 모르면 표본 기간이 다른 값이
    # 같은 표처럼 보인다.
    dates = pitches["Date"].astype(str)
    days, first_date, last_date = dates.nunique(), dates.min(), dates.max()
    print(
        f"[count] pitches={len(pitches)} pa={len(pa)}/{raw_pa} "
        f"dropped_pa={raw_pa - len(pa)} ({1 - len(pa) / raw_pa:.3%}) "
        f"coverage={days}일 ({first_date}~{last_date})"
    )

    cell_buckets = {f"{b}-{s}": [(b, s)] for b, s in COUNT_CELLS}
    league = summarize(pitches, pa, "리그", {**NAMED_BUCKETS, **cell_buckets})
    players = summarize(pitches, pa, "선수", NAMED_BUCKETS)

    out = _rates(pd.concat([league, players], ignore_index=True))
    out = out.assign(Days=days, FirstDate=first_date, LastDate=last_date)[COLUMNS]
    out = out.sort_values(["Scope", "PlayerId", "Bucket"], ascending=[True, True, True])

    path = PROCESSED_DIR / f"kbo_count_baseball_{season}.csv"
    csv_guard.save_csv(out, path, prefix="[count]",
                       extra=f"batters={players['PlayerId'].nunique()} days={days}")
    return out


def _selfcheck() -> None:
    """손으로 센 두 타석을 고정 입력으로 버킷·타석 결과·비율을 확인한다.

    카운트 컬럼의 의미(투구 후)나 타석 결과 문구가 바뀌면 여기서 먼저 깨진다.
    복원 로직 자체의 검증은 build_pitch_arsenal --selfcheck 가 맡는다(여기서
    다시 구현하지 않으므로 다시 검증하지도 않는다).
    """
    # Ball/Strike 는 그 공을 던진 **뒤** 카운트다(주석의 카운트는 던지기 전 값).
    # 타석1(타자9): 볼 0-0 → 파울 1-0 → 파울 1-1 → 헛스윙 1-2 삼진
    # 타석2(타자8): 초구 0-0 인플레이 안타
    # 타석3(타자9): 볼 0-0 → 볼 1-0 → 스트라이크 2-0 → 스트라이크 2-1 → 안타 2-2
    def row(pid, no, res, ball, strike, is_ball, swing, inplay, hit, text, bat):
        return dict(Season=2026, GameId="G1", Date="2026-08-01", PitchId=pid, PitchNo=no,
                    PitchResult=res, Ball=float(ball), Strike=float(strike), IsBall=is_ball,
                    IsSwing=swing, IsInPlay=inplay, IsHit=hit, AtBatText=text,
                    BatterId=bat, BatterName=f"타자{bat}", BatterTeam="LG", BatterSide="R")

    df = pd.DataFrame([
        row("a1", 1, "B", 1, 0, True, False, False, False, "삼진 아웃", 9),
        row("a2", 2, "F", 1, 1, False, True, False, False, "삼진 아웃", 9),
        row("a3", 3, "F", 1, 2, False, True, False, False, "삼진 아웃", 9),
        row("a4", 4, "S", 1, 2, False, True, False, False, "삼진 아웃", 9),
        row("b1", 1, "H", 0, 0, False, True, True, True, "중견수 앞 1루타", 8),
        row("c1", 1, "B", 1, 0, True, False, False, False, "좌익수 앞 1루타", 9),
        row("c2", 2, "B", 2, 0, True, False, False, False, "좌익수 앞 1루타", 9),
        row("c3", 3, "T", 2, 1, False, False, False, False, "좌익수 앞 1루타", 9),
        row("c4", 4, "T", 2, 2, False, False, False, False, "좌익수 앞 1루타", 9),
        row("c5", 5, "H", 2, 2, False, True, True, True, "좌익수 앞 1루타", 9),
    ])
    pitches, pa = prepare(df)
    assert len(pa) == 3 and len(pitches) == 10, (len(pa), len(pitches))
    assert pa["K"].tolist() == [True, False, False], pa["K"].tolist()
    assert pa["OnBase"].tolist() == [False, True, True], pa["OnBase"].tolist()

    league = _rates(summarize(pitches, pa, "리그", NAMED_BUCKETS)).set_index("Bucket")
    # 초구는 타석 수만큼 3구, 그중 스윙 1개(타석2) → 초구 스윙률 1/3.
    assert league.loc["초구", "Pitches"] == 3 and league.loc["초구", "SwingRate"] == round(1 / 3, 4)
    # 2S 를 거친 타석은 1·3번 두 개(도달률 2/3), 그중 삼진 1개·출루 1개.
    assert league.loc["2S", "PA"] == 2 and league.loc["2S", "PaShare"] == round(2 / 3, 4)
    assert league.loc["2S", "KRate"] == 0.5 and league.loc["2S", "OnBaseRate"] == 0.5
    # 2S 에서 던져진 공은 a4(1-2)·c5(2-2) 둘뿐이다(a3 는 던질 때 1-1).
    assert league.loc["2S", "Pitches"] == 2, league.loc["2S", "Pitches"]
    # 투수유리(0-2·1-2)는 2S 의 진부분집합 — 타석1만 걸린다(버킷이 배타가 아니다).
    assert league.loc["투수유리", "PA"] == 1 and league.loc["투수유리", "Pitches"] == 1
    # 타자유리(2-0·3-0·3-1)는 타석3의 c3 한 개.
    assert league.loc["타자유리", "PA"] == 1 and league.loc["타자유리", "Pitches"] == 1
    # 파울은 F 만(a2·a3). 커트율 = 2/10.
    assert league.loc["전체", "Fouls"] == 2 and league.loc["전체", "FoulRate"] == 0.2
    # 인플레이 2개가 모두 안타 → 인플레이 타율 1.000. 헛스윙은 S 하나뿐.
    assert league.loc["전체", "BipAvg"] == 1.0 and league.loc["전체", "Whiffs"] == 1
    # 분모 0 은 .000 이 아니라 결측이다(초구 3구 중 스윙 1 → 헛스윙 분모는 1).
    assert pd.isna(league.loc["타자유리", "WhiffRate"]), "스윙 0인데 헛스윙률이 찍혔다"

    players = _rates(summarize(pitches, pa, "선수", NAMED_BUCKETS))
    nine = players[(players["PlayerId"] == 9) & (players["Bucket"] == "전체")].iloc[0]
    assert nine["PA"] == 2 and nine["Pitches"] == 9 and nine["Team"] == "LG"
    assert nine["KRate"] == 0.5 and nine["OnBaseRate"] == 0.5
    eight = players[(players["PlayerId"] == 8) & (players["Bucket"] == "초구")].iloc[0]
    assert eight["SwingRate"] == 1.0 and eight["PaShare"] == 1.0

    # 카운트가 깨진 타석은 통째로 빠진다(그 공만 빼면 "2S 를 안 거쳤다"가 된다).
    broken = df.copy()
    broken.loc[1, "Ball"] = 9.0
    _, pa2 = prepare(broken)
    assert len(pa2) == 2, f"깨진 타석이 남았다 ({len(pa2)})"

    # 자동 고의4구는 '볼넷'이라는 말이 없어 따로 잡는다.
    ibb = df.head(1).assign(AtBatText="자동 고의4구")
    assert prepare(ibb)[1]["BB"].all(), "자동 고의4구가 볼넷으로 안 잡힌다"

    print("build_count_metrics selfcheck OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=current_kbo_year())
    parser.add_argument("--selfcheck", action="store_true", help="파생 로직 자가검증만 실행")
    args = parser.parse_args()
    if args.selfcheck:
        _selfcheck()
        return
    build(args.year)


if __name__ == "__main__":
    main()
