"""
/api/v2 조회 — PostgreSQL 신규 스키마(ref·ingest·official·derived·verify)만 읽는다. public 테이블은 안 읽는다.

시점 두 가지를 구분한다.
  as_of        시스템이 실제로 데이터를 확보한 시각 기준. 외부 기록은 fetched_at <= as_of 인 경기별 최신 원본,
               계산·대조는 loaded_at <= as_of 인 최신 빌드. 2026 에 백필한 2025 원본은 as_of=2025-xx 에 안 보인다.
  through_date 경기 날짜 기준 집계 범위(ref.game.game_date <= through_date). 예측용 과거 재구성은 별도 기능이다.

외부 기록(official: 네이버 박스스코어 — KBO 공식 기록의 2차 출처)과 자체 계산(calc: 투구 데이터)은 따로 돌려준다.
미확정 계산값은 null 그대로다. `kbo_verified` 는 KBO 원본(source 가 kbo_ 로 시작) 대조가 있을 때만 나올 수 있고,
현재 그런 원본이 없어 모든 kbo 상태는 not_checked 다.

SQL 은 PostgreSQL·SQLite(단위 테스트) 둘 다에서 돌도록 창 함수만 쓴다(DISTINCT ON·형변환 없음).
"""
from datetime import date, datetime, timezone

from sqlalchemy import text

OFFICIAL_SOURCE = "naver_boxscore"
OFFICIAL_NOTE = "네이버 박스스코어 — KBO 공식 기록의 2차 출처. KBO 원본으로 직접 검증한 값이 아니다"
COLLECTION_POLICY = {  # 2026-10-24 운영 결정(src/kbo_access.py · src/naver_access.py)
    "kbo_official_site": "disabled_pending_approval",
    "naver_sports": "paused_pending_terms_review",
}
KBO_NOT_CHECKED = {"status": "not_checked"}

PITCHER_LINE = ["ord", "ip", "outs", "bf", "ab", "h", "hr", "bb", "bbhp", "so", "r", "er", "np", "decision"]
BATTER_LINE = ["bat_order", "pos", "ab", "h", "hr", "bb", "so", "r", "rbi", "sb", "ibb"]
PITCHER_CALC = ["outs", "outs_complete", "bf", "h", "bb", "hbp", "so", "result_unknown", "pa_uncertain",
                "attribution_uncertain", "pa_complete", "stats_complete"]
BATTER_CALC = ["pa", "ab", "h", "b2", "b3", "hr", "bb", "hbp", "sf", "sh", "so", "result_unknown", "pa_uncertain",
               "attribution_uncertain", "pa_complete", "stats_complete"]

# 리더보드에 쓸 수 있는 항목(역할·기준별). 비율은 아래 RATES 에서 계산한다.
LEADER_STATS = {
    ("pitcher", "official"): {"outs", "bf", "h", "hr", "bb", "bbhp", "so", "r", "er", "np", "era", "whip"},
    ("batter", "official"): {"ab", "h", "hr", "bb", "so", "r", "rbi", "sb", "ibb", "avg"},
    ("pitcher", "calc"): {"outs", "bf", "h", "bb", "hbp", "so"},
    ("batter", "calc"): {"pa", "ab", "h", "b2", "b3", "hr", "bb", "hbp", "sf", "sh", "so", "avg"},
}
LOWER_IS_BETTER = {"era", "whip"}


# ---------- 순수 계산 ----------

def ip_text(outs: int | None) -> str | None:
    """아웃 수 → 이닝 표기. 17 → '5 2/3', 3 → '1', 0 → '0'. 계산은 항상 정수 아웃으로 한다."""
    if outs is None:
        return None
    whole, frac = divmod(int(outs), 3)
    return f"{whole} {frac}/3" if frac else str(whole)


def ratio(numerator, denominator, digits: int = 3, scale: float = 1.0):
    """분모가 0·None 이면 None(0 으로 나누지 않는다)."""
    if numerator is None or not denominator:
        return None
    return round(numerator * scale / denominator, digits)


def rates(role: str, totals: dict) -> dict:
    if role == "pitcher":
        outs = totals.get("outs")
        whip_num = None if totals.get("h") is None or totals.get("bb") is None else totals["h"] + totals["bb"]
        return {"era": ratio(totals.get("er"), outs, 2, 27), "whip": ratio(whip_num, outs, 2, 3)}
    return {"avg": ratio(totals.get("h"), totals.get("ab"), 3)}


