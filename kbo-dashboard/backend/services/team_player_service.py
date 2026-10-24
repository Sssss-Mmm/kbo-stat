"""P2-D — 팀 상세 · 선수 검색 · 선수 시즌별 기록(비교용). 새 테이블 없이 기존 자료를 묶는다.

- 선수 ID 가 있는 자료: 네이버 시즌 기록 CSV(data/processed/kbo_naver_{hitters,pitchers}_{시즌}.csv, 2007–2026)와
  KBO 등록선수 명단 스냅샷(data/raw/kbo_official/kbo_registered_players_*.csv, 2026-06~10 — 생년월일·투타).
  둘 다 같은 KBO 선수 ID 를 쓴다. 동명이인은 이 ID 로 가른다.
- 팀 기록·최근 경기·홈/원정은 P2-C 순위·일정 서비스(season_service)를 그대로 쓴다(2001–2026).
- 선수 ID 가 없는 시즌(2001–2006)의 팀 선수는 v1 규정 이상 기록(public.hitters/pitchers)만 있다 — 이름만, 상세 링크 없음.
- 없는 값은 None(0 으로 채우지 않는다). 자료 출처·수집 시각을 응답에 붙인다.
"""
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import pandas as pd
from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError

from services import batting_advanced as ba
from services import season_service as ss
from services.v2_service import _rows, pick_build
from utils import PROCESSED_DIR

RAW_DIR = PROCESSED_DIR.parent / "raw" / "kbo_official"
NAVER = {"batter": "kbo_naver_hitters_{season}.csv", "pitcher": "kbo_naver_pitchers_{season}.csv"}
STATS = {"batter": ["G", "AVG", "AB", "H", "2B", "3B", "HR", "RBI", "R", "SB", "BB", "HBP", "SO", "OBP", "SLG", "OPS",
                    "ISO", "BABIP", "wOBA", "wRC+", "WPA", "WAR"],
         "pitcher": ["G", "W", "L", "SV", "HLD", "IP", "ERA", "SO", "H", "HR", "R", "ER", "BB", "HBP", "WHIP", "QS",
                     "K/9", "BB/9", "K/BB", "WPA", "WAR"]}
NAVER_NOTE = "네이버 스포츠 시즌 기록 자동 수집 — KBO 원본과 직접 대조하지 않음, 이용 권한 확인 전(비공개)"
REGISTRY_NOTE = "KBO 등록선수 명단 자동 수집 스냅샷(2026 시즌 일부 날짜) — 생년월일·투타만 사용"
KEY_PLAYERS = 3
RECENT_GAMES = 10


def _clean(v):
    """NaN·빈 문자열 → None. numpy 수 → 파이썬 수."""
    if v is None or (isinstance(v, float) and v != v) or v == "":
        return None
    return v.item() if hasattr(v, "item") else v


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _key(paths: list[Path]) -> tuple:
    """파일 이름·수정 시각 — 캐시 키. 일일 갱신으로 파일이 바뀌면 다시 읽는다."""
    return tuple((str(p), p.stat().st_mtime_ns) for p in paths if p.exists())


def _read(path: str) -> list[dict]:
    df = pd.read_csv(path, encoding="utf-8-sig", dtype={"PlayerId": "Int64", "등번호": str})
    return [{k: _clean(v) for k, v in r.items()} for r in df.astype(object).to_dict("records")]


def naver_seasons() -> list[int]:
    return sorted({int(p.stem.rsplit("_", 1)[1]) for p in PROCESSED_DIR.glob("kbo_naver_hitters_*.csv")})


def _naver_paths(season: int) -> list[Path]:
    return [PROCESSED_DIR / NAVER[r].format(season=season) for r in ("batter", "pitcher")]


FIELDERS = ("내야수", "외야수", "포수")


def _is_pitcher_batting(line: dict, pitching_games: int | None) -> bool:
    """투구 기록도 있는 선수의 타자 줄이 '투수의 타석'인가. 야수 포지션이면 아니다, '투수'면 맞다.
    포지션이 비었거나 다른 값이면(2007–2023 은 대부분 빈칸) 경기 수로 가른다 — 타격 경기 ≤ 투구 경기면 투수.
    (2007–2026 확인: 빈칸 763행 중 753행은 타격 경기 ≤ 투구 경기·AB 0–3, 10행은 투구 1–3경기의 야수·AB 17–540.)"""
    if line["position"] in FIELDERS:
        return False
    if line["position"] == "투수":
        return True
    return (line["stats"]["G"] or 0) <= (pitching_games or 0)


