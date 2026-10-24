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

from services import season_service as ss
from services.v2_service import _rows
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


@lru_cache(maxsize=64)
def _season_lines(season: int, key: tuple) -> tuple[dict, ...]:
    """한 시즌 타자·투수 줄. 투수 기록이 있는 선수의 타자 줄(투수 타석)은 뺀다 — 포지션이 야수로 적힌 경우만 남긴다
    (2007–2023 은 포지션이 대부분 비어 있다)."""
    lines = []
    for role, (path, _) in zip(("batter", "pitcher"), key):
        lines += [{"player_id": r["PlayerId"], "name": r["선수명"], "season": season, "role": role, "team": r["팀명"],
                   "position": r["포지션"], "back_no": r["등번호"], "qualified": r["규정충족"],
                   "stats": {k: r.get(k) for k in STATS[role]}} for r in _read(path) if r["PlayerId"] is not None]
    pitchers = {x["player_id"] for x in lines if x["role"] == "pitcher"}
    return tuple(x for x in lines if x["role"] == "pitcher" or x["player_id"] not in pitchers
                 or x["position"] not in (None, "투수"))


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


def profile(player_id: int) -> dict | None:
    """한 선수의 시즌·역할별 네이버 시즌 기록(비교·상세용). 없으면 None."""
    lines = [line for line in _all_lines() if line["player_id"] == player_id]
    if not lines:
        return None
    lines.sort(key=lambda x: (-x["season"], x["role"]))
    latest = lines[0]
    identity = {"player_id": player_id, "name": latest["name"], "team": latest["team"], "position": latest["position"],
                **registry().get(player_id, {"birth_date": None, "pitch_bat": None, "roster_date": None})}
    return {"data": {"player": identity, "seasons": lines},
            "meta": {"sources": [naver_source(x["season"], x["role"]) for x in lines]
                     + ([{"source": "kbo_registered_players", "note": REGISTRY_NOTE}] if identity["roster_date"] else [])}}


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
