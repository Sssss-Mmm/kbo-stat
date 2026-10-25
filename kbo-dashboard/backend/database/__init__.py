import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# 테스트 모드는 KBO_ENV=test 로만 켠다. 이때는 .env·DATABASE_URL·기본 localhost 를 쓰지 않고 TEST_DATABASE_URL 만 —
# 없으면 메모리 SQLite. 운영·개발 실행(KBO_ENV 없음)은 기존 경로 그대로: 환경변수 > .env > 기본값.
TESTING = os.getenv("KBO_ENV") == "test"

# 보조 안전장치: 테스트 러너가 떠 있는데 KBO_ENV=test 가 없으면 DB 를 고르지 않고(접속 전) 바로 멈춘다.
# 러너 감지는 설정 누락을 잡는 데만 쓰고, 대상 선택에는 쓰지 않는다.
if not TESTING and ("unittest" in sys.modules or "pytest" in sys.modules):
    raise RuntimeError("테스트 러너가 실행 중인데 KBO_ENV=test 가 없다 — 운영·개발 DB 를 쓰지 않도록 중단한다. "
                       "KBO_ENV=test (필요하면 TEST_DATABASE_URL) 를 지정해 다시 실행할 것.")



# 테스트 대상 검증(Codex 교차검증 반영). 이름의 `_test` 만 믿지 않는다:
#  - SQLite: 메모리만(sqlite:// · sqlite:///:memory:) — 파일 경로는 TMPDIR·심볼릭 링크·uri= 로 바뀔 수 있어 받지 않는다
#  - PostgreSQL: psycopg2 드라이버만. 드라이버가 실제 받을 host·port 가 TEST_DATABASE_ALLOWED_HOSTS(명시 허용 목록)에 있고
#    dbname 이 `_test` 로 끝나야 한다. 다중 호스트, 대상을 바꾸는 쿼리(?dbname=·?service=·?hostaddr=·?port= 등)와
#    libpq 환경변수(PGHOST 등)는 거부한다. 포트는 URL 의 host:port 로만 쓴다. 유닉스 소켓 디렉터리는 심볼릭 링크 없는
#    실제 경로만(검증한 경로 = 엔진이 접속할 경로). IPv6 는 허용 목록에 [주소]:포트 로 쓴다.
#    허용 목록의 호스트 이름이 가리키는 주소(DNS·/etc/hosts)는 검증하지 않는다 — 목록에는 IP·소켓 경로·격리 네트워크 이름만 넣는다.
# 거부 메시지는 고정 문구 — URL·DB 이름·쿼리 값은 싣지 않는다.
TEST_URL_QUERY_KEYS = {"host", "sslmode", "connect_timeout", "application_name"}
LIBPQ_TARGET_ENV = ("PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGSERVICE", "PGSERVICEFILE", "PGSYSCONFDIR",
                    "PGOPTIONS", "PGTARGETSESSIONATTRS")
PG_DRIVERS = {"postgresql", "postgresql+psycopg2"}
ALLOWED_HOSTS_ENV = "TEST_DATABASE_ALLOWED_HOSTS"  # 예: "/run/kbo_test_pgsock:5432,kbo_test_db:5432"


def _norm_host(host):
    """소켓 디렉터리의 끝 슬래시만 떼어 비교한다(/run/sock/ == /run/sock)."""
    return host.rstrip("/") or host if host.startswith("/") else host


def _allowed_endpoints(raw):
    """TEST_DATABASE_ALLOWED_HOSTS → {(host, port)}. 형식이 틀린 항목이 하나라도 있으면 ValueError(값은 싣지 않는다)."""
    endpoints = set()
    for item in filter(None, (part.strip() for part in raw.split(","))):
        host, sep, port = item.rpartition(":")
        host = host[1:-1] if host.startswith("[") and host.endswith("]") else host
        host = _norm_host(host)
        if not sep or not host or not port.isdigit() or not 0 < int(port) < 65536:
            raise ValueError
        endpoints.add((host, int(port)))
    return endpoints


def _real_socket_dir(host):
    """유닉스 소켓 디렉터리가 심볼릭 링크 없는 절대 실제 경로인지. 이미 놓인 링크로 다른 서버를 가리키는 것은 막지만,
    검증 뒤 상위 디렉터리를 바꿔치기하는 경쟁(쓰기 권한 필요)은 막지 못한다 — 소켓은 본인 소유 0700 디렉터리에 둔다."""
    from pathlib import Path

    try:
        return Path(host).is_absolute() and str(Path(host).resolve(strict=True)) == host.rstrip("/")
    except (OSError, RuntimeError):
        return False


