"""
자체 계산 선수-경기 기록(build_player_games)을 네이버 박스스코어(build_naver_box_games)와 대조한다.

    data/processed/kbo_player_games_check_{season}.csv    (경기, 역할, 선수, 항목) 1행
    data/processed/kbo_outs_uncertain_{season}.csv        아웃 미확정 투수-경기와 사유·대조 결과
    data/processed/kbo_verify_exceptions_{season}.csv     예외 사례(자동 고의4구·콜드·무승부·대주자 등) 종류별 목록

어느 쪽 값도 고치지 않는다. 대조 결과는 별도 파일에만 남긴다. 박스스코어가 있는 경기만 대조한다.

Status (네이버 대조임을 이름에 박는다 — KBO 공식 사이트 대조는 kbo_* 로 따로 만든다):
  observed_naver_match     투구 데이터로 입증된 값(CalcProven)이 네이버와 같다
  observed_naver_conflict  입증된 값이 네이버와 다르다 — 계산 버그나 원본 오류, 조사 대상
  naver_verified           입증 못 한 계산값(아웃은 근거 없이 채운 _OutsRaw)이 네이버와 같다
  naver_conflict           입증 못 한 계산값이 네이버와 다르다
  naver_unusable           그 항목의 네이버 선수 합계가 팀 합계와 어긋나 기준으로 못 쓴다
  calc_missing             네이버에는 있는데 계산값이 없다(투구 원본에 없음 등)
  naver_missing            계산값은 있는데 네이버 박스스코어에 그 선수가 없다
naver_verified 는 '네이버와 일치'일 뿐 KBO 공식 확인이 아니다. Outs/OutsComplete 는 그대로다.

Usage:
    python src/verify_player_games.py --season 2025
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

import pandas as pd

import build_player_games as bpg
import csv_guard
from build_zone_metrics import PROCESSED_DIR, ensure_teams

EXTERNAL = "naver_boxscore"
# (계산 열, 네이버 열, 입증 플래그 열, 팀 합계 검사 항목)
PITCHER_METRICS = [("Outs", "Outs", "OutsComplete", "Outs"), ("BF", "BF", "PAComplete", "BF"),
                   ("H", "H", "StatsComplete", "H"), ("BB", "BB", "StatsComplete", None),
                   ("BBHP", "BBHP", "StatsComplete", "BBHP"), ("SO", "SO", "StatsComplete", "SO")]
BATTER_METRICS = [("AB", "AB", "StatsComplete", "AB"), ("H", "H", "StatsComplete", "H"),
                  ("HR", "HR", "StatsComplete", None), ("BB", "BB", "StatsComplete", None),
                  ("SO", "SO", "StatsComplete", None)]
CHECK_COLUMNS = ["Season", "GameId", "Role", "PlayerId", "Player", "Metric", "CalcValue", "CalcProven",
                 "ExternalValue", "ExternalSource", "ExternalFetchedAt", "ExternalRawFile", "Status", "CalcRule", "CheckedAt"]


def status(calc, proven: bool, external, usable: bool) -> str:
    if pd.isna(external):
        return "naver_missing"
    if pd.isna(calc):
        return "calc_missing"
    if not usable:
        return "naver_unusable"
    same = int(calc) == int(external)
    if proven:
        return "observed_naver_match" if same else "observed_naver_conflict"
    return "naver_verified" if same else "naver_conflict"


def compare(games: pd.DataFrame, raw_outs: pd.Series, box: pd.DataFrame, role: str) -> pd.DataFrame:
    """한 역할의 계산 표 vs 네이버 표 → 항목별 대조 행. 박스스코어가 있는 경기만."""
    metrics = PITCHER_METRICS if role == "pitcher" else BATTER_METRICS
    calc = games[(games["Role"] == role) & games["GameId"].isin(box["GameId"])].copy()
    if role == "pitcher":
        calc["BBHP"] = calc["BB"] + calc["HBP"]
        calc["OutsRaw"] = calc.set_index(["GameId", "PlayerId"]).index.map(raw_outs)
    ext = box.copy()
    raw_of = box.drop_duplicates("GameId").set_index("GameId")[["FetchedAt", "RawFile"]]
    joined = calc.merge(ext, on=["GameId", "PlayerId"], how="outer", suffixes=("", "_ext"), indicator=True)
    joined["Player"] = joined["Player"].fillna(joined["Player_ext"])
    rows = []
    for col, ext_col, flag, team_col in metrics:
        value = joined["OutsRaw"].where(~joined["OutsComplete"].fillna(False).astype(bool), joined["Outs"]) \
            if col == "Outs" else joined[col]
        ext_value = joined[f"{ext_col}_ext"]
        proven = joined[flag].fillna(False).astype(bool)
        usable = ~joined["TeamSumMismatch"].fillna("").astype(str).str.split(",").map(lambda bad: team_col in bad)
        rows.append(pd.DataFrame({
            "GameId": joined["GameId"], "Role": role, "PlayerId": joined["PlayerId"], "Player": joined["Player"],
            "Metric": col, "CalcValue": value, "CalcProven": proven & joined["_merge"].ne("right_only"),
            "ExternalValue": ext_value,
            # 그 경기 박스스코어 원본 — 네이버에 없는 선수 행도 어느 원본과 대조했는지 남긴다.
            "ExternalFetchedAt": joined["GameId"].map(raw_of["FetchedAt"]),
            "ExternalRawFile": joined["GameId"].map(raw_of["RawFile"]),
            "Status": [status(c, p, e, u) for c, p, e, u in zip(value, proven, ext_value, usable)],
        }))
    return pd.concat(rows, ignore_index=True)


def uncertain_outs(df: pd.DataFrame, games: pd.DataFrame, checks: pd.DataFrame) -> pd.DataFrame:
    """OutsComplete=False 투수-경기마다 믿지 못한 반이닝·사유·마지막 문구·네이버 대조 결과."""
    half = ["GameId", "Inning", "HomeAway"]
    bad = df[~df["_HalfOk"]]
    last = bad.groupby(half, sort=False).tail(1).set_index(half)
    pitched = bad[[*half, "PitcherId"]].drop_duplicates().join(last[["_HalfReason", "AtBatText", "Out"]], on=half)
    pitched["Half"] = pitched["Inning"].astype(str) + pitched["HomeAway"].map({0: "T", 1: "B"})
    agg = pitched.groupby(["GameId", "PitcherId"]).agg(
        Halves=("Half", ",".join), Reasons=("_HalfReason", lambda s: ",".join(dict.fromkeys(s))),
        LastResults=("AtBatText", lambda s: " | ".join(s.fillna("").astype(str))),
        LastOuts=("Out", lambda s: ",".join(str(int(o)) for o in s)),
    ).rename_axis(["GameId", "PlayerId"])
    pitchers = games[(games["Role"] == "pitcher") & ~games["OutsComplete"].astype(bool)]
    out = pitchers[["Season", "Date", "GameId", "PlayerId", "Player", "Team"]].join(agg, on=["GameId", "PlayerId"])
    outs_check = checks[(checks["Role"] == "pitcher") & (checks["Metric"] == "Outs")].set_index(["GameId", "PlayerId"])
    out = out.join(outs_check[["CalcValue", "ExternalValue", "Status", "ExternalFetchedAt", "ExternalRawFile"]],
                   on=["GameId", "PlayerId"])
    out = out.rename(columns={"CalcValue": "OutsRaw", "ExternalValue": "NaverOuts", "Status": "NaverStatus"})
    out["NaverStatus"] = out["NaverStatus"].fillna("unverified")  # 박스스코어를 아직 안 받은 경기
    return out.reset_index(drop=True)


EXCEPTION_COLUMNS = ["Season", "GameId", "Kind", "Role", "PlayerId", "Player", "Count", "Detail"]
# 박스스코어 타순표 포지션 → 타석 없이 출전한 사유
SUB_KINDS = (("주", "pinch_runner"), ("타", "pinch_hitter_no_pa"), ("투", "pitcher_batting_slot"))


def exceptions(df: pd.DataFrame, games: pd.DataFrame, checks: pd.DataFrame, box_p: pd.DataFrame,
               box_b: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    """공식(네이버) 기록과 자체 계산이 갈리거나 비교가 안 되는 알려진 사례를 종류(Kind)별로 한 줄씩 남긴다.
    값은 고치지 않는다 — 사유 집계용이다.

    경기: no_boxscore · no_pitch_data · tie · walkoff · called_game(정규 이닝 전 또는 이닝 도중 종료) · team_sum_mismatch
    선수: auto_ibb_no_pitch(박스 '고4' − 투구 데이터의 고의4구 타석) · pinch_runner · pinch_hitter_no_pa ·
          pitcher_batting_slot · defensive_sub(타석 없이 출전) · pitcher_no_pitch(상대 타자 0) ·
          no_pitch_rows(타석·상대 타자가 있는데 투구 행 없음) ·
          not_in_boxscore(계산엔 있는데 박스에 없음) · observed_conflict_auto_ibb / observed_conflict_other
    """
    rows = []

    def add(kind, frame, role="", count=1, detail=""):
        plain = lambda v: v.values if isinstance(v, pd.Series) else v  # noqa: E731 — 인덱스 정렬 없이 순서대로
        rows.append(pd.DataFrame({
            "GameId": frame["GameId"].values, "Kind": kind, "Role": plain(role),
            "PlayerId": frame["PlayerId"].values if "PlayerId" in frame else pd.NA,
            "Player": frame["Player"].values if "Player" in frame else "",
            "Count": plain(count), "Detail": plain(detail)}))

    final = schedule[schedule["status"].eq("final")].dropna(subset=["GameId"]).assign(
        GameId=lambda s: s["GameId"].astype(str)).set_index("GameId")
    boxed = final[final.index.isin(box_p["GameId"])]
    add("no_boxscore", final[~final.index.isin(box_p["GameId"])].reset_index())
    add("no_pitch_data", final[~final.index.isin(df["GameId"])].reset_index())
    outs = box_p.groupby(["GameId", "Side"])["Outs"].sum().unstack().reindex(boxed.index)
    home_outs, away_outs = outs.get("home"), outs.get("away")  # 홈 투수 아웃 = 원정 공격(초) 이닝
    home_won = boxed["home_score"] > boxed["away_score"]
    walkoff = home_won & away_outs.mod(3).ne(0) & home_outs.ge(27)
    called = home_outs.lt(27) | home_outs.mod(3).ne(0) | (away_outs.mod(3).ne(0) & ~walkoff)
    detail = "home_pitching_outs=" + home_outs.astype("Int64").astype(str) + " away_pitching_outs=" + \
        away_outs.astype("Int64").astype(str)
    add("tie", boxed[boxed["home_score"].eq(boxed["away_score"])].reset_index())
    add("walkoff", boxed[walkoff].reset_index(), detail=detail[walkoff])
    add("called_game", boxed[called].reset_index(), detail=detail[called])
    for role, box in (("pitcher", box_p), ("batter", box_b)):
        bad = box[box["TeamSumMismatch"].ne("")].drop_duplicates(["GameId", "Side"])
        add("team_sum_mismatch", bad, role, detail=bad["Side"] + ":" + bad["TeamSumMismatch"])

    pa = bpg.plate_appearances(df)
    calc_ibb = pa[pa["Category"].eq("BB") & pa["AtBatText"].fillna("").str.contains("고의4구")] \
        .groupby(["GameId", "ChargedBatter"]).size()
    box_ibb = box_b.set_index(["GameId", "PlayerId"])["IBB"]
    gap = (box_ibb - calc_ibb.rename_axis(["GameId", "PlayerId"]).reindex(box_ibb.index).fillna(0)).astype(int)
    hit = box_b.set_index(["GameId", "PlayerId"]).loc[gap[gap > 0].index].reset_index()
    add("auto_ibb_no_pitch", hit, "batter", count=gap[gap > 0].reset_index(drop=True))

    for role, box, active in (("batter", box_b, box_b["AB"].add(box_b["BB"]).gt(box_b["IBB"])),
                              ("pitcher", box_p, box_p["BF"].gt(0))):
        known = games[games["Role"] == role].set_index(["GameId", "PlayerId"]).index
        absent = ~box.set_index(["GameId", "PlayerId"]).index.isin(known)
        missing = box[absent & active.values]
        add("no_pitch_rows", missing, role, detail=missing["BF" if role == "pitcher" else "AB"].map(
            lambda n: f"{'BF' if role == 'pitcher' else 'AB'}={n}"))
        if role == "pitcher":
            add("pitcher_no_pitch", box[absent & ~active.values], role)  # 박스엔 있는데 상대 타자 0(공 안 던짐)
        if role == "batter":
            idle = box[absent & ~active.values & box["IBB"].eq(0).values]
            pos = idle["Pos"].fillna("").astype(str)
            kind = pd.Series("defensive_sub", index=idle.index)
            for prefix, name in SUB_KINDS:
                kind[pos.str.startswith(prefix)] = name
            for name in kind.unique():
                sel = idle[kind.eq(name)]
                add(name, sel, role, detail=sel["Pos"].fillna("").astype(str))
    lone = checks[checks["Status"].eq("naver_missing")].drop_duplicates(["GameId", "Role", "PlayerId"])
    for role in ("batter", "pitcher"):
        sel = lone[lone["Role"].eq(role)]
        add("not_in_boxscore", sel, role)
    conflict = checks[checks["Status"].eq("observed_naver_conflict")]
    ibb_games = set(hit["GameId"])
    for kind, sel in (("observed_conflict_auto_ibb", conflict[conflict["GameId"].isin(ibb_games)]),
                      ("observed_conflict_other", conflict[~conflict["GameId"].isin(ibb_games)])):
        add(kind, sel, sel["Role"], detail=sel["Metric"] + " calc=" + sel["CalcValue"].astype(str) +
            " naver=" + sel["ExternalValue"].astype(str))
    out = pd.concat(rows, ignore_index=True)
    out["Role"] = out["Role"].astype(str)
    return out.astype({"PlayerId": "Int64", "Count": int})


def build_checks(season: int, pitches: pd.DataFrame, schedule: pd.DataFrame,
                 box_pitchers: pd.DataFrame, box_batters: pd.DataFrame
                 ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    # ponytail: build_frame 이 같은 전처리를 한 번 더 돈다(2025 약 10초). 느려지면 build_frame 이 df 를 돌려주게.
    df = bpg.pitch_outs(bpg.order_plate_appearances(bpg.regular_season(ensure_teams(pitches), schedule)))
    games = bpg.build_frame(pitches, schedule)
    raw_outs = df.groupby(["GameId", "PitcherId"])["_OutsRaw"].sum(min_count=1)
    raw_outs = raw_outs.where(df.groupby(["GameId", "PitcherId"])["_OutsRaw"].apply(lambda s: s.notna().all()))
    checks = pd.concat([compare(games, raw_outs, box_pitchers, "pitcher"),
                        compare(games, raw_outs, box_batters, "batter")], ignore_index=True)
    checks = checks.assign(Season=season, ExternalSource=EXTERNAL, CalcRule=bpg.calc_rule(),
                           CheckedAt=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    checks = checks.astype({"PlayerId": int, "CalcValue": "Int64", "ExternalValue": "Int64"})[CHECK_COLUMNS]
    stamp = checks[["CalcRule", "CheckedAt"]].iloc[0].to_dict() if len(checks) else {}
    found = exceptions(df, games, checks, box_pitchers, box_batters, schedule).assign(Season=season, **stamp)
    return checks, uncertain_outs(df, games, checks).assign(**stamp), found[[*EXCEPTION_COLUMNS, *stamp]]


def build(season: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    box_p = pd.read_csv(PROCESSED_DIR / f"naver_box_pitchers_{season}.csv", encoding="utf-8-sig", keep_default_na=False,
                        na_values=[""]).fillna({"TeamSumMismatch": ""})
    box_b = pd.read_csv(PROCESSED_DIR / f"naver_box_batters_{season}.csv", encoding="utf-8-sig", keep_default_na=False,
                        na_values=[""]).fillna({"TeamSumMismatch": ""})
    checks, uncertain, found = build_checks(season, bpg.load_season_pitches(season), bpg.load_schedule(season),
                                            box_p, box_b)
    counts = checks["Status"].value_counts().to_dict()
    csv_guard.save_csv(checks, PROCESSED_DIR / f"kbo_player_games_check_{season}.csv", prefix="[verify]",
                       extra=" ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    csv_guard.save_csv(uncertain, PROCESSED_DIR / f"kbo_outs_uncertain_{season}.csv", prefix="[verify]",
                       extra=" ".join(f"{k}={v}" for k, v in sorted(uncertain["NaverStatus"].value_counts().items())))
    csv_guard.save_csv(found, PROCESSED_DIR / f"kbo_verify_exceptions_{season}.csv", prefix="[verify]", allow_empty=True,
                       extra=" ".join(f"{k}={v}" for k, v in sorted(found.groupby("Kind")["Count"].sum().items())))
    return checks, uncertain, found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    build(parser.parse_args().season)


if __name__ == "__main__":
    main()
