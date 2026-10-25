"""seed_if_empty 분기 — 임시 SQLite 파일과 합성 행만 쓴다. migrate.main 은 가짜로 바꿔 실제 적재를 하지 않는다."""
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError

import seed_if_empty
from database import Base


class SeedIfEmptyTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.engine = create_engine(f"sqlite:///{Path(tmp.name) / 'seed_test.db'}")
        self.addCleanup(self.engine.dispose)
        self.migrate = types.SimpleNamespace(main=MagicMock())
        patcher = patch.dict(sys.modules, {"migrate": self.migrate})
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_seed(self, engine=None):
        return seed_if_empty.main(engine or self.engine)

    def test_seeded_table_skips_migration(self):
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO teams (id, name) VALUES (1, '가상팀')"))
            conn.execute(text("INSERT INTO standings (id, season, team_id) VALUES (1, 2099, 1)"))
        self.assertEqual(seed_if_empty.seed_state(self.engine), "seeded")
        self.assertEqual(self.run_seed(), 0)
        self.migrate.main.assert_not_called()

    def test_empty_table_seeds(self):
        Base.metadata.create_all(self.engine)
        self.assertEqual(seed_if_empty.seed_state(self.engine), "empty")
        self.assertEqual(self.run_seed(), 0)
        self.migrate.main.assert_called_once()

    def test_missing_table_seeds_through_existing_path(self):
        self.assertEqual(seed_if_empty.seed_state(self.engine), "missing")
        self.assertEqual(self.run_seed(), 0)
        self.migrate.main.assert_called_once()

    def test_connection_failure_is_not_treated_as_empty(self):
        broken = create_engine("sqlite:////nonexistent-dir-for-seed-test/x.db")  # 열 수 없는 경로 → 접속 실패
        with patch("sys.stderr") as err:
            self.assertEqual(self.run_seed(broken), 1)
        self.migrate.main.assert_not_called()
        self.assertIn("DB 상태를 확인하지 못함", "".join(c.args[0] for c in err.write.call_args_list))

    def test_permission_and_timeout_errors_are_not_treated_as_empty(self):
        for exc in (ProgrammingError("SELECT", {}, Exception("permission denied for table standings")),
                    OperationalError("connect", {}, Exception("timeout expired"))):
            with self.subTest(exc=type(exc).__name__), patch.object(seed_if_empty, "inspect", side_effect=exc), \
                    patch("sys.stderr"):
                self.assertEqual(self.run_seed(), 1)
        self.migrate.main.assert_not_called()

    def test_migration_failure_returns_failure(self):
        self.migrate.main.side_effect = RuntimeError("합성 실패")
        with patch("sys.stderr") as err:
            self.assertEqual(self.run_seed(), 1)
        self.assertIn("시드 실패", "".join(c.args[0] for c in err.write.call_args_list))


if __name__ == "__main__":
    unittest.main()