def test_url_problem(url, env=os.environ):
    """테스트 대상이 테스트 전용인지. 문제가 없으면 None, 있으면 고정 문구 이유."""
    try:
        parsed = make_url(url)
    except Exception:  # noqa: BLE001 — 형식 오류 메시지는 비밀번호를 담을 수 있어 종류만
        return "TEST_DATABASE_URL 형식 오류"
    if parsed.get_backend_name() == "sqlite":
        if parsed.database in (None, "", ":memory:") and not parsed.query:
            return None
        return "테스트 SQLite 는 메모리(sqlite://)만 허용한다"
    if parsed.drivername not in PG_DRIVERS:
        return "테스트 DB 는 SQLite 또는 psycopg2 PostgreSQL 만 허용한다"
    if set(parsed.query) - TEST_URL_QUERY_KEYS:
        return f"TEST_DATABASE_URL 에 허용하지 않는 쿼리 파라미터가 있다(허용: {', '.join(sorted(TEST_URL_QUERY_KEYS))})"
    if any(env.get(name) for name in LIBPQ_TARGET_ENV):
        return f"libpq 접속 대상 환경변수({', '.join(LIBPQ_TARGET_ENV)})가 설정돼 있다 — 테스트에서는 비워야 한다"
    try:  # 드라이버가 실제로 받을 인자 — 경로·호스트 표기만 믿지 않는다
        args = parsed.get_dialect()().create_connect_args(parsed)[1]
    except Exception:  # noqa: BLE001 — 드라이버 없음 등. 메시지는 싣지 않는다
        return "TEST_DATABASE_URL 의 PostgreSQL 드라이버를 불러오지 못함"
    host, port = args.get("host"), args.get("port")
    port = 5432 if port is None else port  # 소켓 URL 엔 port 가 없다(libpq 기본 5432). 0 등 다른 값은 그대로 검사
    if not isinstance(host, str) or not host or "," in host or type(port) is not int or not 0 < port < 65536:
        return "TEST_DATABASE_URL 은 호스트 하나와 포트를 명시해야 한다(다중 호스트·기본 호스트 금지)"
    try:
        allowed = _allowed_endpoints(env.get(ALLOWED_HOSTS_ENV, ""))
    except ValueError:
        return f"{ALLOWED_HOSTS_ENV} 형식 오류 — 쉼표로 구분한 호스트:포트([IPv6]:포트, /소켓디렉터리:포트)"
    if host.startswith("/") and not _real_socket_dir(host):
        return "테스트 PostgreSQL 소켓 디렉터리는 심볼릭 링크 없는 실제 경로여야 한다"
    if (_norm_host(host), port) not in allowed:
        return f"테스트 PostgreSQL 호스트·포트가 {ALLOWED_HOSTS_ENV} 허용 목록에 없다"
    if not str(args.get("dbname") or "").endswith("_test"):
        return "테스트 PostgreSQL DB 이름은 _test 로 끝나야 한다"
    return None


if TESTING:
    DATABASE_URL = os.getenv("TEST_DATABASE_URL") or "sqlite://"
    DATABASE_URL_SOURCE = "TEST_DATABASE_URL" if os.getenv("TEST_DATABASE_URL") else "test-default"
    # 전체 테스트가 운영명 DB 를 가리키지 않게 엔진을 만들기 전에 막는다(test_v2_pg 만이 아니라 모든 테스트에 적용).
    if (problem := test_url_problem(DATABASE_URL)):
        raise RuntimeError(f"KBO_ENV=test 인데 {problem}. 접속하지 않고 중단한다.")
else:
    from_env = "DATABASE_URL" in os.environ
    load_dotenv()

    # 데이터베이스 URL — 어디서 왔는지 남긴다(init_db.py 는 기본값으로는 실행하지 않는다)
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql://kbo_user:kbo_password@localhost:5432/kbo_dashboard"
    )
    DATABASE_URL_SOURCE = "env" if from_env else ".env" if "DATABASE_URL" in os.environ else "default"

# SQLAlchemy 엔진 생성 (DB_ECHO=true 일 때만 SQL 로깅)
DB_ECHO = os.getenv("DB_ECHO", "false").lower() == "true"
engine = create_engine(DATABASE_URL, echo=DB_ECHO)

# 세션팩토리 생성
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 베이스 클래스
Base = declarative_base()


def get_db():
    """데이터베이스 세션 의존성"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """데이터베이스 테이블 생성"""
    Base.metadata.create_all(bind=engine)
