"""
/api/v2 시즌·일정·순위 (P2-C) — official.schedule_game · official.season_standing(KBO 공식 사이트 수집분)만 읽는다.

순위는 경기 결과에서 다시 계산하고, 원본 순위표 값은 고치지 않고 옆에 둔다.
  승률   2009·2010 승/(승+패+무)(무승부 = 패 취급), 그 밖 승/(승+패). 소수 셋째 자리 사사오입(ROUND_HALF_UP).
  승차   승률 1위 기준 ((1위 승 - 승) + (패 - 1위 패)) / 2
  순위   승률(정확한 분수) 내림차순, 같은 승률은 같은 계산 순위 + tie 표시 — 상대전적·순위 결정전은 계산하지 않는다.
원본 순위표의 '순위'가 정규시즌 승률 순서와 다른 시즌이 있다(2001–2022 중 12시즌). 방향이 그 해 포스트시즌 결과와 같아
포스트시즌 반영 최종 순위일 가능성이 있지만 포스트시즌 자료가 없어 확인하지 못했다 — 사유를 단정하지 않고 'differs' 로만 둔다.

외부 공개 금지: 이 자료는 이용 권한 확인 전이다(meta.publication). 수집은 중단돼 있다 — '현재'·'오늘' 이 아니라 수집 시점 기준.
"""
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from sqlalchemy import text

from services.v2_service import COLLECTION_POLICY, OFFICIAL_SOURCE, _iso, _rows, pick_build

SOURCE_NOTE = "KBO 공식 사이트 자동 수집분 — 수집 중단(2026-10-24 결정), 이용 권한 확인 전"
PUBLICATION = "private_pending_rights"  # 외부 공개 금지(이용 승인 전)
DRAW_AS_LOSS = {2009, 2010}


# ---------- 순수 계산 ----------

def pct_rule(season: int) -> str:
    return "wins/(wins+losses+draws)" if season in DRAW_AS_LOSS else "wins/(wins+losses)"


def pct_exact(season: int, w: int, l: int, d: int) -> Fraction | None:
    den = w + l + d if season in DRAW_AS_LOSS else w + l
    return Fraction(w, den) if den else None


def round_half_up(value: Fraction | None, places: int = 3) -> float | None:
    if value is None:
        return None
    q = (Decimal(value.numerator) / Decimal(value.denominator)).quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP)
    return float(q)


def _wdl(results: list[str]) -> str:
    return f"{results.count('W')}승{results.count('D')}무{results.count('L')}패"


def _streak(results: list[str]) -> str | None:
    """최근 연속 기록. 원본 표기처럼 무승부는 건너뛴다(연속을 끊지 않는다)."""
    decided = [r for r in results if r != "D"]
    if not decided:
        return None
    last, n = decided[-1], 0
    for r in reversed(decided):
        if r != last:
            break
        n += 1
    return f"{n}{'승' if last == 'W' else '패'}"