def _iso(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _clean(row: dict) -> dict:
    return {k: (bool(v) if k.endswith("_complete") and v is not None else _iso(v)) for k, v in row.items()}


# ---------- 시점 선택 ----------

def latest_raw_sql(where: str = "") -> str:
    """경기별 최신 네이버 박스스코어 원본(fetched_at <= :as_of). :as_of 가 None 이면 시각 조건 없이.
    출처를 고정한다 — 같은 경기의 다른 출처(KBO 등) 원본이 더 늦게 들어와도 네이버 줄을 가리지 않는다."""
    return f"""
        SELECT game_id, raw_file, fetched_at FROM (
            SELECT r.game_id, r.raw_file, r.fetched_at, ROW_NUMBER() OVER (
                PARTITION BY r.game_id ORDER BY r.fetched_at DESC, r.raw_file DESC) AS rn
            FROM ingest.raw_record r
            WHERE r.season = :season AND r.source = '{OFFICIAL_SOURCE}'
                  AND (:as_of IS NULL OR r.fetched_at <= :as_of) {where}
        ) t WHERE rn = 1"""


def pick_build(conn, kind: str, season: int, as_of, basis: str | None = None) -> dict | None:
    """as_of 이전 최신 빌드. basis 를 주면 그 계산 빌드를 기준으로 만든 빌드만(대조·예외)."""
    row = conn.execute(text(f"""
        SELECT build_id, calc_rule, loaded_at FROM derived.build
        WHERE kind = :kind AND season = :season AND (:as_of IS NULL OR loaded_at <= :as_of)
              {"AND basis_build_id = :basis" if basis else ""}
        ORDER BY loaded_at DESC, build_id DESC LIMIT 1"""),
        {"kind": kind, "season": season, "as_of": as_of, "basis": basis}).mappings().first()
    return dict(row) if row else None


def kbo_source_count(conn, season: int, as_of) -> int:
    """그 시즌·그 시점까지 확보한 KBO 원본 수(source 가 kbo 로 시작). 다른 시즌·나중 원본은 세지 않는다."""
    return conn.execute(text("""SELECT COUNT(*) FROM ingest.raw_record WHERE source LIKE 'kbo%' AND season = :s
                                AND (:as_of IS NULL OR fetched_at <= :as_of)"""), {"s": season, "as_of": as_of}).scalar_one()


def meta(conn, season: int, as_of, raws: list[dict] | None = None, builds: dict | None = None, **extra) -> dict:
    fetched = [r["fetched_at"] for r in raws or [] if r.get("fetched_at")]
    sources = []
    if raws is not None:
        sources.append({"source": OFFICIAL_SOURCE, "kind": "official_secondary", "note": OFFICIAL_NOTE,
                        "raw_files": len(raws), "fetched_at_min": _iso(min(fetched)) if fetched else None,
                        "fetched_at_max": _iso(max(fetched)) if fetched else None})
    for kind, build in (builds or {}).items():
        sources.append({"source": "pitch_relay" if kind == "player_game" else "verify", "kind": kind,
                        "build_id": build["build_id"] if build else None,
                        "calc_rule": build["calc_rule"] if build else None,
                        "loaded_at": _iso(build["loaded_at"]) if build else None})
    return {"season": season, "as_of": _iso(as_of), "generated_at": datetime.now(timezone.utc).isoformat(),
            # 경기 일정·선수 이름(ref)은 이력이 없어 현재 값이다. as_of 조회에서 경기 점수·상태는 비운다.
            "reference_data": "current_unversioned",
            "sources": sources, "collection_policy": COLLECTION_POLICY,
            "kbo_direct_verification": "available" if kbo_source_count(conn, season, as_of) else "not_available", **extra}


# ---------- 공통 조립 ----------

def _rows(conn, sql: str, params: dict) -> list[dict]:
    return [dict(r) for r in conn.execute(text(sql), params).mappings()]


def _player_entry(role: str, official: dict | None, calc: dict | None, checks: dict[str, str]) -> dict:
    line_cols, calc_cols = (PITCHER_LINE, PITCHER_CALC) if role == "pitcher" else (BATTER_LINE, BATTER_CALC)
    out = {"official": None, "calc": None, "verification": checks, "kbo": KBO_NOT_CHECKED}
    if official:
        out["official"] = {"source": OFFICIAL_SOURCE, "fetched_at": _iso(official.get("fetched_at")),
                           "raw_file": official.get("raw_file"), **{c: official.get(c) for c in line_cols}}
        if role == "pitcher":
            out["official"]["ip_from_outs"] = ip_text(official.get("outs"))
    if calc:
        out["calc"] = _clean({c: calc.get(c) for c in calc_cols})
        if role == "pitcher":
            out["calc"]["ip_from_outs"] = ip_text(calc.get("outs"))
    return out


def _game_rows(conn, season: int, game_ids: list[str], player_id: int | None, as_of, builds: dict) -> dict:
    """경기 묶음의 (외부 기록 줄, 계산 줄, 대조 상태). 키 = (game_id, role, player_id)."""
    if not game_ids:
        return {"official": {}, "calc": {}, "checks": {}, "raws": []}
    params = {"season": season, "as_of": as_of, "pid": player_id}
    games = ", ".join(f":g{i}" for i in range(len(game_ids)))
    params.update({f"g{i}": g for i, g in enumerate(game_ids)})
    who = "AND l.player_id = :pid" if player_id is not None else ""
    raws = _rows(conn, latest_raw_sql(f"AND r.game_id IN ({games})"), params)
    official = {}
    for role, table in (("pitcher", "official.game_pitcher_line"), ("batter", "official.game_batter_line")):
        for r in _rows(conn, f"""
                SELECT l.* FROM {table} l JOIN ({latest_raw_sql(f"AND r.game_id IN ({games})")}) lr
                  ON lr.raw_file = l.raw_file WHERE 1 = 1 {who}""", params):
            official[(r["game_id"], role, r["player_id"])] = r
    calc, checks = {}, {}
    pg, ck = builds.get("player_game"), builds.get("player_game_check")
    if pg:
        for r in _rows(conn, f"""SELECT * FROM derived.player_game l WHERE build_id = :b AND game_id IN ({games}) {who}""",
                       {**params, "b": pg["build_id"]}):
            calc[(r["game_id"], r["role"], r["player_id"])] = r
    if ck:
        # 지금 보여 주는 원본(raws)과 대조한 결과만 붙인다 — 다시 받은 원본 옆에 옛 원본 대조 상태를 두지 않는다.
        for r in _rows(conn, f"""SELECT l.game_id, l.role, l.player_id, l.metric, l.status FROM verify.player_game_check l
                                 JOIN ({latest_raw_sql(f"AND r.game_id IN ({games})")}) lr
                                   ON lr.raw_file = l.external_raw_file
                                 WHERE l.build_id = :b AND l.game_id IN ({games}) {who}""", {**params, "b": ck["build_id"]}):
            checks.setdefault((r["game_id"], r["role"], r["player_id"]), {})[r["metric"]] = r["status"]
    return {"official": official, "calc": calc, "checks": checks, "raws": raws}


def _builds(conn, season: int, as_of, *kinds: str) -> dict:
    """계산 빌드를 먼저 고르고, 대조·예외 빌드는 그 계산 빌드와 연결된 것만 고른다 — 다른 계산을 대조한
    상태를 지금 보여 주는 계산값 옆에 붙이지 않는다. 계산 빌드가 없으면 대조도 없다."""
    calc = pick_build(conn, "player_game", season, as_of)
    out = {}
    for kind in kinds:
        if kind == "player_game":
            out[kind] = calc
        else:
            out[kind] = pick_build(conn, kind, season, as_of, calc["build_id"]) if calc else None
    return out


# ---------- 엔드포인트 ----------

def game_box(conn, game_id: str, as_of) -> dict | None:
    game = conn.execute(text("SELECT * FROM ref.game WHERE game_id = :g"), {"g": game_id}).mappings().first()
    if game is None:
        return None
    season = game["season"]
    builds = _builds(conn, season, as_of, "player_game", "player_game_check", "verify_exception")
    found = _game_rows(conn, season, [game_id], None, as_of, builds)
    if as_of is not None and not found["raws"] and not found["calc"]:
        return None  # 그 시점엔 이 경기에 대해 가진 게 없었다 — 나중에 적재한 일정 정보도 내보이지 않는다
    raw = found["raws"][0] if found["raws"] else None
    sides = {}
    keys = sorted(set(found["official"]) | set(found["calc"]), key=lambda k: (k[1], k[2]))
    for key in keys:
        _, role, pid = key
        line, calc = found["official"].get(key), found["calc"].get(key)
        entry = {"player_id": pid, "name": (line or calc).get("player"),
                 "side": line.get("side") if line else None, "team": (line or calc).get("team"),
                 **_player_entry(role, line, calc, found["checks"].get(key, {}))}
        sides.setdefault(role, []).append(entry)
    for role in sides:  # 팀별, 외부 기록 순서(등판·타순) — 외부 기록이 없는 선수는 뒤로
        order = "ord" if role == "pitcher" else "bat_order"
        sides[role].sort(key=lambda e: (e["side"] or "~", (e["official"] or {}).get(order) or 99, e["player_id"]))
    exceptions = []
    if builds["verify_exception"]:
        exceptions = _rows(conn, """SELECT kind, role, player_id, player, count, detail FROM verify.exception
                                    WHERE build_id = :b AND game_id = :g ORDER BY kind, player_id""",
                           {"b": builds["verify_exception"]["build_id"], "g": game_id})
    mismatch = {}
    for line in found["official"].values():
        mismatch.setdefault(line["side"], set()).update(filter(None, (line.get("team_sum_mismatch") or "").split(",")))
    data = {
        # ref.game 은 버전 없는 현재 일정이라 as_of 조회에선 그때 몰랐을 수 있는 점수·상태를 비운다.
        "game": {"game_id": game_id, "date": _iso(game["game_date"]), "dh": game["dh"], "away": game["away_team"],
                 "home": game["home_team"],
                 "score": None if as_of is not None else {"away": game["away_score"], "home": game["home_score"]},
                 "status": None if as_of is not None else game["status"], "ballpark": game["ballpark"]},
        "official": None if raw is None else {"source": OFFICIAL_SOURCE, "fetched_at": _iso(raw["fetched_at"]),
                                              "raw_file": raw["raw_file"],
                                              "team_sum_mismatch": {k: sorted(v) for k, v in mismatch.items()}},
        "pitchers": sides.get("pitcher", []), "batters": sides.get("batter", []),
        "exceptions": exceptions, "kbo": KBO_NOT_CHECKED,
    }
    return {"data": data, "meta": meta(conn, season, as_of, found["raws"], builds)}


def player(conn, player_id: int) -> dict | None:
    row = conn.execute(text("SELECT player_id, name FROM ref.player WHERE player_id = :p"), {"p": player_id}).mappings().first()
    if row is None:
        return None
    names = _rows(conn, "SELECT name, source FROM ref.player_name WHERE player_id = :p ORDER BY source, name", {"p": player_id})
    return {**dict(row), "names": names}


def _player_game_keys(conn, season: int, player_id: int, role: str | None, as_of, builds: dict,
                      date_from, date_to) -> list[dict]:
    """선수가 나온 (경기, 역할) — 외부 기록 또는 계산 어느 한쪽에라도 있으면."""
    parts, params = [], {"season": season, "as_of": as_of, "pid": player_id}
    for r, table in (("pitcher", "official.game_pitcher_line"), ("batter", "official.game_batter_line")):
        if role in (None, r):
            parts.append(f"""SELECT l.game_id, '{r}' AS role FROM {table} l
                             JOIN ({latest_raw_sql()}) lr ON lr.raw_file = l.raw_file WHERE l.player_id = :pid""")
    if builds.get("player_game"):
        parts.append("""SELECT game_id, role FROM derived.player_game WHERE build_id = :b AND player_id = :pid"""
                     + (" AND role = :role" if role else ""))
        params.update(b=builds["player_game"]["build_id"], role=role)
    if not parts:
        return []
    where = ["g.season = :season"]
    if date_from:
        where.append("g.game_date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        where.append("g.game_date <= :date_to")
        params["date_to"] = date_to
    return _rows(conn, f"""SELECT DISTINCT k.game_id, k.role, g.game_date, g.dh FROM ({' UNION '.join(parts)}) k
                           JOIN ref.game g ON g.game_id = k.game_id WHERE {' AND '.join(where)}""", params)


def player_games(conn, player_id: int, season: int, role, date_from, date_to, as_of,
                 limit: int, offset: int, sort: str) -> dict | None:
    who = player(conn, player_id)
    if who is None:
        return None
    builds = _builds(conn, season, as_of, "player_game", "player_game_check")
    keys = _player_game_keys(conn, season, player_id, role, as_of, builds, date_from, date_to)
    if as_of is not None and not keys:
        return None  # 그 시점엔 이 선수의 기록이 없었다
    keys.sort(key=lambda k: (str(k["game_date"]), k["dh"], k["game_id"], k["role"]), reverse=sort == "-date")
    page = keys[offset:offset + limit]
    found = _game_rows(conn, season, sorted({k["game_id"] for k in page}), player_id, as_of, builds)
    games = []
    for k in page:
        key = (k["game_id"], k["role"], player_id)
        line, calc = found["official"].get(key), found["calc"].get(key)
        games.append({"game_id": k["game_id"], "date": _iso(k["game_date"]), "role": k["role"],
                      "team": (line or calc or {}).get("team"), "opponent": (calc or {}).get("opponent"),
                      "home_away": (calc or {}).get("home_away") or (line or {}).get("side"),
                      **_player_entry(k["role"], line, calc, found["checks"].get(key, {}))})
    nxt = offset + limit if offset + limit < len(keys) else None
    return {"data": {"player": who, "games": games},
            "page": {"limit": limit, "offset": offset, "total": len(keys), "next_offset": nxt, "sort": sort},
            "meta": meta(conn, season, as_of, found["raws"], builds)}


OFFICIAL_SUMS = {"pitcher": ["outs", "bf", "ab", "h", "hr", "bb", "bbhp", "so", "r", "er", "np"],
                 "batter": ["ab", "h", "hr", "bb", "so", "r", "rbi", "sb", "ibb"]}
# 원본 팀 합계 검사(team_sum_mismatch)가 다루는 항목(파서 이름 → 열). 이 항목이 어긋난 경기의 합은 믿지 않는다.
TEAM_CHECKED = {"pitcher": {"Outs": "outs", "BF": "bf", "H": "h", "HR": "hr", "BBHP": "bbhp", "SO": "so", "R": "r"},
                "batter": {"AB": "ab", "H": "h", "R": "r", "RBI": "rbi", "SB": "sb"}}
STAT_INPUTS = {"era": ["er", "outs"], "whip": ["h", "bb", "outs"], "avg": ["h", "ab"]}


def mismatched(role: str, mismatch_games: dict, stat: str) -> bool:
    """stat(또는 그 비율의 분자·분모)에 팀 합계가 어긋난 경기가 섞였나."""
    return any(mismatch_games.get(col, 0) for col in STAT_INPUTS.get(stat, [stat]))
CALC_SUMS = {"pitcher": ["bf", "h", "bb", "hbp", "so"],
             "batter": ["pa", "ab", "h", "b2", "b3", "hr", "bb", "hbp", "sf", "sh", "so"]}


def _total(expr: str, alias: str) -> str:
    """경기 하나라도 값이 비면 합계도 모른다(SQL SUM 은 NULL 을 건너뛰어 그럴듯한 합을 낸다 — Codex P2-B)."""
    return f"CASE WHEN COUNT({expr}) = COUNT(*) THEN SUM({expr}) END AS {alias}"


def _official_totals_sql(role: str, group_by_player: bool, player_filter: bool) -> str:
    table = "official.game_pitcher_line" if role == "pitcher" else "official.game_batter_line"
    sums = ", ".join(_total(f"l.{c}", c) for c in OFFICIAL_SUMS[role])
    mm = ", ".join(f"SUM(CASE WHEN ',' || l.team_sum_mismatch || ',' LIKE '%,{name},%' THEN 1 ELSE 0 END) AS mm_{col}"
                   for name, col in TEAM_CHECKED[role].items())
    return f"""
        SELECT l.player_id, MAX(l.player) AS player, COUNT(*) AS games, {mm},
               {sums}
        FROM {table} l JOIN ({latest_raw_sql()}) lr ON lr.raw_file = l.raw_file
        JOIN ref.game g ON g.game_id = l.game_id
        WHERE (:through IS NULL OR g.game_date <= :through) {"AND l.player_id = :pid" if player_filter else ""}
        GROUP BY l.player_id"""


def _calc_totals_sql(role: str, player_filter: bool) -> str:
    sums = ", ".join(_total(c, c) for c in CALC_SUMS[role])
    outs = """, SUM(CASE WHEN outs_complete THEN outs ELSE 0 END) AS outs_known,
             SUM(CASE WHEN outs_complete THEN 1 ELSE 0 END) AS games_outs_complete""" if role == "pitcher" else ""
    return f"""
        SELECT player_id, MAX(player) AS player, COUNT(*) AS games,
               SUM(CASE WHEN stats_complete THEN 1 ELSE 0 END) AS games_stats_complete, {sums} {outs}
        FROM derived.player_game
        WHERE build_id = :b AND role = :role AND (:through IS NULL OR game_date <= :through)
              {"AND player_id = :pid" if player_filter else ""}
        GROUP BY player_id"""


def _calc_block(role: str, row: dict | None, build: dict | None) -> dict | None:
    if row is None:
        return None
    exact = row["games_stats_complete"] == row["games"]
    totals = {c: row[c] for c in CALC_SUMS[role]}
    block = {"calc_rule": build["calc_rule"], "games": row["games"], "games_stats_complete": row["games_stats_complete"],
             "stats_exact": exact, "totals": totals}
    if role == "pitcher":
        complete = row["games_outs_complete"] == row["games"]
        # 한 경기라도 아웃 미확정이면 시즌 아웃 합은 모른다 — null. 확정분 합은 하한으로만 따로 준다.
        totals["outs"] = row["outs_known"] if complete else None
        block.update(games_outs_complete=row["games_outs_complete"], outs_lower_bound=row["outs_known"])
        block["rates"] = {"era": None, "whip": None}  # 계산 기록엔 자책·볼넷 확정 기준이 없어 비율을 만들지 않는다
    else:
        block["rates"] = rates("batter", totals) if exact else {"avg": None}
    return block


def player_season(conn, player_id: int, season: int, role, through, as_of) -> dict | None:
    who = player(conn, player_id)
    if who is None:
        return None
    builds = _builds(conn, season, as_of, "player_game", "player_game_check")
    raws = _rows(conn, latest_raw_sql(), {"season": season, "as_of": as_of})
    params = {"season": season, "as_of": as_of, "through": through, "pid": player_id}
    roles = {}
    for r in ("pitcher", "batter"):
        if role not in (None, r):
            continue
        off = conn.execute(text(_official_totals_sql(r, True, True)), params).mappings().first()
        calc = None
        if builds["player_game"]:
            calc = conn.execute(text(_calc_totals_sql(r, True)), {**params, "b": builds["player_game"]["build_id"],
                                                                  "role": r}).mappings().first()
        if off is None and calc is None:
            continue
        official = None
        if off is not None:
            totals = {c: off[c] for c in OFFICIAL_SUMS[r]}
            if r == "pitcher":
                totals["ip_from_outs"] = ip_text(totals["outs"])
            mm = {col: off[f"mm_{col}"] for col in TEAM_CHECKED[r].values() if off[f"mm_{col}"]}
            official = {"source": OFFICIAL_SOURCE, "games": off["games"], "totals": totals, "rates": rates(r, totals),
                        # 원본 팀 합계가 어긋난 경기 수(항목별). 0 이 아니면 그 합은 원본 자체가 불확실하다.
                        "team_sum_mismatch_games": mm}
        verification = {}
        if builds["player_game_check"]:
            for v in _rows(conn, f"""
                    SELECT c.metric, c.status, COUNT(*) AS n FROM verify.player_game_check c
                    JOIN ({latest_raw_sql()}) lr ON lr.raw_file = c.external_raw_file
                    JOIN ref.game g ON g.game_id = c.game_id
                    WHERE c.build_id = :b AND c.role = :role AND c.player_id = :pid
                          AND (:through IS NULL OR g.game_date <= :through)
                    GROUP BY c.metric, c.status ORDER BY c.metric, c.status""",
                    {**params, "b": builds["player_game_check"]["build_id"], "role": r}):
                verification.setdefault(v["metric"], {})[v["status"]] = v["n"]
        roles[r] = {"official": official, "calc": _calc_block(r, dict(calc) if calc else None, builds["player_game"]),
                    "verification": verification, "kbo": KBO_NOT_CHECKED}
    if as_of is not None and not roles:
        return None  # 그 시점엔 이 선수의 기록이 없었다
    return {"data": {"player": who, "through_date": _iso(through), "roles": roles},
            "meta": meta(conn, season, as_of, raws, builds)}


def _team_games(conn, season: int, through, as_of) -> dict[str, int]:
    """팀별 경기 수(규정이닝 분모). 집계에 쓰는 것과 같은 범위 — as_of 에 박스스코어 원본을 가진 경기 중
    through_date 이전 — 로 센다. 현재 일정 전체를 세면 과거 시점 분모에 그 뒤 경기가 섞인다(Codex P2-B 3차)."""
    counts: dict[str, int] = {}
    for g in _rows(conn, f"""SELECT g.away_team, g.home_team FROM ({latest_raw_sql()}) lr
                             JOIN ref.game g ON g.game_id = lr.game_id
                             WHERE (:through IS NULL OR g.game_date <= :through)""",
                   {"season": season, "through": through, "as_of": as_of}):
        for team in (g["away_team"], g["home_team"]):
            counts[team] = counts.get(team, 0) + 1
    return counts


def leaders(conn, season: int, role: str, stat: str, basis: str, min_outs: int, min_ab: int, qualified: bool,
            through, as_of, limit: int, offset: int) -> dict:
    """리더보드. 기준(basis)·자격(min_outs/min_ab/qualified)·정렬(낮을수록 좋은 항목 오름차순, 동점은 player_id)."""
    builds = _builds(conn, season, as_of, "player_game")
    raws = _rows(conn, latest_raw_sql(), {"season": season, "as_of": as_of})
    params = {"season": season, "as_of": as_of, "through": through}
    if basis == "calc" and qualified:
        # 계산 기록엔 소속 팀이 없어 규정이닝(팀 경기 수 × 1이닝)을 정할 수 없다 — 짐작하지 않는다.
        raise ValueError("qualified=true is not supported with basis=calc")
    excluded = excluded_mismatch = 0
    rows = []
    if basis == "official":
        team_of = {r["player_id"]: r["team"] for r in _rows(conn, f"""
            SELECT l.player_id, l.team, ROW_NUMBER() OVER (PARTITION BY l.player_id ORDER BY g.game_date DESC, l.game_id DESC) AS rn
            FROM {'official.game_pitcher_line' if role == 'pitcher' else 'official.game_batter_line'} l
            JOIN ({latest_raw_sql()}) lr ON lr.raw_file = l.raw_file JOIN ref.game g ON g.game_id = l.game_id
            WHERE (:through IS NULL OR g.game_date <= :through)""", params) if r["rn"] == 1}
        for r in _rows(conn, _official_totals_sql(role, True, False), params):
            totals = {c: r[c] for c in OFFICIAL_SUMS[role]}
            if mismatched(role, {col: r[f"mm_{col}"] for col in TEAM_CHECKED[role].values()}, stat):
                excluded_mismatch += 1  # 원본 팀 합계가 어긋난 항목으로는 순위를 매기지 않는다
                continue
            rows.append({"player_id": r["player_id"], "name": r["player"], "team": team_of.get(r["player_id"]),
                         "games": r["games"], "totals": totals, "value": {**totals, **rates(role, totals)}.get(stat),
                         "complete": True})
    elif builds["player_game"]:
        for r in _rows(conn, _calc_totals_sql(role, False), {**params, "b": builds["player_game"]["build_id"], "role": role}):
            block = _calc_block(role, r, builds["player_game"])
            value = {**block["totals"], **block["rates"]}.get(stat)
            # 확정되지 않은 값(하한)으로는 순위를 매기지 않는다.
            exact = block["stats_exact"] and (role != "pitcher" or block["totals"]["outs"] is not None)
            if not exact or value is None:
                excluded += 1
                continue
            rows.append({"player_id": r["player_id"], "name": r["player"], "team": None, "games": r["games"],
                         "totals": block["totals"], "value": value, "complete": True})
    team_games = _team_games(conn, season, through, as_of) if qualified else {}
    need_rate = stat in {"era", "whip", "avg"}

    def eligible(row) -> bool:
        t = row["totals"]
        if role == "pitcher":
            outs = t.get("outs") or 0
            if outs < min_outs or (need_rate and outs == 0):
                return False
            # 규정이닝 = 팀 경기 수 × 1이닝(= 아웃 3개). 팀은 그 선수의 가장 최근 경기 팀.
            return not qualified or outs >= 3 * team_games.get(row["team"], 0)
        ab = t.get("ab") or 0
        return ab >= min_ab and not (need_rate and ab == 0)

    missing = sum(1 for r in rows if r["value"] is None)  # 입력 값이 빈 경기가 있어 합계·비율을 모르는 선수
    ranked = [r for r in rows if r["value"] is not None and eligible(r)]
    sign = 1 if stat in LOWER_IS_BETTER else -1
    ranked.sort(key=lambda r: (sign * r["value"], r["player_id"]))
    page, rank, prev = [], 0, object()
    for i, r in enumerate(ranked):
        if r["value"] != prev:
            rank, prev = i + 1, r["value"]
        if offset <= i < offset + limit:
            page.append({"rank": rank, **{k: r[k] for k in ("player_id", "name", "team", "games", "value", "complete")}})
    # 공식 규정 순위가 아닌 것을 공식처럼 읽지 않게: 규정이닝은 박스스코어 경기 수로 계산한 값, 나머지는 참고 순위.
    criteria = {"ranking": "qualified_innings_computed" if qualified else "reference",
                "basis": basis, "stat": stat, "order": "asc" if sign == 1 else "desc", "min_outs": min_outs,
                "min_ab": min_ab, "qualified": qualified,
                "qualification_rule": "outs >= 3 x team games held at as_of (box score raws, through_date)"
                                      if qualified else None,
                "excluded_not_exact": excluded, "excluded_team_sum_mismatch": excluded_mismatch,
                "excluded_missing_value": missing}
    return {"data": {"leaders": page, "criteria": criteria},
            "page": {"limit": limit, "offset": offset, "total": len(ranked),
                     "next_offset": offset + limit if offset + limit < len(ranked) else None},
            "meta": meta(conn, season, as_of, raws if basis == "official" else None,
                         builds if basis == "calc" else None, through_date=_iso(through))}


def data_quality(conn, season: int, as_of) -> dict:
    builds = _builds(conn, season, as_of, "player_game", "player_game_check", "outs_uncertain", "verify_exception")
    raws = _rows(conn, latest_raw_sql(), {"season": season, "as_of": as_of})
    # ref.game 은 버전이 없는 현재 일정이라 as_of 시점의 완료 경기 수를 알 수 없다 — 그때는 비운다.
    final_games = None if as_of is not None else conn.execute(
        text("SELECT COUNT(*) FROM ref.game WHERE season = :s AND status = 'final'"), {"s": season}).scalar_one()
    calc_games = 0
    if builds["player_game"]:
        calc_games = conn.execute(text("SELECT COUNT(DISTINCT game_id) FROM derived.player_game WHERE build_id = :b"),
                                  {"b": builds["player_game"]["build_id"]}).scalar_one()
    fetch = {r["status"]: r["n"] for r in _rows(conn, """SELECT status, COUNT(*) AS n FROM ingest.fetch_log
                                                         WHERE season = :s AND (:as_of IS NULL OR fetched_at <= :as_of)
                                                         GROUP BY status""", {"s": season, "as_of": as_of})}
    by_metric, outs_uncertain, exceptions = {}, {}, {}
    if builds["player_game_check"]:
        # 지금 보여 주는 원본(as_of 기준 경기별 최신)과 대조한 결과만 센다 — 경기·선수 화면과 같은 기준.
        for r in _rows(conn, f"""SELECT c.role, c.metric, c.status, COUNT(*) AS n FROM verify.player_game_check c
                                 JOIN ({latest_raw_sql()}) lr ON lr.raw_file = c.external_raw_file
                                 WHERE c.build_id = :b GROUP BY c.role, c.metric, c.status""",
                       {"b": builds["player_game_check"]["build_id"], "season": season, "as_of": as_of}):
            by_metric.setdefault(f"{r['role']}.{r['metric']}", {})[r["status"]] = r["n"]
    if builds["outs_uncertain"]:
        outs_uncertain = {r["naver_status"]: r["n"] for r in _rows(conn, f"""
            SELECT u.naver_status, COUNT(*) AS n FROM verify.outs_uncertain u
            LEFT JOIN ({latest_raw_sql()}) lr ON lr.game_id = u.game_id
            WHERE u.build_id = :b
              AND (u.external_raw_file IS NULL OR u.external_raw_file = lr.raw_file)  -- 옛 원본 대조는 빼고 센다
            GROUP BY u.naver_status""",
            {"b": builds["outs_uncertain"]["build_id"], "season": season, "as_of": as_of})}
    if builds["verify_exception"]:
        exceptions = {r["kind"]: r["n"] for r in _rows(conn, """
            SELECT kind, SUM(count) AS n FROM verify.exception WHERE build_id = :b GROUP BY kind""",
            {"b": builds["verify_exception"]["build_id"]})}
    data = {
        "coverage": {"final_games": final_games, "official_raw_games": len(raws), "calc_games": calc_games,
                     "final_games_basis": "current_schedule_unversioned" if as_of is None else "unknown_at_as_of"},
        "collection": {"policy": COLLECTION_POLICY, "fetch_log": fetch,
                       "official_fetched_at_max": _iso(max((r["fetched_at"] for r in raws), default=None))},
        "builds": {k: (None if b is None else {"build_id": b["build_id"], "calc_rule": b["calc_rule"],
                                               "loaded_at": _iso(b["loaded_at"])}) for k, b in builds.items()},
        "verification": {"by_metric": by_metric}, "outs_uncertain": outs_uncertain, "exceptions": exceptions,
        "kbo_verified": 0 if not kbo_source_count(conn, season, as_of) else None,  # KBO 원본 대조가 생기면 그때 센다
    }
    return {"data": data, "meta": meta(conn, season, as_of, raws, builds)}