@lru_cache(maxsize=64)
def _season_lines(season: int, key: tuple) -> tuple[dict, ...]:
    """한 시즌 타자·투수 줄. 투수의 타석(_is_pitcher_batting)인 타자 줄은 뺀다 — 투수로 한두 번 나온 야수의 타격 기록은 남긴다."""
    lines = []
    for role, (path, _) in zip(("batter", "pitcher"), key):
        lines += [{"player_id": r["PlayerId"], "name": r["선수명"], "season": season, "role": role, "team": r["팀명"],
                   "position": r["포지션"], "back_no": r["등번호"], "qualified": r["규정충족"],
                   "stats": {k: r.get(k) for k in STATS[role]}} for r in _read(path) if r["PlayerId"] is not None]
    pitching_games = {x["player_id"]: x["stats"]["G"] for x in lines if x["role"] == "pitcher"}
    return tuple(x for x in lines if x["role"] == "pitcher" or x["player_id"] not in pitching_games
                 or not _is_pitcher_batting(x, pitching_games[x["player_id"]]))


def naver_lines(season: int, role: str | None = None) -> list[dict]:
    key = _key(_naver_paths(season))
    if len(key) < 2:  # 타자·투수 파일이 다 있어야 투수 타석을 가를 수 있다
        return []
    return [x for x in _season_lines(season, key) if role in (None, x["role"])]


def naver_source(season: int, role: str) -> dict | None:
    path = PROCESSED_DIR / NAVER[role].format(season=season)
    return {"source": "naver_season_stats", "season": season, "role": role, "file": path.name,
            "collected_at": _mtime_iso(path), "note": NAVER_NOTE} if path.exists() else None


@lru_cache(maxsize=4)
def _registry(key: tuple) -> dict:
    out = {}
    for path, _ in key:  # 날짜 순 — 뒤가 이긴다
        for r in _read(path):
            out[int(r["PlayerId"])] = {"birth_date": r["BirthDate"], "pitch_bat": r["PitchBat"], "roster_date": r["RosterDate"]}
    return out


def registry() -> dict[int, dict]:
    """선수 ID → 생년월일·투타(가장 늦은 스냅샷 값). 명단에 없는 선수는 빠진다."""
    return _registry(_key(sorted(RAW_DIR.glob("kbo_registered_players_2*.csv"))))


def _all_lines(season: int | None = None, role: str | None = None) -> list[dict]:
    return [line for s in naver_seasons() if season in (None, s) for line in naver_lines(s, role)]


def _norm(name: str) -> str:
    return "".join((name or "").split())


def search(q: str | None, team: str | None, season: int | None, role: str | None, limit: int = 100) -> dict:
    """이름(공백 무시, 부분 일치)·팀·시즌·역할로 선수를 찾는다. 같은 ID 의 시즌·역할 기록은 한 사람으로 묶는다.
    same_name = 전체 자료에서 같은 이름을 쓰는 다른 선수 ID 수(동명이인 표시)."""
    every = _all_lines()
    ids_by_name: dict[str, set] = {}
    for line in every:
        ids_by_name.setdefault(_norm(line["name"]), set()).add(line["player_id"])
    key = _norm(q)
    hits = [line for line in _all_lines(season, role)
            if (not key or key in _norm(line["name"])) and (not team or line["team"] == team)]
    people: dict[int, dict] = {}
    for line in sorted(hits, key=lambda x: -x["season"]):
        p = people.setdefault(line["player_id"], {"player_id": line["player_id"], "name": line["name"], "seasons": []})
        p["seasons"].append({k: line[k] for k in ("season", "role", "team", "position", "back_no")} | {"games": line["stats"]["G"]})
    reg = registry()
    for p in people.values():
        p.update(reg.get(p["player_id"], {"birth_date": None, "pitch_bat": None, "roster_date": None}))
        p["same_name"] = len(ids_by_name[_norm(p["name"])]) - 1
        p["latest_season"] = p["seasons"][0]["season"]
    ranked = sorted(people.values(), key=lambda p: (_norm(p["name"]) != key, -p["latest_season"], p["name"], p["player_id"]))
    seasons = naver_seasons()
    return {"data": ranked[:limit], "total": len(ranked), "truncated": len(ranked) > limit,
            "coverage": {"seasons": seasons, "note": "선수 ID 가 있는 자료(네이버 시즌 기록)만 검색한다 — 그 이전 시즌은 이름·팀만 있어 동명이인을 가를 수 없다"},
            "meta": {"sources": [s for x in seasons for r in ("batter", "pitcher") if (s := naver_source(x, r))]
                     + [{"source": "kbo_registered_players", "note": REGISTRY_NOTE}]}}


