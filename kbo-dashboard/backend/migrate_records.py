"""
P1-A: 원본 JSON·외부 기록·자체 계산·대조 결과를 ref/ingest/official/derived/verify 스키마에 적재한다.

입력(이미 만들어진 파일만 읽는다 — 수집·계산은 src/ 쪽):
  data/raw/naver/record/{season}/{GameId}/*.json, record/ingest_log.csv
  data/raw/kbo_official/kbo_schedule_{season}.csv, kbo_team_rank_{season}.csv (--reference-season: 일정·순위표만)
  data/processed/naver_box_{pitchers,batters}_{season}.csv
  data/processed/kbo_player_games_{season}.csv, kbo_player_games_check_{season}.csv, kbo_outs_uncertain_{season}.csv,
  kbo_verify_exceptions_{season}.csv

재실행 안전(멱등):
  ingest·official   불변. 같은 원본은 ON CONFLICT DO NOTHING — 다시 받은 원본은 새 행으로 쌓이고 옛 행은 남는다.
  ref               경기·선수 기준 정보는 최신 값으로 갱신, 선수 이름은 이력 테이블에 쌓는다.
  derived·verify    입력 CSV 한 벌 = 빌드(내용 해시, CheckedAt 제외). 행은 빌드별 불변 — 같은 CSV 는 같은 빌드라
                    다시 넣지 않고, 입력이 바뀌면 새 빌드가 쌓이며 옛 빌드(사라진 행 포함)는 그대로 남는다.
                    현재 값은 *_current 뷰(시즌별 가장 최근 적재 빌드), 과거 시점은 derived.build.loaded_at 으로 고른다.
public 스키마의 기존 테이블은 읽지도 쓰지도 않는다. DDL 포함 전체가 한 트랜잭션이라 중간에 실패하면 남는 게 없다.
원본 JSON 은 적재 전에 해시를 다시 계산해 저장된 sha256 과 다르면 멈춘다.

Usage (backend 폴더에서, DATABASE_URL 은 .env):
    ./venv/bin/python migrate_records.py --season 2025
    ./venv/bin/python migrate_records.py $(printf -- '--reference-season %s ' $(seq 2001 2026))
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from models.records import (SCHEMAS, Build, FetchLog, Game, GameBatterLine, GamePitcherLine, OutsUncertain, Player,
                            PlayerGame, PlayerGameCheck, PlayerName, RawRecord, RecordsBase, ScheduleGame,
                            SeasonStanding, VerifyException)

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT / "src"))
import naver_box_parse as nbp  # noqa: E402 — 수집·가공과 같은 해시·무결성·파서(표준 라이브러리만 쓴다)

SOURCE = nbp.SOURCE
payload_hash = nbp.payload_hash
CHUNK = 500
# 시점별 조회용: 외부 기록은 원본이 여러 번 쌓이므로 '경기마다 가장 최근 원본'의 줄만 보이는 뷰를 둔다
# (PostgreSQL 전용). 선수별 최신 줄을 고르면 새 원본에서 빠진 선수가 옛 원본에서 계속 보인다(Codex P1-D).
VIEWS = {
    f"official.{name}_current": f"""
        SELECT l.* FROM official.{name} l
        JOIN (SELECT DISTINCT ON (game_id) raw_file FROM ingest.raw_record WHERE source = '{SOURCE}'
              ORDER BY game_id, fetched_at DESC, raw_file DESC) latest ON latest.raw_file = l.raw_file"""
    for name in ("game_pitcher_line", "game_batter_line")
}
# 빌드 테이블은 시즌별 가장 최근에 처음 적재된 빌드만 — 새 빌드에서 사라진 행은 현재 뷰에서 빠진다.
VIEWS.update({
    f"{table}_current": f"""
        SELECT t.* FROM {table} t WHERE t.build_id = (
            SELECT b.build_id FROM derived.build b WHERE b.kind = '{kind}' AND b.season = t.season
            ORDER BY b.loaded_at DESC, b.build_id DESC LIMIT 1)"""
    for table, kind in (("derived.player_game", "player_game"), ("verify.player_game_check", "player_game_check"),
                        ("verify.outs_uncertain", "outs_uncertain"), ("verify.exception", "verify_exception"),
                        ("official.schedule_game", "schedule"), ("official.season_standing", "season_standing"))
})


def _records(df: pd.DataFrame, columns: dict[str, str]) -> list[dict]:
    """CSV 열 → DB 열 이름으로 바꾸고 NaN 을 None 으로."""
    out = df[list(columns)].rename(columns=columns)
    return out.astype(object).where(out.notna(), None).to_dict("records")


def _ts(value):
    return None if value is None else datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _date(value):
    return None if value is None else datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _read(path: Path, season: int, **kwargs) -> pd.DataFrame:
    """CSV 를 읽고 모든 행이 요청 시즌인지 본다(Season 열과 GameId 앞 4자리). 하나라도 다르면 멈춘다."""
    df = pd.read_csv(path, encoding="utf-8-sig", **kwargs)
    game_ids = df["GameId"].dropna().astype(str)
    if df["Season"].ne(season).any() or not game_ids.str.startswith(str(season)).all():
        raise ValueError(f"{path.name}: --season {season} 이 아닌 행이 있다")
    return df


def upsert(conn, model, rows: list[dict], update: bool) -> None:
    """키 충돌 시 update=False 면 그대로 두고(불변), True 면 키 외 열을 새 값으로."""
    if not rows:
        return
    insert = pg_insert if conn.dialect.name == "postgresql" else sqlite_insert
    keys = [c.name for c in model.__table__.primary_key]
    for start in range(0, len(rows), CHUNK):
        stmt = insert(model.__table__).values(rows[start:start + CHUNK])
        if update:
            cols = [c for c in rows[0] if c not in keys]
            stmt = stmt.on_conflict_do_update(index_elements=keys, set_={c: stmt.excluded[c] for c in cols})
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=keys)
        conn.execute(stmt)


def ensure_schema(conn) -> None:
    if conn.dialect.name == "postgresql":
        for schema in SCHEMAS:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
    RecordsBase.metadata.create_all(conn)
    if conn.dialect.name == "postgresql":
        # P2-A 에서 더한 열 — create_all 은 있는 테이블에 열을 추가하지 않는다(옛 빌드는 NULL = 연결 정보 없음).
        conn.execute(text("ALTER TABLE derived.build ADD COLUMN IF NOT EXISTS basis_build_id VARCHAR(16)"))
        for name, body in VIEWS.items():
            conn.execute(text(f"CREATE OR REPLACE VIEW {name} AS {body}"))


def load_games(conn, data: Path, season: int) -> None:
    df = _read(data / "raw" / "kbo_official" / f"kbo_schedule_{season}.csv", season).dropna(subset=["GameId"])
    df["GameId"] = df["GameId"].astype(str)
    rows = _records(df, {"GameId": "game_id", "Season": "season", "Date": "game_date", "away_team": "away_team",
                         "home_team": "home_team", "status": "status", "away_score": "away_score",
                         "home_score": "home_score", "Ballpark": "ballpark"})
    for r in rows:
        r.update(game_date=_date(r["game_date"]), dh=int(r["game_id"][12]), source="kbo_schedule",
                 away_score=None if r["away_score"] is None else int(r["away_score"]),
                 home_score=None if r["home_score"] is None else int(r["home_score"]))
    upsert(conn, Game, rows, update=True)


def load_raw(conn, data: Path, season: int) -> dict[str, dict]:
    """원본을 무결성 재검증 후 적재하고, 원본 파일 → 봉투(가공 CSV·대조 CSV 검증용)를 돌려준다."""
    root = data / "raw" / "naver" / "record"
    rows, envelopes = [], {}
    for path in sorted((root / str(season)).glob("*/*.json")):
        env = json.loads(path.read_text(encoding="utf-8"))
        rel = path.relative_to(root).as_posix()
        nbp.check_envelope(env, rel)
        if env["season"] != season:
            raise ValueError(f"원본 무결성 불일치 — {rel} (시즌)")
        envelopes[rel] = env
        rows.append(dict(raw_file=rel, source=env["source"], season=env["season"], game_id=env["game_id"],
                         url=env["url"], fetched_at=_ts(env["fetched_at"]), sha256=env["sha256"],
                         payload=env["payload"]))
    upsert(conn, RawRecord, rows, update=False)
    log = root / "ingest_log.csv"
    if log.exists():
        df = pd.read_csv(log, dtype=str)
        df = df[df["season"] == str(season)]
        rows = _records(df, {c: c for c in ["run_id", "fetched_at", "game_id", "status", "season", "path",
                                            "sha256", "error"]})
        for r in rows:
            r.update(fetched_at=_ts(r["fetched_at"]), season=int(r["season"]))
        upsert(conn, FetchLog, rows, update=False)
    return envelopes


LINE = {"RawFile": "raw_file", "PlayerId": "player_id", "Source": "source", "Season": "season", "GameId": "game_id",
        "FetchedAt": "fetched_at", "Sha256": "sha256", "GameStatusCode": "game_status_code", "Side": "side",
        "Team": "team", "Player": "player", "TeamSumMismatch": "team_sum_mismatch"}
PITCHER = {**LINE, "Order": "ord", "IP": "ip", "Outs": "outs", "BF": "bf", "AB": "ab", "H": "h", "HR": "hr",
           "BB": "bb", "BBHP": "bbhp", "SO": "so", "R": "r", "ER": "er", "NP": "np", "Decision": "decision"}
BATTER = {**LINE, "BatOrder": "bat_order", "Pos": "pos", "AB": "ab", "H": "h", "HR": "hr", "BB": "bb", "SO": "so",
          "R": "r", "RBI": "rbi", "SB": "sb", "IBB": "ibb"}


TEXT_COLUMNS = {"GameStatusCode": str, "IP": str, "Pos": str, "Decision": str, "TeamSumMismatch": str}


def _parsed(envelopes: dict[str, dict], rels, index: int, columns: dict[str, str]) -> list[dict]:
    """원본들을 같은 파서로 풀어 DB 열 이름의 행으로. CSV 와 같은 꼴(글자 열은 글자, 빈 값은 None)로 맞춘다."""
    frame = pd.DataFrame([row for rel in rels for row in nbp.parse_envelope(envelopes[rel], rel)[index]],
                         columns=list(columns))
    for c in TEXT_COLUMNS.keys() & columns.keys():  # CSV 는 이 열을 글자로 읽는다 — 빈 값은 빈 값 그대로
        frame[c] = frame[c].map(lambda v: v if v is None or pd.isna(v) else str(v))
    return _records(frame, columns)


def load_official(conn, data: Path, season: int, envelopes: dict[str, dict]) -> list[tuple[int, str]]:
    """원본 **모든 판본**을 같은 파서(nbp.parse_envelope)로 풀어 적재한다 — 빈 DB 를 다시 만들어도 옛 원본의
    줄이 남아야 as_of 조회가 그 시점 원본을 쓸 수 있다(Codex P2-B 3차).
    가공 CSV 는 경기별 최신 원본을 푼 결과와 전 필드·전 행이 같아야 한다(다르면 멈춘다)."""
    names = []
    for index, (model, file, columns) in enumerate(((GamePitcherLine, "pitchers", PITCHER),
                                                    (GameBatterLine, "batters", BATTER))):
        name = f"naver_box_{file}_{season}.csv"
        df = _read(data / "processed" / name, season, dtype=TEXT_COLUMNS, keep_default_na=False,
                   na_values=[""]).fillna({"TeamSumMismatch": "", "Decision": ""})
        rows = _records(df, columns)
        # 대조 기대값 = 경기마다 가장 최근 원본(build_naver_box_games 와 같은 선택)을 다시 푼 행 전부.
        latest = {}
        for rel in sorted(envelopes):
            latest[envelopes[rel]["game_id"]] = rel
        key = lambda r: (r["raw_file"], r["player_id"])  # noqa: E731
        if sorted(rows, key=key) != sorted(_parsed(envelopes, latest.values(), index, columns), key=key):
            raise ValueError(f"{name}: 원본을 다시 푼 값과 다르다(값·행 수)")
        every = _parsed(envelopes, sorted(envelopes), index, columns)  # 옛 판본 포함
        for r in every:
            r["fetched_at"] = _ts(r["fetched_at"])
        upsert(conn, model, every, update=False)
        names += list(zip(df["PlayerId"].astype(int), df["Player"]))
    return names


GAMES = {"CalcRule": "calc_rule", "Role": "role", "PlayerId": "player_id", "GameId": "game_id", "Season": "season",
         "Date": "game_date", "DH": "dh", "Player": "player", "Team": "team", "Opponent": "opponent",
         "HomeAway": "home_away", "PA": "pa", "AB": "ab", "H": "h", "2B": "b2", "3B": "b3", "HR": "hr", "BB": "bb",
         "HBP": "hbp", "SF": "sf", "SH": "sh", "SO": "so", "BF": "bf", "ResultUnknown": "result_unknown",
         "PAUncertain": "pa_uncertain", "AttributionUncertain": "attribution_uncertain",
         "PAComplete": "pa_complete", "StatsComplete": "stats_complete", "Outs": "outs",
         "OutsComplete": "outs_complete"}
CHECK = {"CalcRule": "calc_rule", "ExternalRawFile": "external_raw_file", "Role": "role", "PlayerId": "player_id",
         "Metric": "metric", "Season": "season", "GameId": "game_id", "Player": "player", "CalcValue": "calc_value",
         "CalcProven": "calc_proven", "ExternalValue": "external_value", "ExternalSource": "external_source",
         "ExternalFetchedAt": "external_fetched_at", "Status": "status", "CheckedAt": "checked_at"}
UNCERTAIN = {"CalcRule": "calc_rule", "GameId": "game_id", "PlayerId": "player_id", "Season": "season",
             "Date": "game_date", "Player": "player", "Team": "team", "Halves": "halves", "Reasons": "reasons",
             "LastResults": "last_results", "LastOuts": "last_outs", "OutsRaw": "outs_raw", "NaverOuts": "naver_outs",
             "NaverStatus": "naver_status", "ExternalFetchedAt": "external_fetched_at",
             "ExternalRawFile": "external_raw_file", "CheckedAt": "checked_at"}


def register_build(conn, kind: str, season: int, df: pd.DataFrame, source: Path, basis: str | None = None) -> str:
    """CSV 내용(대조 시각 CheckedAt 제외)과 기준 계산 빌드(basis)의 해시를 빌드 ID 로 등록한다.
    이미 있으면 그대로(처음 적재 시각 유지). 같은 대조 CSV 라도 기준 계산 빌드가 다르면 다른 빌드다."""
    rules = df["CalcRule"].dropna().unique() if "CalcRule" in df else []
    if len(rules) > 1:
        raise ValueError(f"{source.name}: 계산 규칙 판본이 섞여 있다 {list(rules)}")
    body = df.drop(columns=["CheckedAt"], errors="ignore").to_csv(index=False)
    build_id = hashlib.sha256(f"{kind}\n{basis or ''}\n{body}".encode()).hexdigest()[:16]
    upsert(conn, Build, [dict(build_id=build_id, kind=kind, season=season, calc_rule=rules[0] if len(rules) else "",
                              source_file=source.name, row_count=len(df), basis_build_id=basis)], update=False)
    return build_id


EXCEPTION = {"RowNo": "row_no", "CalcRule": "calc_rule", "Season": "season", "GameId": "game_id", "Kind": "kind",
             "Role": "role", "PlayerId": "player_id", "Player": "player", "Count": "count", "Detail": "detail",
             "CheckedAt": "checked_at"}


def _ints(rows: list[dict], *cols: str) -> None:
    for r in rows:
        for c in cols:
            if r.get(c) is not None:
                r[c] = int(r[c])


def load_derived(conn, data: Path, season: int) -> tuple[list[tuple[int, str]], str]:
    path = data / "processed" / f"kbo_player_games_{season}.csv"
    df = _read(path, season, dtype={"GameId": str})
    if "CalcRule" not in df:
        raise ValueError("kbo_player_games CSV 에 CalcRule 이 없다 — build_player_games.py 로 다시 만든다")
    build_id = register_build(conn, "player_game", season, df, path)
    rows = _records(df, GAMES)
    for r in rows:
        r.update(game_date=_date(r["game_date"]), build_id=build_id)
    _ints(rows, "pa", "ab", "h", "b2", "b3", "hr", "bb", "hbp", "sf", "sh", "so", "bf", "outs", "dh",
          "result_unknown", "pa_uncertain", "attribution_uncertain")
    upsert(conn, PlayerGame, rows, update=False)
    return list(zip(df["PlayerId"].astype(int), df["Player"])), build_id


def _check_raw_refs(rows: list[dict], envelopes: dict[str, dict], name: str, season: int) -> None:
    """대조 행이 가리키는 원본이 같은 경기·시즌·출처·수집시각인지. 원본이 없는 행(unverified)은 참조도 없어야 한다."""
    for r in rows:
        env = envelopes.get(r["external_raw_file"])
        if r["external_raw_file"] is None and r["external_fetched_at"] is None:
            continue
        if (env is None or env["game_id"] != r["game_id"] or env["season"] != season
                or _ts(env["fetched_at"]) != r["external_fetched_at"]
                or env["source"] != r.get("external_source", SOURCE)):
            raise ValueError(f"{name}: {r['game_id']} 행이 다른 원본({r['external_raw_file']})을 가리킨다")


def load_verify(conn, data: Path, season: int, envelopes: dict[str, dict], basis: str) -> None:
    path = data / "processed" / f"kbo_player_games_check_{season}.csv"
    df = _read(path, season, dtype={"GameId": str})
    build_id = register_build(conn, "player_game_check", season, df, path, basis)
    rows = _records(df, CHECK)
    for r in rows:
        r.update(external_fetched_at=_ts(r["external_fetched_at"]), checked_at=_ts(r["checked_at"]), build_id=build_id)
    _ints(rows, "calc_value", "external_value")
    _check_raw_refs(rows, envelopes, path.name, season)
    upsert(conn, PlayerGameCheck, rows, update=False)
    path = data / "processed" / f"kbo_outs_uncertain_{season}.csv"
    df = _read(path, season, dtype={"GameId": str})
    build_id = register_build(conn, "outs_uncertain", season, df, path, basis)
    rows = _records(df, UNCERTAIN)
    for r in rows:
        r.update(game_date=_date(r["game_date"]), external_fetched_at=_ts(r["external_fetched_at"]),
                 checked_at=_ts(r["checked_at"]), build_id=build_id)
    _ints(rows, "outs_raw", "naver_outs")
    _check_raw_refs(rows, envelopes, path.name, season)
    upsert(conn, OutsUncertain, rows, update=False)
    path = data / "processed" / f"kbo_verify_exceptions_{season}.csv"
    df = _read(path, season, dtype={"GameId": str}, keep_default_na=False, na_values=[""])
    build_id = register_build(conn, "verify_exception", season, df, path, basis)
    rows = _records(df.reset_index(names="RowNo"), EXCEPTION)
    for r in rows:
        r.update(checked_at=_ts(r["checked_at"]), build_id=build_id, role=r["role"] or None)
    _ints(rows, "row_no", "player_id", "count")
    upsert(conn, VerifyException, rows, update=False)


REFERENCE_SOURCE = "kbo_site_crawl"  # KBO 공식 사이트 자동 수집분(2026-10-24 이후 중단, 이용 승인 확인 전)


def _collected_at(path: Path) -> datetime:
    """원본 CSV 를 마지막으로 받은 시각(파일 수정 시각, UTC)."""
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def schedule_status(raw: str, note, away, home) -> tuple[str, str | None]:
    """원본 status·Note → (final|tie|canceled|scheduled, 취소 사유). 원본 status 는 final/scheduled 둘뿐이고,
    취소는 scheduled + Note(우천취소 등), 무승부는 final + 같은 점수로 온다."""
    note = None if note is None or (isinstance(note, float) and pd.isna(note)) or str(note).strip() in ("", "-") else str(note)
    if raw == "final":
        return ("tie" if away == home else "final"), None
    if note:
        return "canceled", note
    return "scheduled", None


def _nonempty(df: pd.DataFrame, path: Path) -> pd.DataFrame | None:
    """0행(헤더만) 원본은 빌드로 등록하지 않는다 — 빈 빌드가 최신 빌드가 되어 기존 자료를 가리지 않게."""
    if df.empty:
        print(f"[skip:input] 0행 {path.name} — 빌드 등록 안 함, 기존 빌드 유지")
        return None
    return df


def load_reference(conn, data: Path, season: int) -> dict[str, int]:
    """시즌 일정(취소 포함)과 원본 시즌 순위표를 빌드 단위로 적재한다. 파일이 없거나 0행이면 건너뛴다(기존 빌드 유지)."""
    loaded = {}
    path = data / "raw" / "kbo_official" / f"kbo_schedule_{season}.csv"
    if path.exists() and (df := _nonempty(_read(path, season, dtype={"GameId": str}), path)) is not None:
        build_id = register_build(conn, "schedule", season, df, path)
        at = _collected_at(path)
        rows = []
        for i, r in enumerate(df.astype(object).where(df.notna(), None).to_dict("records")):
            away, home = (None if r[k] is None else int(r[k]) for k in ("away_score", "home_score"))
            status, reason = schedule_status(r["status"], r["Note"], away, home)
            gid = r["GameId"]
            rows.append(dict(build_id=build_id, row_no=i, season=season, game_date=_date(r["Date"]), game_time=r["Time"],
                             weekday=r["Weekday"], away_team=r["away_team"], home_team=r["home_team"], away_score=away,
                             home_score=home, status=status, status_raw=r["status"], cancel_reason=reason,
                             ballpark=r["Ballpark"], game_id=gid, dh=int(gid[12]) if gid else None,
                             source=REFERENCE_SOURCE, collected_at=at))
        upsert(conn, ScheduleGame, rows, update=False)
        loaded["schedule"] = len(rows)
    path = data / "raw" / "kbo_official" / f"kbo_team_rank_{season}.csv"
    if path.exists() and (df := _nonempty(pd.read_csv(path, encoding="utf-8-sig"), path)) is not None:
        if df["Season"].ne(season).any():
            raise ValueError(f"{path.name}: --reference-season {season} 이 아닌 행이 있다")
        build_id = register_build(conn, "season_standing", season, df, path)
        at = _collected_at(path)
        rows = [dict(build_id=build_id, team=r["팀명"], season=season, rank=r["순위"], games=r["경기"], wins=r["승"],
                     losses=r["패"], draws=r["무"], pct=r["승률"], games_behind=r["게임차"], last10=r.get("최근10경기"),
                     streak=r.get("연속"), home_record=r.get("홈"), away_record=r.get("방문"),
                     source=REFERENCE_SOURCE, collected_at=at)
                for r in df.astype(object).where(df.notna(), None).to_dict("records")]
        upsert(conn, SeasonStanding, rows, update=False)
        loaded["season_standing"] = len(rows)
    return loaded


def load_players(conn, names: list[tuple[int, str]]) -> None:
    """뒤에 온 이름(외부 기록)이 ref.player.name 이 된다. 이름 이력은 출처와 함께 쌓는다."""
    latest = {pid: name for pid, name in names if isinstance(name, str)}
    upsert(conn, Player, [{"player_id": pid, "name": n} for pid, n in latest.items()], update=True)


def load_season(conn, season: int, data: Path = DATA) -> None:
    ensure_schema(conn)
    load_games(conn, data, season)
    envelopes = load_raw(conn, data, season)
    calc_names, calc_build = load_derived(conn, data, season)
    box_names = load_official(conn, data, season, envelopes)
    load_verify(conn, data, season, envelopes, calc_build)
    load_players(conn, calc_names + box_names)
    upsert(conn, PlayerName, [{"player_id": p, "name": n, "source": "pitch_relay"} for p, n in set(calc_names)
                              if isinstance(n, str)], update=False)
    upsert(conn, PlayerName, [{"player_id": p, "name": n, "source": SOURCE} for p, n in set(box_names)
                              if isinstance(n, str)], update=False)


def counts(conn) -> dict[str, int]:
    return {t.fullname: conn.execute(select(func.count()).select_from(t)).scalar_one()
            for t in RecordsBase.metadata.sorted_tables}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, action="append", default=[])
    parser.add_argument("--reference-season", type=int, action="append", default=[],
                        help="일정·시즌 순위표만 적재(official.schedule_game·season_standing)")
    args = parser.parse_args()
    if not args.season and not args.reference_season:
        parser.error("--season 또는 --reference-season 이 필요하다")
    from database import engine  # .env 의 DATABASE_URL — 테스트는 이 모듈을 엔진 없이 쓴다

    try:
        with engine.begin() as conn:
            for season in args.season:
                load_season(conn, season)
            ensure_schema(conn)
            for season in args.reference_season:
                print(f"[records] reference {season}: {load_reference(conn, DATA, season)}")
            for name, n in counts(conn).items():
                print(f"[records] {name}: {n}")
    except Exception as exc:
        print(f"[records] 적재 실패 — 전체 롤백: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