def compute_standings(season: int, games: list[dict]) -> list[dict]:
    """완료·무승부 경기(날짜·더블헤더 순)로 팀별 성적. games 에는 취소·예정이 섞여 있어도 된다."""
    teams = {g[k] for g in games for k in ("away_team", "home_team")}
    log = defaultdict(list)  # team -> [(home?, 'W'|'L'|'D')]
    for g in sorted(games, key=lambda g: (g["game_date"], g["dh"] or 0, g["game_time"] or "")):
        if g["status"] not in ("final", "tie"):
            continue
        a, h = g["away_score"], g["home_score"]
        res = "D" if a == h else ("W" if a > h else "L")
        log[g["away_team"]].append((False, res))
        log[g["home_team"]].append((True, {"W": "L", "L": "W", "D": "D"}[res]))
    rows = []
    for team in teams:
        res = [r for _, r in log[team]]
        w, l, d = res.count("W"), res.count("L"), res.count("D")
        split = {side: [r for home, r in log[team] if home == side] for side in (True, False)}
        rows.append({"team": team, "games": len(res), "wins": w, "losses": l, "draws": d,
                     "_pct": pct_exact(season, w, l, d), "pct": round_half_up(pct_exact(season, w, l, d)),
                     "last10": _wdl(res[-10:]) if res else None, "streak": _streak(res),
                     "home": "-".join(str(split[True].count(x)) for x in "WDL"),
                     "away": "-".join(str(split[False].count(x)) for x in "WDL")})
    key = lambda r: r["_pct"] if r["_pct"] is not None else Fraction(-1)  # noqa: E731 — 경기 없는 팀은 맨 뒤
    rows.sort(key=lambda r: (-key(r), r["team"]))
    top = rows[0] if rows and rows[0]["games"] else None
    for i, r in enumerate(rows):
        same = [x for x in rows if key(x) == key(r)]
        r["rank"] = 1 + sum(1 for x in rows if key(x) > key(r))
        r["tie"] = len(same) > 1 and r["games"] > 0
        r["games_behind"] = (((top["wins"] - r["wins"]) + (r["losses"] - top["losses"])) / 2) if top else None
    for r in rows:
        del r["_pct"]
    return rows


COMPARED = (("games", "games"), ("wins", "wins"), ("losses", "losses"), ("draws", "draws"), ("pct", "pct"),
            ("last10", "last10"), ("streak", "streak"), ("home", "home_record"), ("away", "away_record"))


def check_against_source(computed: list[dict], source: list[dict]) -> dict:
    """계산 순위표와 원본 순위표 대조. 값은 바꾸지 않고 팀별 일치 여부·차이만 붙인다(계산 행에 source·check 추가)."""
    by_team = {s["team"]: s for s in source}
    gb = lambda t, x: ((t["wins"] - x["wins"]) + (x["losses"] - t["losses"])) / 2  # noqa: E731
    # 원본 승차의 기준 팀이 시즌마다 다르다: 원본 1위(2001–2013 등, 음수 승차가 나온다) 또는 정규시즌 승률 1위(2015·2018).
    tops = [min(source, key=lambda s: s["rank"]), by_team.get(computed[0]["team"])] if source and computed else []
    summary = {"teams": len(computed), "record_mismatch": 0, "rank_differs": 0, "rank_tie": 0,
               "missing_in_source": 0}
    for r in computed:
        s = by_team.get(r["team"])
        if s is None:
            r["source"], r["check"] = None, {"status": "missing_in_source"}
            summary["missing_in_source"] += 1
            continue
        diff = [mine for mine, theirs in COMPARED
                if (r[mine] != (float(s[theirs]) if mine == "pct" and s[theirs] is not None else s[theirs]))]
        gb_basis = next((("source_rank_1", "regular_season_top")[i] for i, t in enumerate(tops)
                         if t is not None and s["games_behind"] is not None and float(s["games_behind"]) == gb(t, s)), None)
        if s["games_behind"] is not None and gb_basis is None:
            diff.append("games_behind")
        tied = sum(1 for x in computed if x["rank"] == r["rank"])
        if r["rank"] == s["rank"]:
            rank = "match"
        elif r["tie"] and r["rank"] <= s["rank"] < r["rank"] + tied:
            rank = "tie_resolved_by_source"   # 같은 승률 — 원본 순위(상대전적·결정전)를 따른다
        else:
            rank = "differs"                  # 정규시즌 승률 순서와 다르다 — 사유 미확정(포스트시즌 반영 가능성)
        r["source"] = {"rank": s["rank"], "games_behind": None if s["games_behind"] is None else float(s["games_behind"]),
                       "games_behind_basis": gb_basis,
                       **{mine: s[theirs] if mine != "pct" or s[theirs] is None else float(s[theirs])
                          for mine, theirs in COMPARED}}
        r["check"] = {"status": "mismatch" if diff else "match", "fields": diff, "rank": rank}
        summary["record_mismatch"] += bool(diff)
        summary["rank_differs"] += rank == "differs"
        summary["rank_tie"] += rank == "tie_resolved_by_source"
    return summary


