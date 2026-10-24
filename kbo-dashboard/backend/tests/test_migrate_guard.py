"""public 재적재(migrate.py) 빈 데이터 보호: 0행·없는 CSV 로 시즌의 기존 DB 행을 지우지 않는다. SQLite 메모리 DB."""
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import migrate
import migrate_analytics
from database import Base
from models import Standing, Team


class PublicReloadGuardTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        team = Team(name="LG")
        self.db.add(team)
        self.db.flush()
        self.db.add(Standing(season=2026, rank=1, team_id=team.id, games=144, wins=90, losses=50, draws=4))
        self.db.commit()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def count(self):
        return self.db.query(Standing).filter(Standing.season == 2026).count()

    def test_header_only_csv_keeps_rows(self):
        (self.dir / "kbo_team_rank_2026.csv").write_text("Season,순위,팀명,경기,승,패,무,승률,게임차,최근10경기,연속,홈,방문\n",
                                                         encoding="utf-8")
        migrate.migrate_standings(self.db, self.dir, 2026, {})
        self.assertEqual(self.count(), 1)

    def test_missing_csv_keeps_rows(self):
        migrate.migrate_standings(self.db, self.dir, 2026, {})
        self.assertEqual(self.count(), 1)

    def test_empty_rows_do_not_clear_analytics_table(self):
        migrate_analytics._load(self.db, Standing, [], season=2026)
        self.assertEqual(self.count(), 1)

    def test_real_rows_still_replace(self):
        migrate_analytics._load(self.db, Standing, [dict(season=2026, rank=2, team_id=1, games=1, wins=1, losses=0, draws=0)],
                                season=2026)
        self.assertEqual([s.rank for s in self.db.query(Standing).filter(Standing.season == 2026)], [2])


if __name__ == "__main__":
    unittest.main()
