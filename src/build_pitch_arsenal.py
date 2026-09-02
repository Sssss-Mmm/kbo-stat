"""
Build season-cumulative pitch-type (arsenal) datasets for pitchers and batters.

Reads the per-day Naver pitch CSVs (data/raw/naver/naver_kbo_pitches_*.csv) via
build_zone_metrics.load_pitches() — 같은 원본, 같은 시즌 선별·중복 제거 로직을
그대로 쓴다 — 존 격자 대신 PitchType/SpeedKmh 축으로 접어 두 파일을 만든다:

    data/processed/kbo_pitcher_arsenal_{season}.csv   이 투수가 뭘 던지나
    data/processed/kbo_batter_vs_pitch_{season}.csv   이 타자가 뭘 못 치나

각 행은 (선수, 구종, 볼카운트 버킷) 하나이고 투구 수·구속·헛스윙·스트라이크·
인플레이 안타를 담는다.

주의 — 원본 데이터의 함정 두 가지(실제 데이터로 확인함):
  1) PitchResult 의 'H' 는 안타가 아니라 **인플레이**다('H' 수 == IsInPlay 수).
     안타는 반드시 IsHit 으로 센다.
  2) Ball/Strike 컬럼은 그 공을 **던진 뒤** 카운트다("1구 볼" 행이 Ball=1).
     배합을 보려면 던지기 전 카운트가 필요하므로 타석 안에서 한 칸 밀어 쓴다.

Usage:
    python src/build_pitch_arsenal.py --year 2026
    python src/build_pitch_arsenal.py --selfcheck
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

import csv_guard
from build_zone_metrics import PROCESSED_DIR, current_kbo_year, ensure_teams, load_pitches

# 리그 전체에서 이 투구 수 미만인 구종은 "기타"로 묶는다.
# (2026 너클볼 6구, 2025 슬러브 3구·싱커 1구 같은 극소수 분류가 표를 어지럽힌다)
RARE_PITCH_MIN = 100

# 볼카운트 버킷. "전체"는 모든 투구, 나머지는 부분집합이고 서로 배타가 아니다
# (결정구는 유리 카운트와 겹친다) — 합이 전체가 되지 않는다는 뜻이다.
BUCKETS = {
    "초구": lambda d: (d["PreBall"] == 0) & (d["PreStrike"] == 0),
    "유리": lambda d: (d["PreStrike"] == 2) & (d["PreBall"] <= 1),
    "불리": lambda d: (d["PreBall"] == 3) & (d["PreStrike"] <= 1),
    "결정구": lambda d: d["IsPutaway"],
}

# 결정구 판정에 쓰는 타석 결과 문구(삼진 아웃 / 포수 스트라이크 낫 아웃).
STRIKEOUT_TEXT = "삼진|낫 아웃"


def annotate(pitches: pd.DataFrame) -> pd.DataFrame:
    """투구 전 볼카운트(PreBall/PreStrike)와 결정구 여부를 붙인다.

    타석은 PitchNo==1 에서 시작하고 한 타석 안의 행은 (GameId, PitchId) 정렬에서
    연속·오름차순이다(2026 41,181타석 중 99.7% 확인). 그래서 groupby 없이 한 칸
    shift 하고 타석 첫 공만 0-0 으로 되돌리면 던지기 전 카운트가 나온다.

    밀린 값이 "이전 카운트 + 이번 공의 효과 == 현재 카운트"를 만족하지 않으면
    (타석 행이 끊긴 0.1%) 카운트를 NaN 으로 두어 버킷에서 빠지게 한다 —
    틀린 카운트로 배합을 계산하느니 그 공을 세지 않는 편이 낫다.
    """
    df = pitches.sort_values(["GameId", "PitchId"], kind="mergesort").reset_index(drop=True)
    first = df["PitchNo"] == 1
    pre_ball = df["Ball"].shift(1).where(~first, 0)
    pre_strike = df["Strike"].shift(1).where(~first, 0)
    consistent = (pre_ball == df["Ball"] - df["IsBall"].astype(int)) & (
        df["Strike"] - pre_strike
    ).between(0, 1)
    df["PreBall"] = pre_ball.where(consistent)
    df["PreStrike"] = pre_strike.where(consistent)

    # 타석의 마지막 투구 = 다음 행이 새 타석의 1구(마지막 행도 마지막 투구).
    is_last = df["PitchNo"].shift(-1).fillna(1).eq(1)
    df["IsPutaway"] = is_last & df["AtBatText"].astype(str).str.contains(
        STRIKEOUT_TEXT, regex=True
    )

    # 결과 플래그. 'S'=헛스윙, IsBall==False 인 모든 공이 스트라이크(파울·인플레이 포함).
    df["IsWhiff"] = df["PitchResult"] == "S"
    df["IsStrike"] = ~df["IsBall"].astype(bool)
    return df


def fold_rare_types(pitches: pd.DataFrame) -> pd.DataFrame:
    """리그 전체 표본이 적은 구종을 "기타"로 묶는다.

    화이트리스트를 두지 않는다 — 네이버가 새 구종(스위퍼 등)을 추가해도 관측된
    이름 그대로 살아남고, 표본이 쌓이기 전까지만 기타에 머문다.
    """
    counts = pitches["PitchType"].value_counts()
    rare = set(counts[counts < RARE_PITCH_MIN].index)
    df = pitches.copy()
    df["PitchType"] = df["PitchType"].fillna("기타")
    df.loc[df["PitchType"].isin(rare), "PitchType"] = "기타"
    return df


def _ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    """분모 0 은 결측으로 둔다 — 0/0 을 .000 으로 보여주면 없는 표본을 있다고 말하게 된다."""
    return (num / den.where(den > 0)).round(4)


def _aggregate(pitches: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """(선수 키..., 구종) 단위 원시 카운트 집계."""
    return (
        pitches.groupby([*keys, "PitchType"], dropna=False)
        .agg(
            Pitches=("PitchId", "count"),
            AvgKmh=("SpeedKmh", "mean"),
            MaxKmh=("SpeedKmh", "max"),
            Swings=("IsSwing", "sum"),
            Whiffs=("IsWhiff", "sum"),
            Strikes=("IsStrike", "sum"),
            InPlay=("IsInPlay", "sum"),
            Hits=("IsHit", "sum"),
        )
        .reset_index()
    )


def _label(series: pd.Series) -> str:
    """한 선수의 이름/팀/타석 방향 대표값 = 가장 많이 관측된 값.

    시즌 중 이적한 선수는 팀이 둘이고, 스위치히터는 타석 방향이 둘이며, 팀·방향이
    빠진 투구도 드물게 있다. 이런 컬럼을 집계 키에 넣으면 한 선수가 표에서 둘로
    쪼개진다(실제로 박성한이 직구 905구/1구로 갈렸다). 선수 동일성은 PlayerId
    하나로 정하고, 나머지는 표시용 라벨로만 쓴다.
    """
    mode = series.dropna().mode()
    return mode.iloc[0] if len(mode) else ""


def summarize(pitches: pd.DataFrame, id_col: str, name_col: str, team_col: str,
              side_col: str | None) -> pd.DataFrame:
    """한 선수 관점(투수 또는 타자)에서 구종×볼카운트 버킷 집계를 만든다."""
    keys = ["Season", id_col]
    frames = []
    for bucket, mask in [("전체", None), *BUCKETS.items()]:
        subset = pitches if mask is None else pitches[mask(pitches)]
        if subset.empty:
            continue
        agg = _aggregate(subset, keys)
        agg.insert(0, "CountBucket", bucket)
        frames.append(agg)
    summary = pd.concat(frames, ignore_index=True)

    label_cols = {"Player": name_col, "Team": team_col}
    if side_col:
        label_cols["Side"] = side_col
    labels = pitches.groupby(id_col).agg(
        **{out: (src, _label) for out, src in label_cols.items()}
    ).reset_index()
    summary = summary.merge(labels, on=id_col, how="left")
    summary = summary.rename(columns={id_col: "PlayerId"})
    if not side_col:
        summary["Side"] = ""

    summary = summary.dropna(subset=["PlayerId"])
    summary["PlayerId"] = summary["PlayerId"].astype(int)

    # 구사율은 같은 (선수, 버킷) 안에서의 비중이라 버킷별로 따로 나눈다.
    bucket_total = summary.groupby(["PlayerId", "CountBucket"])["Pitches"].transform("sum")
    summary["BucketPitches"] = bucket_total
    summary["UsageRate"] = (summary["Pitches"] / bucket_total).round(4)
    summary["WhiffRate"] = _ratio(summary["Whiffs"], summary["Swings"])
    summary["StrikeRate"] = _ratio(summary["Strikes"], summary["Pitches"])
    summary["BipAvg"] = _ratio(summary["Hits"], summary["InPlay"])
    summary["AvgKmh"] = summary["AvgKmh"].round(1)
    return summary.sort_values(
        ["PlayerId", "CountBucket", "Pitches"], ascending=[True, True, False]
    )


def build(season: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """투구 원본에서 투수 아스널 / 타자 상대 구종 데이터셋 2종을 만든다."""
    pitches = load_pitches(season)
    if pitches.empty:
        print(f"[arsenal] no pitch data for {season}")
        return pd.DataFrame(), pd.DataFrame()

    pitches = ensure_teams(pitches)
    pitches = annotate(pitches)
    pitches = fold_rare_types(pitches)

    # 부분 수집 데이터라 표본 기간을 행마다 함께 싣는다. 존 데이터와 마찬가지로
    # PC 가 꺼진 날은 영구 결손이고, 커버리지를 모르면 표본 기간이 다른 값이
    # 같은 표처럼 보인다.
    # ponytail: 매 행에 같은 값이 반복되지만 CSV 직결 라우터가 별도 메타 파일 없이
    # 커버리지를 그대로 넘길 수 있어 가장 싸다.
    dates = pitches["Date"].astype(str)
    days, first_date, last_date = dates.nunique(), dates.min(), dates.max()
    bad_count = pitches["PreBall"].isna().mean()
    print(
        f"[arsenal] pitches={len(pitches)} types={pitches['PitchType'].nunique()} "
        f"putaway={int(pitches['IsPutaway'].sum())} "
        f"count_unresolved={bad_count:.3%} "
        f"coverage={days}일 ({first_date}~{last_date})"
    )

    pitcher = summarize(pitches, "PitcherId", "PitcherName", "PitcherTeam", None)
    batter = summarize(pitches, "BatterId", "BatterName", "BatterTeam", "BatterSide")

    cols = ["Season", "PlayerId", "Player", "Team", "Side", "PitchType", "CountBucket",
            "Pitches", "BucketPitches", "AvgKmh", "MaxKmh", "Swings", "Whiffs",
            "Strikes", "InPlay", "Hits", "UsageRate", "WhiffRate", "StrikeRate",
            "BipAvg", "Days", "FirstDate", "LastDate"]
    out = []
    for df, path in [
        (pitcher, PROCESSED_DIR / f"kbo_pitcher_arsenal_{season}.csv"),
        (batter, PROCESSED_DIR / f"kbo_batter_vs_pitch_{season}.csv"),
    ]:
        df = df.assign(Days=days, FirstDate=first_date, LastDate=last_date)[cols]
        csv_guard.save_csv(df, path, prefix="[arsenal]",
                           extra=f"players={df['PlayerId'].nunique()} days={days}")
        out.append(df)
    return out[0], out[1]


def _selfcheck() -> None:
    """실제 데이터에서 관측한 한 타석을 고정 입력으로 파생 로직을 확인한다.

    카운트 컬럼의 의미(투구 후)나 PitchResult 코드가 바뀌면 여기서 먼저 깨진다.
    """
    # 실측 타석: 1구 볼 → 2구 파울 → 3구 헛스윙(삼진). Ball/Strike 는 투구 후 값.
    pa = pd.DataFrame({
        "Season": [2026] * 4,
        "GameId": ["G1"] * 4,
        "PitchId": ["a1", "a2", "a3", "b1"],
        "PitchNo": [1, 2, 3, 1],
        "PitchResult": ["B", "F", "S", "H"],
        "PitchType": ["직구", "슬라이더", "포크", "직구"],
        "SpeedKmh": [148.0, 135.0, 132.0, 150.0],
        "Ball": [1.0, 1.0, 1.0, 0.0],
        "Strike": [0.0, 1.0, 2.0, 0.0],
        "IsBall": [True, False, False, False],
        "IsSwing": [False, True, True, True],
        "IsInPlay": [False, False, False, True],
        "IsHit": [False, False, False, True],
        "AtBatText": ["삼진 아웃"] * 3 + ["중견수 앞 1루타"],
        "PitcherId": [1, 1, 1, 1],
        "PitcherName": ["투수"] * 4,
        "PitcherTeam": ["두산"] * 4,
        "BatterId": [9, 9, 9, 8],
        "BatterName": ["타자A"] * 3 + ["타자B"],
        "BatterTeam": ["LG"] * 4,
        "BatterSide": ["R"] * 4,
    })
    ann = annotate(pa)

    # 투구 전 카운트: 1구=0-0, 2구=1-0, 3구=1-1(파울로 1스트라이크가 된 뒤).
    assert ann["PreBall"].tolist() == [0, 1, 1, 0], ann["PreBall"].tolist()
    assert ann["PreStrike"].tolist() == [0, 0, 1, 0], ann["PreStrike"].tolist()
    # 결정구는 삼진 타석의 마지막 공 하나뿐(3구 헛스윙).
    assert ann["IsPutaway"].tolist() == [False, False, True, False]
    # 헛스윙은 'S' 만. 'H' 는 인플레이지 안타가 아니고 스트라이크로 센다.
    assert ann["IsWhiff"].tolist() == [False, False, True, False]
    assert ann["IsStrike"].tolist() == [False, True, True, True]

    res = summarize(ann, "PitcherId", "PitcherName", "PitcherTeam", None)
    total = res[res["CountBucket"] == "전체"]
    assert total["Pitches"].sum() == 4, total["Pitches"].tolist()
    assert abs(total["UsageRate"].sum() - 1.0) < 1e-6, "구사율 합이 100%가 아니다"
    # 직구 2구 중 인플레이 1개가 안타 → 인플레이 타율 1.000, 그 외 구종은 결측.
    fastball = total[total["PitchType"] == "직구"].iloc[0]
    assert fastball["Pitches"] == 2 and fastball["MaxKmh"] == 150.0
    assert fastball["BipAvg"] == 1.0 and fastball["InPlay"] == 1
    # 포크: 스윙 1 / 헛스윙 1 → 헛스윙률 1.000
    fork = total[total["PitchType"] == "포크"].iloc[0]
    assert fork["WhiffRate"] == 1.0, fork["WhiffRate"]
    # 초구 버킷은 타석 첫 공 2개(직구·직구)뿐.
    assert res[res["CountBucket"] == "초구"]["Pitches"].sum() == 2
    assert res[res["CountBucket"] == "결정구"]["PitchType"].tolist() == ["포크"]
    # 유리(1-1)·불리(3볼) 카운트는 이 표본에 없다.
    assert "유리" not in res["CountBucket"].values
    assert "불리" not in res["CountBucket"].values

    # 이적(팀 2개)·스위치히터(방향 2개)·결측이 있어도 선수는 하나로 남는다.
    moved = ann.copy()
    moved.loc[3, "BatterId"] = 9
    moved.loc[3, "BatterTeam"] = "KT"
    moved.loc[3, "BatterSide"] = None
    bat = summarize(moved, "BatterId", "BatterName", "BatterTeam", "BatterSide")
    bat_total = bat[bat["CountBucket"] == "전체"]
    assert bat_total["PlayerId"].nunique() == 1, "이적/결측으로 선수가 쪼개졌다"
    assert (bat_total["PitchType"] == "직구").sum() == 1, "같은 구종이 두 행으로 갈렸다"
    assert bat_total["Pitches"].sum() == 4 and bat_total["Side"].iloc[0] == "R"

    # 타석 행이 끊기면 카운트를 포기한다(틀린 배합보다 결측이 낫다).
    broken = ann.copy()
    broken.loc[1, "Ball"] = 9.0
    assert annotate(broken)["PreBall"].isna().any(), "모순된 카운트가 그대로 통과됐다"

    # 표본 적은 구종은 기타로 묶인다(RARE_PITCH_MIN 미만).
    folded = fold_rare_types(pd.DataFrame({"PitchType": ["직구"] * 200 + ["너클볼"] * 3}))
    assert set(folded["PitchType"]) == {"직구", "기타"}, set(folded["PitchType"])

    print("build_pitch_arsenal selfcheck OK")


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
