"""DB 접속 대상·import 부작용 — 실제 DB 에 접속하지 않고 설정과 연결 차단만 확인한다.

새 파이썬 프로세스에서 .env 읽기(load_dotenv), 파이썬 소켓, psycopg2(libpq — 파이썬 소켓을 쓰지 않는다) 접속을 막은 채
database·main 을 import 한다. 운영 같은 URL 도 아무것도 듣지 않는 포트 1 을 가리킨다(막기가 새도 운영 DB 에 닿지 않게).
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent

GUARD = """
import socket, dotenv, psycopg2
def _no_connect(*a, **k): raise AssertionError("네트워크 접속 시도")
socket.socket.connect = socket.socket.connect_ex = _no_connect
socket.create_connection = _no_connect
def _no_pg(*a, **k): raise psycopg2.OperationalError("네트워크 접속 시도(psycopg2) — 테스트에서 막음")
psycopg2.connect = _no_pg
def _no_dotenv(*a, **k): raise AssertionError("load_dotenv 호출됨")
dotenv.load_dotenv = _no_dotenv if DOTENV == "block" else (lambda *a, **k: False)
"""

PROD_LIKE = "postgresql://kbo_user:pw@127.0.0.1:1/kbo_dashboard"
TMP_SQLITE = "sqlite:///:memory:"  # 기본값(sqlite://)과 구별되는, 테스트 모드가 허용하는 명시 URL


def run_guarded(code, runner=False, dotenv="noop", **env):
    """새 프로세스에서 막아 둔 채 실행. runner=True 면 테스트 러너(unittest)가 먼저 로드된 상황을 흉내 낸다.
    DB 관련 환경변수는 넘긴 것만 남긴다. → (종료 코드, stdout, stderr)"""
    base = {k: v for k, v in os.environ.items()
            if k not in ("DATABASE_URL", "TEST_DATABASE_URL", "KBO_ENV", "TEST_DATABASE_ALLOWED_HOSTS") and not k.startswith("PG")}
    prelude = ("import unittest\n" if runner else "") + f"DOTENV = {dotenv!r}\n"
    out = subprocess.run([sys.executable, "-c", prelude + GUARD + code], cwd=BACKEND, env=base | env,
                         capture_output=True, text=True, timeout=120)
    return out.returncode, out.stdout, out.stderr


def last_line(out):
    return (out.strip().splitlines() or [""])[-1]


class ImportSideEffectTest(unittest.TestCase):
    def test_importing_app_makes_no_connection_even_with_prod_like_url(self):
        # 테스트 모드가 아닌 운영 실행 경로 — 운영 같은 DATABASE_URL 이 있어도 import 만으로는 접속·테이블 생성이 없다
        code, out, err = run_guarded("import main, database; print(database.engine.url.render_as_string(hide_password=False))",
                                     DATABASE_URL=PROD_LIKE)
        self.assertEqual(code, 0, err)
        self.assertEqual(last_line(out), PROD_LIKE)
        self.assertNotIn("네트워크 접속 시도", out + err)

    def test_app_does_not_call_init_db_on_import(self):
        code, out, err = run_guarded("import database\ncalls = []\ndatabase.init_db = lambda: calls.append(1)\n"
                                     "import main; print(len(calls))", DATABASE_URL=PROD_LIKE)
        self.assertEqual((code, last_line(out)), (0, "0"), err)

    def test_guard_blocks_psycopg2(self):
        # 위 검사가 의미 있으려면 막기가 실제로 동작해야 한다
        code, out, err = run_guarded("import database\ntry:\n    database.engine.connect()\nexcept Exception as e:\n"
                                     "    print(type(e).__name__, e)", DATABASE_URL=PROD_LIKE)
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith("OperationalError"), out)
        self.assertIn("네트워크 접속 시도(psycopg2)", out)


class TestModeTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.sock = str(Path(tmp.name).resolve() / "pgsock")  # 실제 디렉터리(심볼릭 링크 없음)
        Path(self.sock).mkdir()
        self.link = str(Path(tmp.name).resolve() / "pgsock-link")
        os.symlink(self.sock, self.link)

    def test_test_mode_ignores_database_url_and_dotenv(self):
        code, out, err = run_guarded("import database; print(database.DATABASE_URL)", dotenv="block",
                                     KBO_ENV="test", DATABASE_URL=PROD_LIKE)
        self.assertEqual((code, last_line(out)), (0, "sqlite://"), err)

    def test_test_database_url_takes_priority(self):
        code, out, err = run_guarded("import database; print(database.DATABASE_URL, database.DATABASE_URL_SOURCE)",
                                     dotenv="block", KBO_ENV="test", DATABASE_URL=PROD_LIKE,
                                     TEST_DATABASE_URL=TMP_SQLITE)
        self.assertEqual((code, last_line(out)), (0, f"{TMP_SQLITE} TEST_DATABASE_URL"), err)

    def test_test_mode_refuses_non_test_database_before_connecting(self):
        """Codex 교차검증: _test 검사가 test_v2_pg 에만 있어 전체 테스트가 운영명 DB 를 쓸 수 있었다."""
        for url in (PROD_LIKE, "postgresql://u:secretpw@127.0.0.1:1/test_kbo", "mysql://u:p@127.0.0.1:1/x_test", "not a url",
                    # Codex 재검토: 쿼리 파라미터로 실제 대상(dbname·서비스 파일·DSN)을 바꾸는 우회
                    "postgresql+psycopg2://u:secretpw@127.0.0.1:1/safe_test?dbname=kbo_dashboard",
                    "postgresql://u:p@127.0.0.1:1/safe_test?service=prod", "postgresql://u:p@127.0.0.1:1/safe_test?dsn=dbname%3Dprod",
                    # Codex 3차: 이름만 _test 인 운영 서버·기본 호스트·다중 호스트·hostaddr·다른 드라이버·임의 SQLite 파일
                    "postgresql://u:p@127.0.0.1:5433/kbo_secretname_test", "postgresql://u:p@/kbo_p3s1_test",
                    "postgresql://u:p@/kbo_p3s1_test?host=127.0.0.1:1&host=127.0.0.1:5433",
                    "postgresql://u:p@127.0.0.1:1/kbo_p3s1_test?hostaddr=10.0.0.1", "postgresql+pg8000://u:p@127.0.0.1:1/kbo_p3s1_test",
                    "sqlite:///kbo_dashboard.db", "sqlite:////home/someone/other_project_test.db",
                    # Codex 4차: 파일 SQLite 는 TMPDIR·심볼릭 링크·uri= 로 바뀔 수 있다 / 쿼리형 port
                    "sqlite:////tmp/x_test.db", "sqlite:///file:/etc/x_test.db?mode=rw&uri=true",
                    "postgresql://u:p@/kbo_p3s1_test?host=/tmp/pgsock&port=5433",
                    # :0 은 SQLAlchemy 가 port 인자를 빼서 libpq 기본 5432 로 간다 — 검증도 같은 인자로 5432 를 보고 거부
                    "postgresql://u:p@127.0.0.1:0/kbo_p3s1_test",
                    # Codex 5차: 허용 목록에 있는 디렉터리라도 심볼릭 링크 경로·없는 경로는 거부
                    f"postgresql://u:p@/kbo_p3s1_test?host={self.link}", "postgresql://u:p@/kbo_p3s1_test?host=/nonexistent/pgsock"):
            code, out, err = run_guarded("import database", dotenv="block", KBO_ENV="test", TEST_DATABASE_URL=url,
                                         TEST_DATABASE_ALLOWED_HOSTS=f"127.0.0.1:1,{self.sock}:5432,{self.link}:5432,/nonexistent/pgsock:5432")
            self.assertNotEqual(code, 0, url)
            self.assertIn("KBO_ENV=test 인데", err)
            for leak in ("secretpw", "secretname", "kbo_dashboard"):  # 비밀번호·DB 이름을 메시지에 싣지 않는다
                self.assertNotIn(leak, err + out, url)
            self.assertNotIn("네트워크 접속 시도", err)
        # 허용 목록에 있어도 libpq 대상 환경변수가 있으면 거부(PGHOSTADDR 가 host 의 실제 주소를 바꾼다)
        code, _, err = run_guarded("import database", dotenv="block", KBO_ENV="test", PGHOSTADDR="10.0.0.1",
                                   TEST_DATABASE_URL="postgresql://u:p@127.0.0.1:1/kbo_p3s1_test", TEST_DATABASE_ALLOWED_HOSTS="127.0.0.1:1")
        self.assertIn("libpq", err)
        # 허용 목록이 없으면 PostgreSQL 은 쓸 수 없다
        code, _, err = run_guarded("import database", dotenv="block", KBO_ENV="test",
                                   TEST_DATABASE_URL="postgresql://u:p@127.0.0.1:1/kbo_p3s1_test")
        self.assertIn("허용 목록에 없다", err)
        # 허용 목록 형식 오류는 값 없이 고정 문구(포트 비숫자·범위 밖·호스트 없음)
        for allowed in ("127.0.0.1:abc", "127.0.0.1:70000", ":5432", "secret-host-name"):
            code, out, err = run_guarded("import database", dotenv="block", KBO_ENV="test", TEST_DATABASE_ALLOWED_HOSTS=allowed,
                                         TEST_DATABASE_URL="postgresql://u:p@127.0.0.1:1/kbo_p3s1_test")
            self.assertIn("형식 오류", err, allowed)
            self.assertNotIn("secret-host-name", err)
        for url, allowed in (("postgresql://u:p@127.0.0.1:1/kbo_p3s1_test", "127.0.0.1:1"),
                             (f"postgresql://u@/kbo_p3s1_test?host={self.sock}&sslmode=disable", f"db:5432, {self.sock}/:5432"),
                             ("postgresql://u:p@[::1]:5432/kbo_p3s1_test", "[::1]:5432")):  # 끝 슬래시 정규화·IPv6 대괄호
            code, out, err = run_guarded("import database; print(database.engine.url.database)", dotenv="block", KBO_ENV="test",
                                         TEST_DATABASE_URL=url, TEST_DATABASE_ALLOWED_HOSTS=allowed)
            self.assertEqual((code, last_line(out)), (0, "kbo_p3s1_test"), err)

    def test_runner_without_kbo_env_fails_before_connecting(self):
        code, out, err = run_guarded("import main", runner=True, dotenv="block", DATABASE_URL=PROD_LIKE)
        self.assertNotEqual(code, 0)
        self.assertIn("KBO_ENV=test 가 없다", err)
        self.assertNotIn("load_dotenv 호출됨", err)  # .env 도 읽기 전에 멈춘다
        self.assertNotIn("네트워크 접속 시도", out + err)

    def test_runner_is_not_used_to_select_target(self):
        # 러너 감지 여부와 무관하게 KBO_ENV=test 만이 테스트 대상을 고른다
        for runner in (True, False):
            code, out, err = run_guarded("import database; print(database.DATABASE_URL)", runner=runner, dotenv="block",
                                         KBO_ENV="test", TEST_DATABASE_URL=TMP_SQLITE)
            self.assertEqual((code, last_line(out)), (0, TMP_SQLITE), err)

    def test_app_run_path_keeps_existing_priority(self):
        # 러너도 KBO_ENV 도 없으면 기존처럼 .env 를 읽는다(막아 둔 load_dotenv 에 걸림) — 환경변수가 우선
        code, _, err = run_guarded("import database", dotenv="block", DATABASE_URL=PROD_LIKE)
        self.assertNotEqual(code, 0)
        self.assertIn("load_dotenv 호출됨", err)
        code, out, err = run_guarded("import database; print(database.DATABASE_URL_SOURCE, database.DATABASE_URL)",
                                     DATABASE_URL=PROD_LIKE)
        self.assertEqual((code, last_line(out)), (0, f"env {PROD_LIKE}"), err)
        code, out, err = run_guarded("import database; print(database.DATABASE_URL_SOURCE)")
        self.assertEqual((code, last_line(out)), (0, "default"), err)


if __name__ == "__main__":
    unittest.main()
