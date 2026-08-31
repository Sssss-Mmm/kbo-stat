"""
Build season-cumulative hot/cold zone datasets for batters and pitchers.

Reads the per-day Naver pitch CSVs (data/raw/naver/naver_kbo_pitches_*.csv),
de-duplicates pitches across overlapping date ranges, re-buckets every pitch
into a GRID_N x GRID_N grid from its plate coordinates, and writes two
processed datasets the zones page consumes:

    data/processed/kbo_batter_zones_{season}.csv
    data/processed/kbo_pitcher_zones_{season}.csv

Each row is one (player, zone) cell with pitch counts and hot/cold rate metrics.

원본 CSV 의 Zone 컬럼은 크롤러가 만든 3x3+존밖 라벨이라 여기서는 쓰지 않고,
PlateX/PlateZ 와 타자별 존 상하단(TopSz/BottomSz)으로 직접 다시 계산한다.
격자 크기를 바꾸려면 GRID_N 하나만 고치면 된다(화면은 데이터에서 격자 크기를
읽으므로 따라온다).

Usage:
    python src/build_zone_metrics.py --year 2026
    python src/build_zone_metrics.py --selfcheck
"""

from __future__ import annotations

import argparse
import glob
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import csv_guard
from crawl_naver_pitch_zones import HALF_PLATE_WIDTH_FT

ROOT = Path(__file__).parent.parent
RAW_DIR = ROOT / "data" / "raw" / "naver"
PROCESSED_DIR = ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# 격자 한 변의 칸 수. 바깥 한 겹은 스트라이크존 밖(유인구), 안쪽 GRID_N-2 칸이
# 스트라이크존을 등분한다. 5 이면 안쪽 3x3 이 스트라이크존과 정확히 일치한다.
# ponytail: 안쪽 GRID_N-2 칸 = 스트라이크존, 바깥 테두리 한 겹 = 존 밖(경계 없이
# 열려 있어 아무리 멀리 빠져도 테두리 칸이 흡수한다). 4 면 안쪽이 2×2 라 정중앙
# 칸이 없고, 3 이면 스트라이크존 전체가 한 칸이 된다.
GRID_N = 5

# 존 라벨 규칙: "row-col", row 1 = 맨 위(높은 코스), col 1 = 좌(x 가 작은 쪽).
# 크롤러 zone_bucket() 과 같은 방향이다.


def current_kbo_year() -> int:
    """한국 시간 기준 현재 시즌 연도."""
    return datetime.now(ZoneInfo("Asia/Seoul")).year


def _file_covers_season(path: str, season: int) -> bool:
    """파일명(naver_kbo_pitches_{날짜}[_{날짜}].csv)이 해당 시즌을 담는지 본다.

    KBO 시즌은 한 해 안에서 끝나므로 파일명의 연도만 봐도 다른 시즌 파일을
    열지 않고 걸러낼 수 있다. 날짜가 없는 이름은 판단이 불가하니 읽어서
    Season 컬럼에 맡긴다(잘못 거르는 쪽보다 낫다).
    """
    years = set(re.findall(r"(\d{4})-\d{2}-\d{2}", Path(path).stem))
    return not years or str(season) in years


def load_pitches(season: int) -> pd.DataFrame:
    """해당 시즌 투구 CSV만 골라 읽어 합치고 중복 투구를 제거한다.

    파일명으로 먼저 걸러 다른 시즌 파일은 아예 열지 않는다 — 백필로 파일이
    수백 MB 늘어도 매일 새벽 cron 이 읽는 양은 그 시즌치로 유지된다.
    Season 컬럼 필터는 그대로 남아 있어 결과는 파일명과 무관하게 정확하다.
    """
    files = sorted(glob.glob(str(RAW_DIR / "naver_kbo_pitches_*.csv")))
    files = [path for path in files if _file_covers_season(path, season)]
    if not files:
        return pd.DataFrame()
    frames = [pd.read_csv(path) for path in files]
    pitches = pd.concat(frames, ignore_index=True)
    pitches = pitches[pitches["Season"] == season].copy()
    # Drop duplicate pitches that appear in overlapping date-range exports.
    pitches = pitches.dropna(subset=["PitchId"]).drop_duplicates(["GameId", "PitchId"])
    return pitches