def profile(player_id: int, engine=None) -> dict | None:
    """한 선수의 시즌·역할별 네이버 시즌 기록(비교·상세용). 없으면 None.
    engine 을 주면 타자 시즌 줄에 P3-A 고급 지표(`advanced`)를 붙인다 — 기존 키는 그대로, 투수 줄에는 붙이지 않는다."""
    lines = [line for line in _all_lines() if line["player_id"] == player_id]
    if not lines:
        return None
    lines.sort(key=lambda x: (-x["season"], x["role"]))
    latest = lines[0]
    identity = {"player_id": player_id, "name": latest["name"], "team": latest["team"], "position": latest["position"],
                **registry().get(player_id, {"birth_date": None, "pitch_bat": None, "roster_date": None})}
    meta = {"sources": [naver_source(x["season"], x["role"]) for x in lines]
            + ([{"source": "kbo_registered_players", "note": REGISTRY_NOTE}] if identity["roster_date"] else [])}
    batting = sorted({x["season"] for x in lines if x["role"] == "batter"})
    if engine is not None and batting:
        ctx = batting_context(engine, batting, player_id)
        advanced = {s: season_advanced(s, ctx, only=player_id) for s in batting}
        # 캐시된 줄을 고치지 않도록 복사해서 붙인다
        lines = [dict(x) | {"advanced": advanced[x["season"]].get(player_id)} if x["role"] == "batter" else x
                 for x in lines]
        meta |= {"advanced": advanced_meta(ctx)}
    return {"data": {"player": identity, "seasons": lines}, "meta": meta}


# ---------------------------------------------------------------- P3-A 타자 고급 지표(services/batting_advanced.py)

ADVANCED_RULES = {
    "iso": "(2B + 2·3B + 3·HR) / AB — 개수 기반 정확 계산. 네이버 ISO 는 '반올림 SLG − 반올림 AVG' 라 표시값이 0.001 다를 수 있다",
    "babip": "(H − HR) / (AB − SO − HR + SF) — SF 는 투구 데이터 계산에만 있어, 시즌 전 경기가 완결된 선수만 직접 계산",
    "babip_source": "네이버가 준 BABIP — 직접 계산 아님. 분모 0 가능 행의 0.000 은 쓰지 않는다",
    "bb_pct": "BB / PA × 100", "k_pct": "SO / PA × 100",
    "pa": "① KBO 기록실 PA(선수 ID 1:1 연결·BB·SO 일치) ② 조립 PA = AB + BB + HBP + SF + SH(투구 계산 완결 선수) ③ 없으면 계산하지 않음",
    "display": "ROUND_HALF_UP — ISO·BABIP 소수 3자리, BB%·K% 소수 1자리. value 는 반올림 전 정밀값",
    "status": "calculated · source · unavailable · zero_denominator — 계산할 수 없으면 0 이 아니라 null + reason",
}


def _id_row(line: dict) -> dict:
    """네이버 시즌 줄 → 계산 모듈 입력(행 키)."""
    return {"Season": line["season"], "PlayerId": line["player_id"], "선수명": line["name"], "팀명": line["team"],
            **line["stats"]}


def batting_context(engine, seasons: list[int], player_id: int | None = None) -> dict:
    """시즌들의 KBO 기록실 행(규정 이상)과 투구 계산 시즌 합을 읽는다. 쿼리 수는 시즌 수에만 비례(선수 수와 무관).
    DB 를 못 읽으면 그 부분은 빈 자료 + 경고 — 응답 전체를 실패시키지 않는다."""
    ctx = {"seasons": seasons, "kbo": {s: [] for s in seasons}, "calc": {s: {} for s in seasons}, "builds": {}, "warnings": []}
    try:
        with engine.connect() as conn:
            q = text("""SELECT h.season AS "Season", h.player_name AS "선수명", t.name AS "팀명", h.pa AS "PA", h.ab AS "AB",
                              h.hits AS "H", h.bb AS "BB", h.so AS "SO", h.hbp AS "HBP"
                       FROM hitters h JOIN teams t ON t.id = h.team_id WHERE h.season IN :seasons""")
            for r in conn.execute(q.bindparams(bindparam("seasons", expanding=True)), {"seasons": seasons}).mappings():
                ctx["kbo"][r["Season"]].append(dict(r))
    except SQLAlchemyError as exc:
        ctx["warnings"].append(f"KBO 기록실 PA 를 읽지 못함({type(exc).__name__}) — BB%·K% 는 조립 PA 만 사용")
    try:
        with engine.connect() as conn:
            for s in seasons:
                build = pick_build(conn, "player_game", s, None)
                if build is None:
                    continue
                ctx["builds"][s] = build
                who = "AND player_id = :pid" if player_id is not None else ""
                q = text(f"""SELECT player_id, COUNT(*) AS games,
                                      SUM(CASE WHEN stats_complete THEN 1 ELSE 0 END) AS complete_games,
                                      SUM(ab) AS "AB", SUM(hbp) AS "HBP", SUM(sf) AS "SF", SUM(sh) AS "SH"
                               FROM derived.player_game WHERE build_id = :b AND role = 'batter' {who}
                               GROUP BY player_id""")
                for r in conn.execute(q, {"b": build["build_id"], "pid": player_id}).mappings():
                    ctx["calc"][s][int(r["player_id"])] = {k: r[k] for k in ("games", "complete_games", "AB", "HBP", "SF", "SH")}
    except SQLAlchemyError as exc:
        ctx["warnings"].append(f"투구 계산 자료를 읽지 못함({type(exc).__name__}) — BABIP 직접 계산·조립 PA 불가")
    return ctx