# ---------- 조회 ----------

def _ref_build(conn, kind: str, season: int):
    """원본(일정·순위표) 최신 빌드. 행 없는 빌드는 없는 것으로 본다 — 로더가 만들지 않지만 예전 적재분이 있으면
    모든 화면이 500 대신 '자료 없음'이 되게(검증 결과 빌드는 0행이 정상일 수 있어 pick_build 자체는 그대로)."""
    b = pick_build(conn, kind, season, None)
    return b if b and _rows(conn, "SELECT row_count FROM derived.build WHERE build_id = :b", {"b": b["build_id"]})[0]["row_count"] else None


def _schedule_build(conn, season: int):
    return _ref_build(conn, "schedule", season)


def _schedule_rows(conn, build_id: str, where: str = "", params: dict | None = None) -> list[dict]:
    return _rows(conn, f"""SELECT row_no, season, game_date, game_time, weekday, away_team, home_team, away_score,
                                   home_score, status, cancel_reason, ballpark, game_id, dh, collected_at
                            FROM official.schedule_game WHERE build_id = :b {where}
                            ORDER BY game_date, game_time, row_no""", {"b": build_id, **(params or {})})


def _boxed(conn, game_ids: list[str]) -> set[str]:
    """네이버 박스스코어 원본이 있는 경기(상세 기록 링크를 걸 수 있는 경기)."""
    ids = [g for g in game_ids if g]
    if not ids:
        return set()
    marks = ",".join(f":g{i}" for i in range(len(ids)))
    return {r["game_id"] for r in _rows(conn, f"""SELECT DISTINCT game_id FROM ingest.raw_record
                                                   WHERE source = '{OFFICIAL_SOURCE}' AND game_id IN ({marks})""",
                                         {f"g{i}": g for i, g in enumerate(ids)})}


def _game_out(g: dict, boxed: set[str]) -> dict:
    return {"game_id": g["game_id"], "date": _iso(g["game_date"]), "time": g["game_time"], "weekday": g["weekday"],
            "away": {"team": g["away_team"], "score": g["away_score"]},
            "home": {"team": g["home_team"], "score": g["home_score"]},
            "status": g["status"], "cancel_reason": g["cancel_reason"], "ballpark": g["ballpark"],
            "doubleheader": g["dh"] if g["dh"] else None, "has_box": g["game_id"] in boxed}


def _source(build: dict, collected_at) -> dict:
    return {"source": "kbo_site_crawl", "note": SOURCE_NOTE, "build_id": build["build_id"],
            "collected_at": _iso(collected_at), "loaded_at": _iso(build["loaded_at"])}


def _meta(**extra) -> dict:
    return {"publication": PUBLICATION, "collection_policy": COLLECTION_POLICY, "updates": "paused", **extra}