def ensure_teams(pitches: pd.DataFrame) -> pd.DataFrame:
    """Derive batter/pitcher teams from HomeAway for older files that lack them.

    HomeAway==1 means the home team is batting (pitcher is the away team).
    """
    if "BatterTeam" in pitches.columns and pitches["BatterTeam"].notna().all():
        return pitches
    home_batting = pitches["HomeAway"].astype(str).isin(["1", "home", "HOME"])
    pitches["BatterTeam"] = pitches["HomeTeam"].where(home_batting, pitches["AwayTeam"])
    pitches["PitcherTeam"] = pitches["AwayTeam"].where(home_batting, pitches["HomeTeam"])
    return pitches


def _axis_bins(frac: pd.Series) -> pd.Series:
    """상대 위치(0=존 시작, 1=존 끝)를 1~GRID_N 칸 번호로 바꾼다.

    0~1 구간을 안쪽 GRID_N-2 칸이 등분하고, 0 미만/1 초과는 각각 테두리 칸
    1 과 GRID_N 이 받는다. 테두리는 위아래 경계가 없어 아무리 멀리 빠진 공도
    흡수한다 — 좌표만 있으면 버려지는 투구가 없다.
    """
    inner = GRID_N - 2
    bins = (2 + np.floor(frac * inner)).clip(2, GRID_N - 1)
    return bins.where(frac >= 0, 1).where(frac <= 1, GRID_N).astype(int)


def assign_zones(pitches: pd.DataFrame) -> pd.DataFrame:
    """PlateX/PlateZ 로 GRID_N×GRID_N 존을 다시 매긴다. 좌표가 없는 투구는 버린다.

    col: x = ±HALF_PLATE_WIDTH_FT 가 스트라이크존 좌우 경계, col 1 = 좌(x 최소).
    row: z = BottomSz~TopSz 가 존 상하 경계, row 1 = 맨 위(크롤러 zone_bucket 과 동일).
    """
    df = pitches.dropna(subset=["PlateX", "PlateZ", "TopSz", "BottomSz"]).copy()
    df = df[df["TopSz"] > df["BottomSz"]]
    col = _axis_bins((df["PlateX"] + HALF_PLATE_WIDTH_FT) / (HALF_PLATE_WIDTH_FT * 2))
    row = _axis_bins((df["TopSz"] - df["PlateZ"]) / (df["TopSz"] - df["BottomSz"]))
    df["Zone"] = row.astype(str) + "-" + col.astype(str)
    return df


def summarize(pitches: pd.DataFrame, id_col: str, name_col: str, team_col: str,
              extra_keys: list[str]) -> pd.DataFrame:
    """(선수, 존) 단위로 투구를 집계하고 스윙률/인플레이 안타율을 계산한다."""
    group_cols = ["Season", id_col, name_col, team_col, *extra_keys, "Zone"]
    summary = (
        pitches.groupby(group_cols, dropna=False)
        .agg(
            Pitches=("PitchId", "count"),
            Swings=("IsSwing", "sum"),
            Balls=("IsBall", "sum"),
            CalledStrikes=("IsCalledStrike", "sum"),
            InPlay=("IsInPlay", "sum"),
            Hits=("IsHit", "sum"),
            AvgSpeedKmh=("SpeedKmh", "mean"),
        )
        .reset_index()
    )
    rename = {id_col: "PlayerId", name_col: "Player", team_col: "Team"}
    summary = summary.rename(columns=rename)
    summary["SwingRate"] = summary["Swings"] / summary["Pitches"]
    summary["BipHitRate"] = summary["Hits"] / summary["InPlay"].replace(0, pd.NA)
    summary["AvgSpeedKmh"] = summary["AvgSpeedKmh"].round(1)
    summary = summary.dropna(subset=["PlayerId"])
    summary["PlayerId"] = summary["PlayerId"].astype(int)
    return summary