def season_advanced(season: int, ctx: dict, only: int | None = None) -> dict[int, dict]:
    """한 시즌 타자의 고급 지표 {player_id: {...}}. 선수 연결은 늘 시즌 전체로 판정한다(필터 전에 — 유일성 보장).
    only 를 주면 지표는 그 선수만 계산한다(프로필)."""
    id_rows = [_id_row(line) for line in naver_lines(season, "batter")]
    kbo_rows = ctx["kbo"].get(season, [])
    links = ba.link_kbo_records(kbo_rows, id_rows, season)
    by_pid = {lk["player_id"]: (kbo_rows[lk["index"]], lk) for lk in links if lk["player_id"] is not None}
    out = {}
    for r in id_rows:
        pid = r["PlayerId"]
        if only is not None and pid != only:
            continue
        kbo_row, link = by_pid.get(pid, (None, None))
        res = ba.player_season(r, season, kbo_row=kbo_row, link=link, calc=ctx["calc"].get(season, {}).get(pid))
        out[pid] = {"pa": res["pa"],
                    "kbo_record_link": {"status": link["status"], "reason": link["reason"]} if link
                    else {"status": "not_listed", "reason": "KBO 기록실(규정 이상) 명단에 연결되는 행 없음"},
                    "metrics": {k: res[k] for k in ("iso", "babip", "babip_source", "bb_pct", "k_pct")}}
    return out


def advanced_meta(ctx: dict) -> dict:
    sources = [{"source": "kbo_record_season", "note": "KBO 기록실 시즌 기록(규정 이상, v1 적재) — PA 출처",
                "seasons": [s for s in ctx["seasons"] if ctx["kbo"].get(s)]}]
    sources += [{"source": "pitch_relay_calc", "season": s, "build_id": b["build_id"], "calc_rule": b["calc_rule"],
                 "note": "투구 데이터 계산 경기 기록의 시즌 합 — SF·SH 출처"} for s, b in sorted(ctx["builds"].items())]
    return {"rules": ADVANCED_RULES, "sources": sources, "warnings": ctx["warnings"],
            "publication": "private_pending_rights"}


def batting_advanced_list(engine, season: int, team: str | None, qualified: bool | None, limit: int, offset: int) -> dict:
    """GET /api/v2/batting/advanced — 시즌 타자 전원의 원본 기록·PA·고급 지표. 정렬: AB 내림차순, 같으면 player_id."""
    lines = naver_lines(season, "batter")
    if not lines:
        return {"data": [], "season": season, "reason": "no_batting_data",
                "page": {"limit": limit, "offset": offset, "total": 0, "next_offset": None},
                "meta": {"rules": ADVANCED_RULES, "sources": [], "warnings": [], "publication": "private_pending_rights"}}
    ctx = batting_context(engine, [season])
    advanced = season_advanced(season, ctx)
    rows = [x for x in lines if (not team or x["team"] == team) and (qualified is None or x["qualified"] is qualified)]
    rows.sort(key=lambda x: (-(x["stats"]["AB"] or 0), x["player_id"]))
    page = rows[offset:offset + limit]
    data = [{"player_id": x["player_id"], "name": x["name"], "team": x["team"], "season": season,
             "position": x["position"], "qualified": x["qualified"],
             "record": {"source": "naver_season_stats", **{k: x["stats"][k] for k in ("G", "AB", "H", "2B", "3B", "HR", "BB", "HBP", "SO")}},
             **advanced[x["player_id"]]} for x in page]
    counts: dict[str, dict[str, int]] = {}
    for x in rows:
        for k, m in advanced[x["player_id"]]["metrics"].items():
            counts.setdefault(k, {}).setdefault(m["status"], 0)
            counts[k][m["status"]] += 1
    meta = advanced_meta(ctx)
    meta["sources"].insert(0, naver_source(season, "batter"))
    return {"data": data, "season": season, "reason": None, "status_counts": counts,
            "page": {"limit": limit, "offset": offset, "total": len(rows),
                     "next_offset": offset + limit if offset + limit < len(rows) else None},
            "meta": meta}


