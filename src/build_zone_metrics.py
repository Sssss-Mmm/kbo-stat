"""
Build season-cumulative hot/cold zone datasets for batters and pitchers.

Reads the per-day Naver pitch CSVs (data/raw/naver/naver_kbo_pitches_*.csv),
de-duplicates pitches across overlapping date ranges, keeps the 3x3 strike-zone
cells, and writes two processed datasets the web zones page consumes:

    data/processed/kbo_batter_zones_{season}.csv
    data/processed/kbo_pitcher_zones_{season}.csv

Each row is one (player, zone) cell with pitch counts and hot/cold rate metrics.

Usage:
    python src/build_zone_metrics.py --year 2026
"""

from __future__ import annotations

import argparse
import glob
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).parent.parent
RAW_DIR = ROOT / "data" / "raw" / "naver"
PROCESSED_DIR = ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Only the 3x3 in-strike-zone cells (row-col, row 3=top, col 1=left).
ZONE_CELL = re.compile(r"^[1-3]-[1-3]$")


def current_kbo_year() -> int:
    return datetime.now(ZoneInfo("Asia/Seoul")).year


def load_pitches(season: int) -> pd.DataFrame:
    files = sorted(glob.glob(str(RAW_DIR / "naver_kbo_pitches_*.csv")))
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


def summarize(pitches: pd.DataFrame, id_col: str, name_col: str, team_col: str,
              extra_keys: list[str]) -> pd.DataFrame:
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
    pitches = load_pitches(season)
    if pitches.empty:
        print(f"[zones] no pitch data for {season}")
        return pd.DataFrame(), pd.DataFrame()

    pitches = ensure_teams(pitches)
    pitches = pitches[pitches["Zone"].astype(str).str.match(ZONE_CELL)].copy()
    if pitches.empty:
        print(f"[zones] no in-zone pitches for {season}")
        return pd.DataFrame(), pd.DataFrame()

    batter = summarize(pitches, "BatterId", "BatterName", "BatterTeam", ["BatterSide"])
    batter = batter.rename(columns={"BatterSide": "Side"})
    pitcher = summarize(pitches, "PitcherId", "PitcherName", "PitcherTeam", [])

    batter_path = PROCESSED_DIR / f"kbo_batter_zones_{season}.csv"
    pitcher_path = PROCESSED_DIR / f"kbo_pitcher_zones_{season}.csv"
    batter.to_csv(batter_path, index=False, encoding="utf-8-sig")
    pitcher.to_csv(pitcher_path, index=False, encoding="utf-8-sig")
    print(f"[zones] saved {batter_path.name} rows={len(batter)} players={batter['PlayerId'].nunique()}")
    print(f"[zones] saved {pitcher_path.name} rows={len(pitcher)} players={pitcher['PlayerId'].nunique()}")
    return batter, pitcher


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=current_kbo_year())
    args = parser.parse_args()
    build(args.year)


if __name__ == "__main__":
    main()