def seasons(conn) -> dict:
    """적재된 시즌별 보유 범위. 일정·순위표·박스스코어를 따로 센다(시즌마다 다르다)."""
    held = [r["season"] for r in _rows(conn, """SELECT DISTINCT season FROM derived.build
                                                WHERE kind IN ('schedule', 'season_standing') ORDER BY season""", {})]
    box = {r["season"]: r["n"] for r in _rows(conn, f"""SELECT season, COUNT(DISTINCT game_id) AS n FROM ingest.raw_record
                                                         WHERE source = '{OFFICIAL_SOURCE}' GROUP BY season""", {})}
    out = []
    for season in held:
        sb, tb = _schedule_build(conn, season), _ref_build(conn, "season_standing", season)
        entry = {"season": season, "schedule": None, "standings": None, "box_games": box.get(season, 0),
                 "postseason": "not_collected"}
        if sb:
            agg = _rows(conn, """SELECT MIN(game_date) AS first, MAX(game_date) AS last, MAX(collected_at) AS at,
                                        SUM(CASE WHEN status IN ('final','tie') THEN 1 ELSE 0 END) AS played,
                                        SUM(CASE WHEN status = 'tie' THEN 1 ELSE 0 END) AS ties,
                                        SUM(CASE WHEN status = 'canceled' THEN 1 ELSE 0 END) AS canceled,
                                        SUM(CASE WHEN status = 'scheduled' THEN 1 ELSE 0 END) AS scheduled,
                                        MAX(CASE WHEN status IN ('final','tie') THEN game_date END) AS last_played
                                 FROM official.schedule_game WHERE build_id = :b""", {"b": sb["build_id"]})[0]
            entry["schedule"] = {"first_date": _iso(agg["first"]), "last_date": _iso(agg["last"]),
                                 "last_played_date": _iso(agg["last_played"]), "played": agg["played"],
                                 "ties": agg["ties"], "canceled": agg["canceled"], "scheduled": agg["scheduled"],
                                 **_source(sb, agg["at"])}
        if tb:
            at = _rows(conn, "SELECT MAX(collected_at) AS at, COUNT(*) AS n FROM official.season_standing WHERE build_id = :b",
                       {"b": tb["build_id"]})[0]
            entry["standings"] = {"teams": at["n"], **_source(tb, at["at"])}
        out.append(entry)
    collected = [e[k]["collected_at"] for e in out for k in ("schedule", "standings") if e[k]]
    return {"data": out, "meta": _meta(last_collected_at=max(collected) if collected else None,
                                       latest_season=held[-1] if held else None)}


def _range(entry: dict | None) -> dict | None:
    return None if not entry or not entry["schedule"] else {
        "first_date": entry["schedule"]["first_date"], "last_date": entry["schedule"]["last_date"]}


def schedule(conn, day: date | None, season: int | None, month: int | None) -> dict:
    """하루(day) 또는 한 달(season+month) 경기. 빈 결과는 이유를 붙인다:
    season_not_held(일정 자료 없는 시즌) / out_of_range(시즌 범위 밖 — 개막 전·종료 후·포스트시즌) / no_games(범위 안 쉬는 날)."""
    season = day.year if day else season
    build = _schedule_build(conn, season)
    if build is None:
        return {"data": [], "reason": "season_not_held", "season": season, "meta": _meta()}
    if day:
        rows = _schedule_rows(conn, build["build_id"], "AND game_date = :d", {"d": day})
    else:
        lo = date(season, month, 1)
        hi = date(season + (month == 12), month % 12 + 1, 1)
        rows = _schedule_rows(conn, build["build_id"], "AND game_date >= :lo AND game_date < :hi", {"lo": lo, "hi": hi})
    span = _rows(conn, "SELECT MIN(game_date) AS a, MAX(game_date) AS b, MAX(collected_at) AS at FROM official.schedule_game"
                       " WHERE build_id = :b", {"b": build["build_id"]})[0]
    first, last = (date.fromisoformat(str(span[k])[:10]) for k in ("a", "b"))
    reason = None
    if not rows:
        start, end = (day, day) if day else (lo, hi)
        reason = "out_of_range" if (end < first if day else end <= first) or start > last else "no_games"
    boxed = _boxed(conn, [r["game_id"] for r in rows])
    return {"data": [_game_out(r, boxed) for r in rows], "reason": reason, "season": season,
            "range": {"first_date": first.isoformat(), "last_date": last.isoformat()},
            "meta": _meta(sources=[_source(build, span["at"])])}