def _team_games(conn, team: str, season: int) -> list[dict]:
    build = ss._schedule_build(conn, season)
    if build is None:
        return []
    rows = ss._schedule_rows(conn, build["build_id"], "AND (away_team = :t OR home_team = :t) AND status IN ('final', 'tie')",
                             {"t": team})
    # 순위 계산(compute_standings)과 같은 순서 — 원본은 같은 시각 더블헤더를 2차전부터 적기도 한다(2006 KIA·롯데)
    rows.sort(key=lambda g: (g["game_date"], g["dh"] or 0, g["game_time"] or ""))
    recent = rows[-RECENT_GAMES:][::-1]  # 최근 것부터
    boxed = ss._boxed(conn, [g["game_id"] for g in recent])
    out = []
    for g in recent:
        home = g["home_team"] == team
        mine, theirs = (g["home_score"], g["away_score"]) if home else (g["away_score"], g["home_score"])
        result = "T" if g["status"] == "tie" else ("W" if mine > theirs else "L")
        out.append(ss._game_out(g, boxed) | {"side": "home" if home else "away",
                                            "opponent": g["away_team"] if home else g["home_team"], "result": result})
    return out


def _v1_players(conn, team: str, season: int) -> dict:
    """선수 ID 가 없는 시즌: v1 규정 이상 기록(KBO 기록실 순위표)만 — 이름·주요 기록."""
    hitters = _rows(conn, """SELECT h.player_name AS name, h.rank, h.games, h.avg, h.home_runs, h.rbi FROM hitters h
                             JOIN teams t ON t.id = h.team_id WHERE h.season = :s AND t.name = :t ORDER BY h.rank""",
                    {"s": season, "t": team})
    pitchers = _rows(conn, """SELECT p.player_name AS name, p.rank, p.games, p.era, p.wins, p.losses, p.saves, p.holds,
                                     p.innings_pitched, p.strikeouts FROM pitchers p
                              JOIN teams t ON t.id = p.team_id WHERE p.season = :s AND t.name = :t ORDER BY p.rank""",
                     {"s": season, "t": team})
    clean = lambda rows: [{k: (float(v) if hasattr(v, "as_tuple") else v) for k, v in r.items()} for r in rows]  # noqa: E731 — Decimal → float
    return {"basis": "v1_qualified", "batters": clean(hitters), "pitchers": clean(pitchers)}


def team_detail(conn, team: str, season: int) -> dict | None:
    table = ss.standings(conn, season, None)
    row = next((r for r in table["data"] if r["team"] == team), None) if table else None
    if row is None:
        return None
    if season in naver_seasons():
        roster = {r: [x for x in naver_lines(season, r) if x["team"] == team] for r in ("batter", "pitcher")}
        by_war = lambda xs: sorted((x for x in xs if x["stats"]["WAR"] is not None), key=lambda x: -x["stats"]["WAR"])  # noqa: E731
        players = {"basis": "naver_season_stats", "batters": roster["batter"], "pitchers": roster["pitcher"],
                   "key_batters": by_war(roster["batter"])[:KEY_PLAYERS],
                   "key_pitchers": by_war(roster["pitcher"])[:KEY_PLAYERS],
                   "note": "그 시즌 출전 선수 · 소속은 네이버 시즌 기록의 팀(시즌 중 이적은 한 팀으로만 잡힌다)"}
        sources = [s for r in ("batter", "pitcher") if (s := naver_source(season, r))]
    else:
        players = _v1_players(conn, team, season) | {
            "note": "선수 ID 가 있는 자료가 없는 시즌 — KBO 기록실 규정 이상 선수만(동명이인 구분·상세 연결 불가)"}
        sources = [{"source": "kbo_site_crawl", "note": "KBO 기록실 시즌 순위표(v1 적재) — 규정 이상만"}]
    return {"data": {"team": team, "season": season, "record": row, "coverage": table["coverage"],
                     "last_played_date": table["last_played_date"], "recent_games": _team_games(conn, team, season),
                     "players": players},
            "meta": {"sources": table["meta"]["sources"] + sources, "rules": table["rules"],
                     "publication": "private_pending_rights", "updates": "paused"}}
