"""운영 DB 백업 보관 정리. backup_kbo_db.sh 가 **새 백업 검증에 성공한 뒤에만** 부른다.

남기는 것(합집합):
  - 일간: 가장 최근 N 일(날짜별 가장 늦은 백업 하나씩)
  - 주간: 가장 최근 N 주(ISO 주별 가장 늦은 백업 하나씩)
  - 월간: 가장 최근 N 개월(월별 가장 늦은 백업 하나씩)
  - --protect 로 준 파일(방금 만든 백업)
이름이 `kbo-YYYYMMDD-HHMMSS.dump` 가 아닌 파일은 건드리지 않는다. 지우는 건 그 dump 와 짝 `.sha256` 뿐이다.

사용:
    python3 scripts/kbo_backup_retention.py DIR --protect FILE [--keep-daily 14 --keep-weekly 8 --keep-monthly 6] [--dry-run]
    python3 scripts/kbo_backup_retention.py --selftest
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

NAME = re.compile(r"^kbo-(\d{8})-(\d{6})\.dump$")


def backups(directory: Path) -> list[tuple[datetime, Path]]:
    out = []
    for path in directory.iterdir():
        m = NAME.match(path.name)
        if m and path.is_file():
            out.append((datetime.strptime(m[1] + m[2], "%Y%m%d%H%M%S"), path))
    return sorted(out, reverse=True)  # 최신 먼저


def keep_set(items: list[tuple[datetime, Path]], daily: int, weekly: int, monthly: int) -> set[Path]:
    keep: set[Path] = set()
    for n, key in ((daily, lambda t: t.date()), (weekly, lambda t: t.isocalendar()[:2]), (monthly, lambda t: (t.year, t.month))):
        seen: list = []
        for ts, path in items:  # 최신 먼저라 구간별 첫 파일이 그 구간의 가장 늦은 백업
            k = key(ts)
            if k in seen:
                continue
            if len(seen) >= n:
                break
            seen.append(k)
            keep.add(path)
    return keep


def prune(directory: Path, protect: Path, daily: int, weekly: int, monthly: int, dry_run: bool) -> list[Path]:
    items = backups(directory)
    if protect.resolve() not in {p.resolve() for _, p in items}:
        raise SystemExit(f"[retention] 보호 대상이 백업 목록에 없다 — 아무것도 지우지 않는다: {protect.name}")
    keep = keep_set(items, daily, weekly, monthly) | {protect}
    doomed = [p for _, p in items if p.resolve() not in {k.resolve() for k in keep}]
    for path in doomed:
        print(f"[retention] {'(dry-run) ' if dry_run else ''}remove {path.name}")
        if not dry_run:
            path.unlink()
            path.with_name(path.name + ".sha256").unlink(missing_ok=True)
    print(f"[retention] kept={len(items) - len(doomed)} removed={len(doomed)}")
    return doomed


def _selftest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        # 2026-01-01 ~ 2026-10-26 매일 03:30 + 10-26 에 하나 더(같은 날 두 개), 이름이 다른 파일 하나
        start = datetime(2026, 1, 1, 3, 30)
        names = []
        for i in range(299):
            names.append((start + timedelta(days=i)).strftime("kbo-%Y%m%d-%H%M%S.dump"))
        names.append("kbo-20261026-120000.dump")
        for n in names:
            (d / n).write_text("x")
            (d / (n + ".sha256")).write_text("x")
        (d / "notes.txt").write_text("keep me")
        newest = d / "kbo-20261026-120000.dump"
        removed = prune(d, newest, daily=14, weekly=8, monthly=6, dry_run=False)
        left = sorted(p.name for p in d.glob("kbo-*.dump"))
        assert newest.exists() and (d / "notes.txt").exists()
        assert not (d / "kbo-20261026-033000.dump").exists()            # 같은 날 이른 백업은 일간 하나만 남는다
        assert (d / "kbo-20261013-033000.dump").exists()                # 최근 14일
        assert all((d / (n + ".sha256")).exists() for n in left)        # 남은 dump 의 짝은 그대로
        assert not any((d / (p.name + ".sha256")).exists() for p in removed)
        assert len(left) <= 14 + 8 + 6 and len(left) >= 14              # 합집합이라 겹치면 더 적다
        months = {n[4:10] for n in left}
        assert {"202605", "202606", "202607", "202608", "202609", "202610"} <= months  # 최근 6개월은 남는다
        # 보호 대상이 목록에 없으면 아무것도 지우지 않는다
        before = set(d.iterdir())
        try:
            prune(d, d / "kbo-20990101-000000.dump", 1, 1, 1, dry_run=False)
            raise AssertionError("보호 대상 없이 정리했다")
        except SystemExit:
            pass
        assert set(d.iterdir()) == before
    print("[retention] selftest ok")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("directory", nargs="?", type=Path)
    ap.add_argument("--protect", type=Path)
    ap.add_argument("--keep-daily", type=int, default=14)
    ap.add_argument("--keep-weekly", type=int, default=8)
    ap.add_argument("--keep-monthly", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest()
        return
    if not a.directory or not a.protect:
        ap.error("DIR 와 --protect 가 필요하다")
    if min(a.keep_daily, a.keep_weekly, a.keep_monthly) < 1:
        ap.error("보관 개수는 1 이상")
    prune(a.directory, a.protect, a.keep_daily, a.keep_weekly, a.keep_monthly, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
