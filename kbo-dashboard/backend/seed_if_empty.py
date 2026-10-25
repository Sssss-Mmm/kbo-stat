"""DB가 비어 있으면 migrate.py 로 최초 1회 시드한다.

컨테이너 진입점(entrypoint.sh)에서 uvicorn 기동 전에 호출한다. 마이그레이션은
시즌별 delete-after 라 멱등하지만, 매 기동마다 전체 재적재를 피하려고 standings
가 비어 있을 때만 실행한다. postgres 볼륨이 살아 있으면 재기동 시 시드를 건너뛴다.

상태 판정(seed_state):
  seeded  — standings 테이블에 행이 있다 → 시드하지 않는다
  empty   — 테이블은 있지만 비어 있다 → 시드(migrate.py)
  missing — 테이블이 없다 → 시드(migrate.py 가 init_db 로 테이블부터 만든다)
접속 실패·권한 오류·타임아웃 등 DB 오류는 '비어 있음'으로 보지 않는다 — 시드하지 않고 원인을 남긴 뒤 실패(1)를 돌려준다.
entrypoint.sh 는 실패해도 API 를 띄운다(CSV 라우터는 DB 없이 동작, DB 라우터는 503).
"""
import sys

from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

import database
from models import Standing


def seed_state(engine) -> str:
    """seeded / empty / missing. DB 오류는 SQLAlchemyError 그대로 올린다."""
    if not inspect(engine).has_table(Standing.__tablename__):
        return "missing"
    with engine.connect() as conn:
        row = conn.execute(Standing.__table__.select().limit(1)).first()
    return "seeded" if row is not None else "empty"


def main(engine=None) -> int:
    engine = engine or database.engine
    try:
        state = seed_state(engine)
    except SQLAlchemyError as exc:
        print(f"[seed] DB 상태를 확인하지 못함 — 시드하지 않는다. {type(exc).__name__}: {exc}".rstrip(), file=sys.stderr)
        return 1
    if state == "seeded":
        print("[seed] DB already seeded — skipping migration.")
        return 0
    print(f"[seed] standings {'테이블 없음' if state == 'missing' else '비어 있음'} — running migration...")
    try:
        import migrate
        migrate.main()
    except Exception as exc:  # noqa: BLE001 — 시드 실패 원인을 남기고 실패로 돌려준다
        print(f"[seed] 시드 실패 — {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
