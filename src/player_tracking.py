"""
KBO 선수 트래킹 CLI.

Usage:
    python player_tracking.py --search Park
    python player_tracking.py --name Park
    python player_tracking.py --name Park --season 2023
    python player_tracking.py --name Park --compare
    python player_tracking.py --name Park --season 2023 --compare --metric WAR
"""

import argparse
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from pathlib import Path

warnings.filterwarnings("ignore")

DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DIR  = DATA_DIR / "raw"
OUT_DIR  = DATA_DIR / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 한글 폰트 ────────────────────────────────────────────────────────────────

def _setup_font():
    for path in [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
    ]:
        if Path(path).exists():
            fm.fontManager.addfont(path)
            plt.rcParams["font.family"] = Path(path).stem
            break
    else:
        plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 120


# ── 데이터 로드 ───────────────────────────────────────────────────────────────

def load_data() -> pd.DataFrame:
    files = sorted(RAW_DIR.glob("kbo_*.csv"))
    if not files:
        raise FileNotFoundError(
            "데이터 없음. src/crawl.py 먼저 실행하세요.\n"
            f"  경로: {RAW_DIR}"
        )

    frames = []
    for f in files:
        df = pd.read_csv(f, dtype=str)
        if "Name" in df.columns:
            df["Name"] = (
                df["Name"]
                .str.replace(r"[฀-鿿가-힯]+", "", regex=True)
                .str.strip()
            )
        frames.append(df)

    df = pd.concat(frames, ignore_index=True)

    skip = {"Name", "Team", "PlayerName", "KName"}
    num_cols = [c for c in df.columns if c not in skip]
    df[num_cols] = df[num_cols].apply(pd.to_numeric, errors="coerce")
    df = df[df["PA"] >= 50].copy()
    return df


# ── 선수 검색 ─────────────────────────────────────────────────────────────────

def search_player(df: pd.DataFrame, query: str):
    show = ["Name", "Season", "Team", "PA", "AVG", "OBP", "SLG", "wRC+", "WAR"]
    show = [c for c in show if c in df.columns]
    result = (
        df[df["Name"].str.contains(query, case=False, na=False)][show]
        .drop_duplicates()
        .sort_values(["Name", "Season"])
    )
    if result.empty:
        print(f'"{query}"와 일치하는 선수가 없습니다.')
    else:
        print(result.to_string(index=False))


# ── 커리어 대시보드 ───────────────────────────────────────────────────────────

def player_dashboard(df: pd.DataFrame, name: str):
    p = df[df["Name"].str.contains(name, case=False, na=False)].sort_values("Season")
    if p.empty:
        print(f'"{name}" 선수를 찾을 수 없습니다. --search 로 먼저 확인하세요.')
        return

    display_name = p["Name"].iloc[0]
    seasons = p["Season"].values

    def pct_rank(col):
        out = []
        for _, row in p.iterrows():
            val = row[col]
            if pd.isna(val):
                out.append(np.nan)
                continue
            season_col = df.loc[df["Season"] == row["Season"], col].dropna()
            out.append((season_col < val).mean() * 100)
        return out

    fig, axes = plt.subplots(3, 2, figsize=(14, 12))
    fig.suptitle(f"{display_name} 커리어 트래킹", fontsize=16, fontweight="bold")

    # wRC+
    ax = axes[0, 0]
    if "wRC+" in p.columns:
        ax.plot(seasons, p["wRC+"], marker="o", color="#2196F3", linewidth=2.5, markersize=7, label="wRC+")
        ax.axhline(100, color="gray", linestyle="--", alpha=0.5, label="리그 평균(100)")
    ax.set_title("wRC+ 추이"); ax.set_xlabel("시즌"); ax.legend(); ax.grid(alpha=0.3)

    # AVG / OBP / SLG
    ax = axes[0, 1]
    for m, c in [("AVG", "#4CAF50"), ("OBP", "#FF9800"), ("SLG", "#E91E63")]:
        if m in p.columns:
            ax.plot(seasons, p[m], marker="o", linewidth=2.5, markersize=7, label=m, color=c)
    ax.set_title("타율/출루율/장타율"); ax.set_xlabel("시즌"); ax.legend(); ax.grid(alpha=0.3)

    # WAR
    ax = axes[1, 0]
    if "WAR" in p.columns:
        ax.bar(seasons, p["WAR"], color="#9C27B0", alpha=0.8)
    ax.set_title("WAR 추이"); ax.set_xlabel("시즌"); ax.set_ylabel("WAR"); ax.grid(alpha=0.3, axis="y")

    # PA
    ax = axes[1, 1]
    if "PA" in p.columns:
        ax.bar(seasons, p["PA"], color="#607D8B", alpha=0.8)
    ax.set_title("타석 수 (PA)"); ax.set_xlabel("시즌"); ax.set_ylabel("PA"); ax.grid(alpha=0.3, axis="y")

    # wRC+ 퍼센타일
    ax = axes[2, 0]
    if "wRC+" in p.columns:
        pct = pct_rank("wRC+")
        bar_colors = [
            "#F44336" if (v or 0) >= 90 else "#2196F3" if (v or 0) >= 50 else "#9E9E9E"
            for v in pct
        ]
        ax.bar(seasons, pct, color=bar_colors, alpha=0.85)
        ax.axhline(50, color="gray", linestyle="--", alpha=0.5)
        ax.set_ylim(0, 100)
    ax.set_title("wRC+ 리그 내 퍼센타일"); ax.set_xlabel("시즌"); ax.set_ylabel("%"); ax.grid(alpha=0.3, axis="y")

    # 스탯 테이블
    ax = axes[2, 1]
    ax.axis("off")
    show_cols = ["Season", "Team", "PA", "AVG", "OBP", "SLG", "wRC+", "WAR"]
    show_cols = [c for c in show_cols if c in p.columns]
    tbl_data = [
        [
            f"{v:.3f}" if isinstance(v, float) and 0 < abs(v) < 10
            else f"{v:.0f}" if isinstance(v, float)
            else str(v)
            for v in row
        ]
        for row in p[show_cols].tail(8).values.tolist()
    ]
    tbl = ax.table(cellText=tbl_data, colLabels=show_cols, loc="center", cellLoc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8.5)
    tbl.auto_set_column_width(list(range(len(show_cols))))
    ax.set_title("시즌별 스탯 요약")

    plt.tight_layout()
    out_path = OUT_DIR / f"{display_name.replace(' ', '_')}_dashboard.png"
    plt.savefig(out_path, bbox_inches="tight")
    plt.show()
    print(f"저장: {out_path}")


