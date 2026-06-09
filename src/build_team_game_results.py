"""
Build team-level game results from KBO schedule/results CSV.

Input:
    data/raw/kbo_official/kbo_schedule_<year>.csv

Outputs:
    data/processed/kbo_team_games_<year>.csv
    data/processed/kbo_team_monthly_<year>.csv

Usage:
    python src/build_team_game_results.py --year 2026
"""

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
RAW_DIR = ROOT / "data" / "raw" / "kbo_official"
PROCESSED_DIR = ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def _result_for(row: pd.Series, side: str) -> str:
    own = row[f"{side}_score"]
    opp = row["home_score"] if side == "away" else row["away_score"]
    if pd.isna(own) or pd.isna(opp):
        return ""
    if own > opp:
        return "W"
    if own < opp:
        return "L"
    return "D"


def _team_rows(game: pd.Series) -> list[dict]:
    if game.get("status") != "final":
        return []

    rows = []
    for side, opponent_side, home_away in [
        ("away", "home", "away"),
        ("home", "away", "home"),
    ]:
        team = game[f"{side}_team"]
        opponent = game[f"{opponent_side}_team"]
        if not team or not opponent:
            continue

        scored = game[f"{side}_score"]
        allowed = game[f"{opponent_side}_score"]
        result = _result_for(game, side)
        rows.append(
            {
                "Season": game["Season"],
                "Date": game["Date"],
                "Month": str(game["Date"])[5:7],
                "GameId": game["GameId"],
                "Team": team,
                "Opponent": opponent,
                "HomeAway": home_away,
                "Ballpark": game["Ballpark"],
                "RunsFor": int(scored),
                "RunsAgainst": int(allowed),
                "RunDiff": int(scored - allowed),
                "Result": result,
                "Win": 1 if result == "W" else 0,
                "Loss": 1 if result == "L" else 0,
                "Draw": 1 if result == "D" else 0,
            }
        )
    return rows


def build(year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    schedule_path = RAW_DIR / f"kbo_schedule_{year}.csv"
    if not schedule_path.exists():
        raise FileNotFoundError(f"Missing schedule CSV: {schedule_path}")

    schedule = pd.read_csv(schedule_path)
    final_games = schedule[
        (schedule["status"] == "final")
        & schedule["GameId"].notna()
        & schedule["away_score"].notna()
        & schedule["home_score"].notna()
    ].copy()

    records = []
    for _, game in final_games.iterrows():
        records.extend(_team_rows(game))

    team_games = pd.DataFrame(records)
    if team_games.empty:
        raise RuntimeError("No final team game rows found.")

    monthly = (
        team_games.groupby(["Season", "Month", "Team"], as_index=False)
        .agg(
            Games=("GameId", "count"),
            Wins=("Win", "sum"),
            Losses=("Loss", "sum"),
            Draws=("Draw", "sum"),
            RunsFor=("RunsFor", "sum"),
            RunsAgainst=("RunsAgainst", "sum"),
            RunDiff=("RunDiff", "sum"),
        )
    )
    monthly["WinRate"] = monthly["Wins"] / (monthly["Wins"] + monthly["Losses"])
    monthly["WinRate"] = monthly["WinRate"].fillna(0).round(3)

    team_games_out = PROCESSED_DIR / f"kbo_team_games_{year}.csv"
    monthly_out = PROCESSED_DIR / f"kbo_team_monthly_{year}.csv"
    team_games.to_csv(team_games_out, index=False, encoding="utf-8-sig")
    monthly.to_csv(monthly_out, index=False, encoding="utf-8-sig")
    print(f"saved {team_games_out.name} rows={len(team_games)}")
    print(f"saved {monthly_out.name} rows={len(monthly)}")
    return team_games, monthly


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2026)
    args = parser.parse_args()
    build(args.year)
