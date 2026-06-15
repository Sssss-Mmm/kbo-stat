"""
Build hitter metric dataset for dashboard and AI analysis.

Input:
    data/raw/kbo_official/kbo_<year>.csv

Output:
    data/processed/kbo_hitter_metrics_<year>.csv

Usage:
    python src/build_hitter_metrics.py --year 2026
"""

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
RAW_DIR = ROOT / "data" / "raw" / "kbo_official"
PROCESSED_DIR = ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def _num(series: pd.Series) -> pd.Series:
    """문자열/결측이 섞인 컬럼을 숫자로 강제 변환(변환 실패는 0)."""
    return pd.to_numeric(series, errors="coerce").fillna(0)


def build(year: int) -> pd.DataFrame:
    """원본 타자 CSV에서 OBP/SLG/OPS/WARProxy 파생지표를 계산해 저장한다."""
    source = RAW_DIR / f"kbo_{year}.csv"
    if not source.exists():
        raise FileNotFoundError(f"Missing hitter CSV: {source}")

    df = pd.read_csv(source)
    # 계산에 쓰는 컬럼이 없으면 0으로 채우고 모두 숫자형으로 정규화.
    for col in ["AB", "H", "2B", "3B", "HR", "BB", "HBP", "RBI", "AVG", "XR", "PA"]:
        if col not in df.columns:
            df[col] = 0
        df[col] = _num(df[col])

    # 누루타(TB) = 1루타 + 2*2루타 + 3*3루타 + 4*홈런, 분모 0은 NA 로 막아 0나눗셈 방지.
    singles = df["H"] - df["2B"] - df["3B"] - df["HR"]
    total_bases = singles + df["2B"] * 2 + df["3B"] * 3 + df["HR"] * 4
    obp_den = df["AB"] + df["BB"] + df["HBP"]

    metrics = pd.DataFrame(
        {
            "Season": year,
            "Rank": df.get("순위", ""),
            "Player": df.get("선수명", ""),
            "Team": df.get("팀명", ""),
            "PA": df["PA"],
            "AVG": df["AVG"],
            "OBP": (df["H"] + df["BB"] + df["HBP"]) / obp_den.replace(0, pd.NA),
            "SLG": total_bases / df["AB"].replace(0, pd.NA),
            "HR": df["HR"],
            "RBI": df["RBI"],
            "XR": df["XR"],
            "WARProxy": df["XR"] / 8,  # XR 8점 ≈ 1승 가정한 간이 WAR 근사치
        }
    )
    metrics["OPS"] = metrics["OBP"] + metrics["SLG"]
    for col in ["AVG", "OBP", "SLG", "OPS", "WARProxy"]:
        metrics[col] = metrics[col].astype(float).round(3)

    metrics = metrics.sort_values(["WARProxy", "OPS"], ascending=False)
    out = PROCESSED_DIR / f"kbo_hitter_metrics_{year}.csv"
    metrics.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"saved {out.name} rows={len(metrics)}")
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2026)
    args = parser.parse_args()
    build(args.year)