# ── 동료 비교 (레이더 차트) ───────────────────────────────────────────────────

def compare_with_peers(df: pd.DataFrame, name: str, season: int = None,
                       top_n: int = 10, metric: str = "wRC+"):
    p = df[df["Name"].str.contains(name, case=False, na=False)]
    if p.empty:
        print(f'"{name}" 선수를 찾을 수 없습니다.'); return

    if season is None:
        season = int(p["Season"].max())

    season_df = df[(df["Season"] == season) & (df["PA"] >= 200)].copy()
    player_row = season_df[season_df["Name"].str.contains(name, case=False, na=False)]
    if player_row.empty:
        print(f"{season}시즌에 {name} 데이터 없음 (PA 200 미만일 수 있음)"); return

    radar_cols = [c for c in ["AVG", "OBP", "SLG", "wRC+", "WAR", "BB%", "K%"] if c in season_df.columns]

    # 정규화
    norm = season_df[radar_cols].copy()
    for c in radar_cols:
        mn, mx = norm[c].min(), norm[c].max()
        norm[c] = (norm[c] - mn) / (mx - mn + 1e-9)
        if c == "K%":
            norm[c] = 1 - norm[c]

    angles = np.linspace(0, 2 * np.pi, len(radar_cols), endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(polar=True))

    avg_vals = norm[radar_cols].mean().tolist() + [norm[radar_cols].mean().iloc[0]]
    ax.plot(angles, avg_vals, color="gray", linewidth=1, linestyle="--", label="리그 평균")
    ax.fill(angles, avg_vals, alpha=0.05, color="gray")

    idx = player_row.index[0]
    p_vals = norm.loc[idx, radar_cols].tolist() + [norm.loc[idx, radar_cols[0]]]
    display_name = player_row["Name"].iloc[0]
    ax.plot(angles, p_vals, color="#2196F3", linewidth=2.5, label=display_name)
    ax.fill(angles, p_vals, alpha=0.2, color="#2196F3")

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(radar_cols, fontsize=11)
    ax.set_title(f"{display_name} vs 리그 ({season}시즌)", fontsize=13, fontweight="bold", pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))

    plt.tight_layout()
    out_path = OUT_DIR / f"{display_name.replace(' ', '_')}_{season}_radar.png"
    plt.savefig(out_path, bbox_inches="tight")
    plt.show()
    print(f"저장: {out_path}")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    _setup_font()

    parser = argparse.ArgumentParser(description="KBO 선수 트래킹")
    parser.add_argument("--search",  metavar="QUERY", help="선수 검색 (영문 이름 일부)")
    parser.add_argument("--name",    metavar="NAME",  help="선수 이름 (영문, 커리어 대시보드)")
    parser.add_argument("--season",  type=int,        help="비교 시즌 (기본: 최근 시즌)")
    parser.add_argument("--compare", action="store_true", help="레이더 차트로 리그 비교")
    parser.add_argument("--metric",  default="wRC+",  help="비교 기준 스탯 (기본: wRC+)")
    parser.add_argument("--top-n",   type=int, default=10, dest="top_n",
                        help="비교 상위 선수 수 (기본: 10)")
    args = parser.parse_args()

    if not args.search and not args.name:
        parser.print_help()
        return

    print("데이터 로딩 중 …")
    df = load_data()
    print(f"  {len(df)}행  {int(df['Season'].min())}~{int(df['Season'].max())}시즌\n")

    if args.search:
        search_player(df, args.search)

    if args.name:
        player_dashboard(df, args.name)
        if args.compare:
            compare_with_peers(df, args.name, args.season, args.top_n, args.metric)


if __name__ == "__main__":
    main()
