"""테스트가 운영·다른 프로젝트 DB 에 닿지 않는지 — 실제 DB 에 접속하지 않고 설정과 연결 차단만 확인한다.

새 파이썬 프로세스에서 .env 읽기(load_dotenv)와 모든 소켓 연결을 막은 채 database·main 을 import 한다.
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent

# .env 를 읽거나 네트워크로 접속하면 즉시 실패시키는 준비 코드
GUARD = """
import socket, dotenv
def _no_dotenv(*a, **k): raise AssertionError("load_dotenv 호출됨")
def _no_connect(*a, **k): raise AssertionError(f"네트워크 접속 시도: {a[1:]}")
dotenv.load_dotenv = _no_dotenv
socket.socket.connect = socket.socket.connect_ex = _no_connect
socket.create_connection = _no_connect
"""

PROD_LIKE = "postgresql://u:p@127.0.0.1:5433/kbo_dashboard"


def run(code, testing=True, **env):
    base = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "TEST_DATABASE_URL")}
    prelude = "import unittest\n" if testing else ""
    out = subprocess.run([sys.executable, "-c", prelude + GUARD + code], cwd=BACKEND, env=base | env,
                         capture_output=True, text=True, timeout=120)
    return out.returncode, out.stdout.strip().splitlines()[-1:] or [""], out.stderr


class TestDbIsolationTest(unittest.TestCase):
    def test_tests_ignore_database_url_and_dotenv(self):
        code, last, err = run("import database; print(database.DATABASE_URL)", DATABASE_URL=PROD_LIKE)
        self.assertEqual(code, 0, err)
        self.assertEqual(last, ["sqlite://"])

    def test_importing_app_under_tests_makes_no_network_connection(self):
        # main 은 import 때 init_db(create_all)를 부른다 — 운영 같은 DATABASE_URL 이 있어도 메모리 SQLite 에만 만든다
        code, last, err = run("import main, database; print(database.engine.url.drivername)", DATABASE_URL=PROD_LIKE)
        self.assertEqual(code, 0, err)
        self.assertEqual(last, ["sqlite"])
        self.assertNotIn("네트워크 접속 시도", err)

    def test_explicit_test_database_url_is_used(self):
        code, last, err = run("import database; print(database.DATABASE_URL)",
                              DATABASE_URL=PROD_LIKE, TEST_DATABASE_URL="sqlite:///kbo_unit_test.db")
        self.assertEqual(code, 0, err)
        self.assertEqual(last, ["sqlite:///kbo_unit_test.db"])

    def test_app_run_path_is_unchanged(self):
        # 테스트 러너 없이(운영 uvicorn 과 같은 조건) import 하면 기존처럼 DATABASE_URL 을 쓴다 — 접속은 하지 않는다
        code, last, err = run("import database, sys; print(database.TESTING, database.DATABASE_URL)",
                              testing=False, DATABASE_URL=PROD_LIKE)
        self.assertEqual(code, 1)  # 운영 경로는 .env 를 읽는다 → 막아 둔 load_dotenv 에 걸림
        self.assertIn("load_dotenv 호출됨", err)
        code, last, err = run("import dotenv; dotenv.load_dotenv = lambda *a, **k: None\n"
                              "import database; print(database.TESTING, database.DATABASE_URL)",
                              testing=False, DATABASE_URL=PROD_LIKE)
        self.assertEqual(code, 0, err)
        self.assertEqual(last, [f"False {PROD_LIKE}"])


if __name__ == "__main__":
    unittest.main()