def build(season: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """투구 데이터에서 타자/투수의 GRID_N×GRID_N 존별 핫/콜드 데이터셋 2종을 만든다."""
    pitches = load_pitches(season)
    if pitches.empty:
        print(f"[zones] no pitch data for {season}")
        return pd.DataFrame(), pd.DataFrame()

    pitches = ensure_teams(pitches)
    total = len(pitches)
    pitches = assign_zones(pitches)
    if pitches.empty:
        print(f"[zones] no pitches with plate coordinates for {season}")
        return pd.DataFrame(), pd.DataFrame()

    # 부분 수집 데이터라 표본 기간을 함께 남긴다(존 데이터는 PC 가 꺼진 날이 영구 결손).
    dropped = total - len(pitches)
    dates = pitches["Date"].astype(str)
    print(
        f"[zones] grid={GRID_N}x{GRID_N} pitches={len(pitches)}/{total} "
        f"dropped_no_coords={dropped} ({dropped / total:.2%}) "
        f"coverage={dates.nunique()}일 ({dates.min()}~{dates.max()})"
    )

    batter = summarize(pitches, "BatterId", "BatterName", "BatterTeam", ["BatterSide"])
    batter = batter.rename(columns={"BatterSide": "Side"})
    pitcher = summarize(pitches, "PitcherId", "PitcherName", "PitcherTeam", [])

    batter_path = PROCESSED_DIR / f"kbo_batter_zones_{season}.csv"
    pitcher_path = PROCESSED_DIR / f"kbo_pitcher_zones_{season}.csv"
    csv_guard.save_csv(batter, batter_path, prefix="[zones]",
                       extra=f"players={batter['PlayerId'].nunique()}")
    csv_guard.save_csv(pitcher, pitcher_path, prefix="[zones]",
                       extra=f"players={pitcher['PlayerId'].nunique()}")
    return batter, pitcher


def _selfcheck() -> None:
    """실제 투구 한 줄을 고정 입력으로 존 배정과 투구 수 보존을 확인한다.

    좌표 컬럼이나 존 경계 규칙이 바뀌면 여기서 먼저 깨진다.
    """
    # data/raw/naver/naver_kbo_pitches_2026-03-28_2026-06-10.csv 첫 줄(크롤러 Zone="1-2").
    sample = pd.DataFrame({
        "PlateX": [0.120791, -5.0, 0.0, 0.0, 0.7083],
        "PlateZ": [3.077750972023956, -1.0, 2.5085, 9.9, 2.5085],
        "TopSz": [3.378] * 5,
        "BottomSz": [1.639] * 5,
    })
    out = assign_zones(sample)
    assert len(out) == len(sample), "좌표가 멀쩡한데 투구가 버려졌다"

    if GRID_N == 5:
        # 안쪽 3×3(2~4번 칸)이 스트라이크존, 1·5번 칸이 존 밖 테두리.
        assert out["Zone"].tolist() == ["2-3", "5-1", "3-3", "1-3", "3-4"], out["Zone"].tolist()

    rc = out["Zone"].str.split("-", expand=True).astype(int)
    assert rc.min().min() >= 1 and rc.max().max() <= GRID_N, "격자 범위를 벗어난 칸이 생겼다"

    # 좌표가 없으면 버린다(테두리로 흡수하지 않는다 — 위치를 모르는 공이라서).
    missing = pd.DataFrame({"PlateX": [None], "PlateZ": [2.5], "TopSz": [3.3], "BottomSz": [1.6]})
    assert len(assign_zones(missing)) == 0, "좌표 없는 투구가 존에 배정됐다"

    # 파일명 기반 시즌 선별(F-3): 다른 시즌 파일을 열지 않되 판단 불가한 이름은 읽는다.
    assert _file_covers_season("naver_kbo_pitches_2025-05-01_2025-05-31.csv", 2025)
    assert not _file_covers_season("naver_kbo_pitches_2025-05-01_2025-05-31.csv", 2026)
    assert _file_covers_season("naver_kbo_pitches_2026-06-10.csv", 2026)
    assert _file_covers_season("naver_kbo_pitches_legacy.csv", 2026), "판단 불가한 이름은 읽어야 한다"

    print(f"build_zone_metrics selfcheck OK (GRID_N={GRID_N})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=current_kbo_year())
    parser.add_argument("--selfcheck", action="store_true", help="존 배정 자가검증만 실행")
    args = parser.parse_args()
    if args.selfcheck:
        _selfcheck()
        return
    build(args.year)


if __name__ == "__main__":
    main()
