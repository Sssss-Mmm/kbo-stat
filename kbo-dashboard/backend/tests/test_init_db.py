"""명시적 초기화 명령(init_db.py) — 임시 SQLite 파일에만 실행한다. 새 프로세스에서 .env 읽기·소켓·psycopg2 접속을 막는다."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

try:
    from test_db_isolation import run_guarded  # unittest discover -s tests
except ImportError:
    from tests.test_db_isolation import run_guarded  # python -m unittest tests.test_init_db


def run_init(**env):
    return run_guarded("import runpy, sys\nsys.argv = ['init_db.py']\n"
                       "try:\n    runpy.run_path('init_db.py', run_name='__main__')\n"
                       "except SystemExit as e:\n    sys.exit(e.code)\n", **env)


class InitDbCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "init_test.db"
        self.url = f"sqlite:///{self.path}"

    def tables(self):
        with sqlite3.connect(self.path) as conn:
            return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    def test_creates_public_tables_and_is_idempotent(self):
        code, out, err = run_init(DATABASE_URL=self.url)
        self.assertEqual(code, 0, err)
        self.assertIn("새로 만든 테이블 13개", out)
        self.assertIn("출처: env", out)
        self.assertTrue({"teams", "standings", "schedules", "hitters", "pitchers"} <= self.tables())
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO teams (id, name) VALUES (1, '가상팀')")
        code, out, err = run_init(DATABASE_URL=self.url)  # 다시 실행 — 있는 테이블·데이터는 그대로
        self.assertEqual(code, 0, err)
        self.assertIn("새로 만든 테이블 0개", out)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute("SELECT name FROM teams").fetchall(), [("가상팀",)])

    def test_refuses_without_explicit_database_url(self):
        code, out, err = run_init()  # 환경변수·.env 모두 없음 → 기본 localhost:5432 로 가지 않는다
        self.assertEqual(code, 2, out + err)
        self.assertIn("DATABASE_URL 이 지정되지 않았다", err)
        self.assertNotIn("네트워크 접속 시도", out + err)

    def test_refuses_unsupported_or_malformed_url(self):
        for url in ("mysql://u:p@h/db", "not a url"):
            code, _, err = run_init(DATABASE_URL=url)
            self.assertEqual(code, 2, err)
            self.assertIn("거부", err)

    def test_masks_password_in_output(self):
        code, out, err = run_init(DATABASE_URL="postgresql://u:secretpw@127.0.0.1:1/x_test")
        self.assertNotIn("secretpw", out + err)
        self.assertNotEqual(code, 0)  # 소켓을 막아 두었으므로 접속 실패 → 실패 코드(1)
        self.assertIn("[init_db] 실패", err)


if __name__ == "__main__":
    unittest.main()