def standings(conn, season: int, through: date | None) -> dict | None:
    """계산 순위표(+ 시즌 전체일 때 원본 순위표 대조). through 는 그 날짜까지 끝난 경기만. 시즌 자료가 없으면 None."""
    build = _schedule_build(conn, season)
    if build is None:
        return None
    games = all_games = _schedule_rows(conn, build["build_id"])
    played = [g for g in games if g["status"] in ("final", "tie")]
    first, last_played = (min(g["game_date"] for g in games),
                          max((g["game_date"] for g in played), default=None))
    as_date = lambda v: date.fromisoformat(str(v)[:10])  # noqa: E731 — SQLite 는 문자열로 돌려준다
    coverage = "season_final"
    if through is not None:
        if through < as_date(first) or not played or through < as_date(min(g["game_date"] for g in played)):
            coverage = "before_first_game"
        elif last_played is not None and through >= as_date(last_played):
            coverage = "after_last_played"  # 보유 자료의 마지막 경기 이후 — 그 뒤 경기는 자료 없음
        else:
            coverage = "partial"
        games = [g for g in games if as_date(g["game_date"]) <= through]
    rows = compute_standings(season, games)
    source_build = _ref_build(conn, "season_standing", season)
    summary, source_meta = None, []
    if coverage != "partial" and coverage != "before_first_game" and source_build:
        src = _rows(conn, "SELECT * FROM official.season_standing WHERE build_id = :b", {"b": source_build["build_id"]})
        summary = check_against_source(rows, src)
        source_meta.append(_source(source_build, max(s["collected_at"] for s in src)))
    elif source_build:
        for r in rows:
            r["source"], r["check"] = None, {"status": "not_compared"}
    remaining = sum(1 for g in all_games if g["status"] == "scheduled")
    return {"data": rows, "season": season, "through_date": _iso(through), "coverage": coverage,
            "last_played_date": _iso(last_played), "remaining_scheduled": remaining,
            "rules": {"pct": pct_rule(season), "rounding": "ROUND_HALF_UP(3)",
                      "games_behind": "((top_wins - wins) + (losses - top_losses)) / 2, top = 계산 승률 1위",
                      "rank": "승률 내림차순, 같은 승률은 같은 계산 순위(tie) — 상대전적·순위 결정전은 원본 순위를 따른다",
                      "source_rank": "원본 순위 값을 그대로 둔다. 계산 순위와 다르면 check.rank=differs — 사유 미확정(포스트시즌 반영 가능성, 포스트시즌 자료 미보유로 확인 불가)"},
            "check_summary": summary,
            "meta": _meta(sources=[_source(build, max(g["collected_at"] for g in all_games))]
                          + source_meta)}


def home(conn, season: int | None) -> dict | None:
    """라이트팬 첫 화면: 기준 배너 · 순위 요약 · 보유 자료의 마지막 경기일 결과. 실시간·'오늘' 이 아니다."""
    info = seasons(conn)
    season = season or info["meta"]["latest_season"]
    entry = next((e for e in info["data"] if e["season"] == season), None)
    if entry is None or entry["schedule"] is None:
        return None
    table = standings(conn, season, None)
    last = entry["schedule"]["last_played_date"]
    day = schedule(conn, date.fromisoformat(last), None, None) if last else {"data": []}
    return {"season": season, "banner": {"last_collected_at": info["meta"]["last_collected_at"],
                                         "season_collected_at": entry["schedule"]["collected_at"],
                                         "last_played_date": last, "remaining_scheduled": table["remaining_scheduled"],
                                         "updates": "paused", "postseason": "not_collected"},
            "standings": [{k: r[k] for k in ("rank", "team", "games", "wins", "losses", "draws", "pct", "games_behind",
                                              "tie")} | {"source_rank": (r.get("source") or {}).get("rank")}
                          for r in table["data"]],
            "check_summary": table["check_summary"],
            "last_games": {"date": last, "games": day["data"]},
            "seasons": [{"season": e["season"], "schedule": e["schedule"] is not None, "box_games": e["box_games"]}
                        for e in info["data"]],
            "meta": _meta(sources=table["meta"]["sources"])}
