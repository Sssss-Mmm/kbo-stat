"""
Merge per-season raw CSVs into a single processed dataset
suitable for year-N → year-N+1 prediction.

Output: data/processed/kbo_batters.csv

Key transformations:
- Numeric coercion for all stat columns
- Minimum PA filter (default 100) to remove noise
- 'next_wRC+' target column (wRC+ in the following season)
"""

import re
import pandas as pd
from pathlib import Path

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

MIN_PA = 100  # minimum plate appearances to keep a row


def _clean_name(name: str) -> str:
    """'Seong-han Park박성한' → 'Seong-han Park'"""
    return re.sub(r"[฀-鿿가-힯]+", "", str(name)).strip()


def load_raw() -> pd.DataFrame:
    """data/raw 의 시즌별 kbo_*.csv 를 모두 읽어 하나로 합친다(전부 문자열로 로드)."""
    files = sorted(RAW_DIR.glob("kbo_*.csv"))
    if not files:
        raise FileNotFoundError("No raw files found. Run src/crawl.py first.")
    frames = [pd.read_csv(f, dtype=str) for f in files]
    df = pd.concat(frames, ignore_index=True)
    return df


def build(min_pa: int = MIN_PA) -> pd.DataFrame:
    """원본을 정제(이름/숫자/PA필터)하고 다음 시즌 wRC+를 타깃으로 붙여 저장한다."""
    df = load_raw()

    # clean player name
    df["Name"] = df["Name"].apply(_clean_name)

    # numeric coercion
    skip = {"Name", "Team", "PlayerName", "KName"}
    num_cols = [c for c in df.columns if c not in skip]
    df[num_cols] = df[num_cols].apply(pd.to_numeric, errors="coerce")

    # PA filter
    df = df[df["PA"] >= min_pa].copy()

    # sort
    df = df.sort_values(["Season", "Name"]).reset_index(drop=True)

    # next-season wRC+ target (for same player)
    df = df.sort_values(["Name", "Season"])
    df["next_wRC+"] = (
        df.groupby("Name")["wRC+"].shift(-1)
    )
    # only keep rows where next season is season+1 (no gaps)
    df["_next_season"] = df.groupby("Name")["Season"].shift(-1)
    df = df[df["_next_season"] == df["Season"] + 1].drop(columns="_next_season")

    df = df.sort_values(["Season", "Name"]).reset_index(drop=True)

    out = PROCESSED_DIR / "kbo_batters.csv"
    df.to_csv(out, index=False)
    print(f"Saved {len(df)} rows × {len(df.columns)} cols → {out}")
    return df


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-pa", type=int, default=MIN_PA)
    args = parser.parse_args()
    build(args.min_pa)
