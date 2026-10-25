"""public 테이블을 명시적으로 만든다(Base.metadata.create_all — 없는 테이블만 만들고, 있는 테이블·데이터는 건드리지 않는다).

앱 import 는 더 이상 테이블을 만들지 않는다. 신규 환경은 컨테이너 기동 때 seed_if_empty.py → migrate.py 가 처리하고,
테이블만 따로 만들 때 이 명령을 쓴다. 대상은 DATABASE_URL(환경변수 또는 .env) 또는 테스트 모드의 TEST_DATABASE_URL —
아무 설정 없이 기본값(localhost:5432)으로는 실행하지 않는다.

  DATABASE_URL=postgresql://... python init_db.py
"""
import sys

from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

ALLOWED_DRIVERS = ("postgresql", "sqlite")


def check_target(database) -> str | None:
    """실행 전 대상 검증 — 문제가 있으면 이유(접속 전에 판단)."""
    if database.DATABASE_URL_SOURCE == "default":
        return "DATABASE_URL 이 지정되지 않았다(환경변수·.env 모두 없음) — 기본값 localhost:5432 로는 실행하지 않는다"
    if make_url(database.DATABASE_URL).drivername.split("+")[0] not in ALLOWED_DRIVERS:
        return f"지원하지 않는 DB 종류: {make_url(database.DATABASE_URL).drivername}"
    return None


def main() -> int:
    try:
        import database
        import models  # noqa: F401 — Base 에 테이블을 등록한다
    except Exception as exc:  # noqa: BLE001 — URL 형식 오류·없는 드라이버. 메시지는 URL(비밀번호)을 담을 수 있어 종류만 보인다
        print(f"[init_db] 거부 — DATABASE_URL 을 쓸 수 없다({type(exc).__name__})", file=sys.stderr)
        return 2
    problem = check_target(database)
    if problem:
        print(f"[init_db] 거부 — {problem}", file=sys.stderr)
        return 2
    target = database.engine.url.render_as_string(hide_password=True)
    print(f"[init_db] 대상: {target} (출처: {database.DATABASE_URL_SOURCE})")
    try:
        before = set(inspect(database.engine).get_table_names())
        database.init_db()
        created = sorted(set(inspect(database.engine).get_table_names()) - before)
    except SQLAlchemyError as exc:
        print(f"[init_db] 실패 — {type(exc).__name__}: {exc.orig if getattr(exc, 'orig', None) else exc}", file=sys.stderr)
        return 1
    print(f"[init_db] 완료 — 새로 만든 테이블 {len(created)}개{': ' + ', '.join(created) if created else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
