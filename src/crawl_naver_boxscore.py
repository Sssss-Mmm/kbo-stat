"""
네이버 경기 기록(박스스코어) 응답 원본을 그대로 보존한다.

    data/raw/naver/record/{season}/{GameId}/{fetched_at}.json
    data/raw/naver/record/ingest_log.csv        수집 시도마다 한 줄(성공·실패 모두)

파일 하나 = 수집 한 번. 기존 파일은 절대 덮어쓰지 않는다 — 다시 받으면 새 시각의
파일이 하나 더 생기고, 해석(build_naver_box_games.py)은 가장 최근 파일을 쓴다.
쓰기는 같은 폴더의 임시 파일 → os.link(이미 있으면 실패) 라 중간에 죽어도 반쪽 JSON 이 남지 않고,
동시에 같은 이름으로 저장해도 먼저 쓴 원본이 바뀌지 않는다.
요청이 실패하면 아무 파일도 만들지 않는다.

봉투(envelope) 형식:
    {"source": "naver_boxscore", "url", "game_id", "season", "fetched_at"(UTC ISO),
     "sha256"(payload 의 정렬 JSON 해시), "payload"(API result 그대로)}

출처 표기는 "naver_boxscore" 다. KBO 공식 사이트 원본과의 교차검증(kbo_*)은 별도 단계다.

Usage:
    python src/crawl_naver_boxscore.py --season 2025 --games-file games.csv   # GameId 열
    python src/crawl_naver_boxscore.py --season 2025 --game 20250719HHKT0
    python src/crawl_naver_boxscore.py --season 2025 --all-final               # 일정의 완료 경기 전부
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import json
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from crawl_naver_pitch_zones import API_BASE, PAUSE_SECONDS, RAW_DIR, SCHEDULE_DIR, get_json, naver_game_id
import naver_access
from naver_box_parse import SOURCE, check_envelope, payload_hash

RECORD_DIR = RAW_DIR / "record"
LOG_FIELDS = ["run_id", "fetched_at", "season", "game_id", "status", "path", "sha256", "error"]
FINAL_STATUS = "4"  # recordData.gameInfo.statusCode — 경기 종료
REQUIRED_KEYS = ("gameInfo", "pitchersBoxscore", "teamPitchingBoxscore", "battersBoxscore")
RETRIES = 2  # 요청 실패 시 다시 묻는 횟수(경기당 최대 3번 요청)
GAME_ID = re.compile(r"\d{8}[A-Z]{4}\d")


def record_url(game_id: str, season: int) -> str:
    return f"{API_BASE}/schedule/games/{naver_game_id(game_id, season)}/record"


def fetch_record(game_id: str, season: int) -> dict:
    """네이버 record API result 전체(recordData 포함). 실패하면 예외."""
    nid = naver_game_id(game_id, season)
    return get_json(record_url(game_id, season), referer=f"https://m.sports.naver.com/game/{nid}/record")


def game_dir(game_id: str, season: int, root: Path | None = None) -> Path:
    """GameId 는 경로가 되므로 KBO 형식(예: 20250719HHKT0)만 받는다 — '../'·절대경로로 원본 폴더를 벗어나지 않게."""
    if not GAME_ID.fullmatch(str(game_id)) or not 1982 <= int(season) <= 2100:
        raise ValueError(f"잘못된 GameId/season: {game_id!r} {season!r}")
    return (root or RECORD_DIR) / str(int(season)) / game_id


def saved_files(game_id: str, season: int, root: Path | None = None) -> list[Path]:
    """이 경기의 원본 파일들, 오래된 것부터(파일명이 UTC 시각이라 이름순 = 시간순)."""
    return sorted(game_dir(game_id, season, root).glob("*.json"))


def has_boxscore(payload) -> bool:
    """완료 경기 박스스코어인가: 종료 상태 + 필수 객체 + 두 팀 이름 + 양 팀 투수·타자 줄이 하나 이상.
    빈 객체만 온 일시적 응답을 '이미 받음'으로 남기지 않게 한다."""
    record = payload.get("recordData") if isinstance(payload, dict) else None
    if not isinstance(record, dict) or not all(isinstance(record.get(k), dict) for k in REQUIRED_KEYS):
        return False
    info = record["gameInfo"]
    # 진행 중 경기의 부분 기록을 최종본처럼 남기지 않는다 — 2025 원본 720개 모두 statusCode "4"(종료).
    return info.get("statusCode") == FINAL_STATUS and bool(info.get("aName") and info.get("hName")) and all(
        isinstance(record[box].get(side), list) and record[box][side]
        for box in ("pitchersBoxscore", "battersBoxscore") for side in ("away", "home"))


def latest_problem(game_id: str, season: int, root: Path | None = None) -> str | None:
    """가장 최근 원본이 쓸 수 있는가. 쓸 수 없으면 이유(문자열) — 해시·출처·경로·종료 상태를 본다."""
    path = saved_files(game_id, season, root)[-1]
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        check_envelope(envelope, path.relative_to(root or RECORD_DIR).as_posix())
    except (ValueError, KeyError, AttributeError) as exc:
        return f"{path.name}: {exc}"
    return None if has_boxscore(envelope["payload"]) else f"{path.name}: 완료 박스스코어 아님"


def save_record(game_id: str, season: int, payload: dict, url: str,
                fetched_at: datetime | None = None, root: Path | None = None) -> tuple[str, Path | None, str]:
    """원본을 새 파일로 남긴다. (status, path, sha256). status: saved | unchanged.

    가장 최근 파일과 payload 해시가 같으면 새로 쓰지 않는다(unchanged).
    박스스코어가 없는 응답은 저장하지 않는다(ValueError) — 빈 원본이 '이미 받음'으로 남아
    재수집을 막지 않게, 모든 저장 경로(collect·투구 크롤러의 keep)가 여기를 지난다.
    """
    if not has_boxscore(payload):
        raise ValueError(f"박스스코어 없는 응답 — 저장 안 함 ({game_id})")
    fetched_at = fetched_at or datetime.now(timezone.utc)
    digest = payload_hash(payload)
    existing = saved_files(game_id, season, root)
    try:
        latest = json.loads(existing[-1].read_text(encoding="utf-8")) if existing else None
    except ValueError:  # 읽을 수 없는 최신 파일 — '같음'으로 볼 수 없으니 새 파일로 남긴다
        latest = None
    # 최신 파일의 payload 가 저장된 해시와 맞을 때만 '같음'으로 본다 — 손상된 파일이면 새 정상 원본을 따로 남긴다.
    if latest and latest.get("sha256") == digest and payload_hash(latest.get("payload")) == digest:
        return "unchanged", existing[-1], digest
    folder = game_dir(game_id, season, root)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{fetched_at.strftime('%Y%m%dT%H%M%S%fZ')}.json"
    envelope = {"source": SOURCE, "url": url, "game_id": game_id, "season": season,
                "fetched_at": fetched_at.isoformat().replace("+00:00", "Z"), "sha256": digest, "payload": payload}
    fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(envelope, handle, ensure_ascii=False)
        os.link(tmp, target)  # 이미 있으면 FileExistsError — 동시 실행에서도 기존 원본을 덮어쓰지 않는다
    finally:
        Path(tmp).unlink(missing_ok=True)
    return "saved", target, digest


def append_log(row: dict, root: Path | None = None) -> None:
    path = (root or RECORD_DIR) / "ingest_log.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)  # 동시 실행에서도 헤더 한 번·행 단위로 쓰게(닫으면 풀린다)
        writer = csv.DictWriter(handle, fieldnames=LOG_FIELDS)
        if handle.seek(0, os.SEEK_END) == 0:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in LOG_FIELDS})


def keep(game_id: str, season: int, payload: dict, run_id: str, root: Path | None = None) -> str:
    """이미 받은 payload 를 보존하고 로그를 남긴다. 저장 실패도 로그로 남기고 예외는 올리지 않는다."""
    now = datetime.now(timezone.utc)
    row = {"run_id": run_id, "fetched_at": now.isoformat().replace("+00:00", "Z"), "season": season, "game_id": game_id}
    try:
        status, path, digest = save_record(game_id, season, payload, record_url(game_id, season), now, root)
        row.update(status=status, path=str(path.relative_to(root or RECORD_DIR)), sha256=digest)
    except Exception as exc:  # noqa: BLE001 — 보존 실패가 호출자(투구 크롤링)를 깨지 않게
        row.update(status="error", error=f"save: {exc}")
    append_log(row, root)
    return row["status"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def collect(game_ids: list[str], season: int, refresh: bool = False, pause: float = PAUSE_SECONDS,
            root: Path | None = None, retries: int = RETRIES) -> dict[str, int]:
    """경기마다 받아 보존한다. 이미 파일이 있으면 refresh 가 아닌 한 요청하지 않는다.

    요청 실패·빈 응답은 retries 번까지 다시 묻는다(pause×2, ×4 … 대기). 시도마다 로그를 남기고
    (중간 실패 retry, 마지막 실패 error) 한 경기 실패로 나머지를 멈추지 않는다.
    """
    for game_id in game_ids:  # 형식이 틀린 GameId 가 하나라도 있으면 요청 전에 멈춘다
        game_dir(game_id, season, root)
    run_id = uuid.uuid4().hex[:12]
    counts: dict[str, int] = {}
    for i, game_id in enumerate(game_ids):
        problem = None if refresh or not saved_files(game_id, season, root) else latest_problem(game_id, season, root)
        if not refresh and saved_files(game_id, season, root) and problem is None:
            status = "skipped_existing"
            append_log({"run_id": run_id, "fetched_at": _now(), "season": season, "game_id": game_id,
                        "status": status}, root)
        else:
            if problem:  # 손상·미완료 원본만 있으면 지우지 않고 남긴 채 다시 받는다
                append_log({"run_id": run_id, "fetched_at": _now(), "season": season, "game_id": game_id,
                            "status": "invalid_existing", "error": problem}, root)
            for attempt in range(retries + 1):
                try:
                    payload = fetch_record(game_id, season)
                    if not has_boxscore(payload):
                        raise RuntimeError("박스스코어 없는 응답")
                except Exception as exc:  # noqa: BLE001 — 한 경기 실패로 나머지를 멈추지 않는다
                    status = "error" if attempt == retries else "retry"
                    append_log({"run_id": run_id, "fetched_at": _now(), "season": season, "game_id": game_id,
                                "status": status, "error": f"fetch attempt {attempt + 1}: {exc}"}, root)
                    if status == "retry":
                        time.sleep(pause * 2 ** (attempt + 1))
                    continue
                status = keep(game_id, season, payload, run_id, root)
                break
            if i < len(game_ids) - 1:
                time.sleep(pause)
        counts[status] = counts.get(status, 0) + 1
    print(f"[naver-box] run={run_id} season={season} " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return counts


def final_games(season: int) -> list[str]:
    schedule = pd.read_csv(SCHEDULE_DIR / f"kbo_schedule_{season}.csv", encoding="utf-8-sig")
    return sorted(schedule.loc[schedule["status"].eq("final"), "GameId"].dropna().astype(str))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--game", action="append")
    group.add_argument("--games-file", type=Path, help="GameId 열이 있는 CSV")
    group.add_argument("--all-final", action="store_true")
    parser.add_argument("--refresh", action="store_true", help="이미 받은 경기도 다시 받아 새 파일로 남긴다")
    parser.add_argument("--pause", type=float, default=PAUSE_SECONDS)
    args = parser.parse_args()
    if not naver_access.allowed():
        naver_access.skip("box score backfill")
        return
    if args.all_final:
        games = final_games(args.season)
    elif args.games_file:
        games = sorted(pd.read_csv(args.games_file, encoding="utf-8-sig")["GameId"].dropna().astype(str).unique())
    else:
        games = args.game
    counts = collect(games, args.season, refresh=args.refresh, pause=args.pause)
    if counts.get("error"):
        raise SystemExit(f"[naver-box] {counts['error']} 경기 수집 실패 — ingest_log.csv 참고")


if __name__ == "__main__":
    main()
