import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import migrate
from database import Base

SEASONS = (2024, 2025)


def make_engine():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    event.listen(engine, 'connect', lambda conn, _: conn.execute('PRAGMA foreign_keys=ON'))
    return engine


def write_csvs(root: Path, wins=5, extra_team=False, break_season=None):
    raw = root / 'data' / 'raw' / 'kbo_official'
    processed = root / 'data' / 'processed'
    raw.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    teams = ['LG', '한화'] + (['신생팀'] if extra_team else [])
    for season in SEASONS:
        pd.DataFrame([
            {'순위': i + 1, '팀명': t, '경기': 10, '승': wins, '패': 10 - wins, '무': 0,
             '승률': wins / 10, '게임차': float(i)}
            for i, t in enumerate(teams)
        ]).to_csv(raw / f'kbo_team_rank_{season}.csv', index=False)
        pd.DataFrame([{'선수명': f'타자{t}', '팀명': t, 'AVG': 0.3, 'G': 10} for t in teams]) \
            .to_csv(raw / f'kbo_{season}.csv', index=False)
        pd.DataFrame([{'선수명': f'투수{t}', '팀명': t, 'ERA': 3.5, 'G': 10} for t in teams]) \
            .to_csv(raw / f'kbo_pitcher_{season}.csv', index=False)
        games = pd.DataFrame([
            {'Season': season, 'Date': f'{season}-04-01', 'Month': 4, 'GameId': f'G{season}{t}',
             'Team': t, 'Opponent': 'X', 'HomeAway': 'H', 'Ballpark': '잠실', 'RunsFor': 3,
             'RunsAgainst': 2, 'RunDiff': 1, 'Result': 'W', 'Win': 1, 'Loss': 0, 'Draw': 0}
            for t in teams
        ])
        if season == break_season:
            games = games.drop(columns=['RunsFor'])  # 분석 단계(마지막 쪽)에서 KeyError
        games.to_csv(processed / f'kbo_team_games_{season}.csv', index=False)


class MigrateAtomicityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = make_engine()
        self.Session = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        patches = [
            patch.object(migrate, '__file__', str(self.root / 'kbo-dashboard' / 'backend' / 'migrate.py')),
            patch.object(migrate, 'SessionLocal', self.Session),
            patch.object(migrate, 'init_db', lambda: Base.metadata.create_all(bind=self.engine)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def run_migrate(self):
        self.out = io.StringIO()
        with contextlib.redirect_stdout(self.out), contextlib.redirect_stderr(io.StringIO()):
            migrate.main()

    def snapshot(self):
        with self.engine.connect() as conn:
            return {t.name: sorted(map(tuple, conn.execute(select(t)).all()), key=repr)
                    for t in Base.metadata.sorted_tables}

    def counts(self):
        return {name: len(rows) for name, rows in self.snapshot().items()}

    def test_rerun_is_idempotent(self):
        write_csvs(self.root)
        self.run_migrate()
        first = self.counts()
        self.assertIn('모든 마이그레이션 완료', self.out.getvalue())
        self.run_migrate()
        self.assertEqual(self.counts(), first)
        self.assertEqual(first['teams'], 2)
        for table in ('standings', 'hitters', 'pitchers', 'team_games'):
            self.assertEqual(first[table], 2 * len(SEASONS), table)

    def test_failure_rolls_back_everything(self):
        write_csvs(self.root)
        self.run_migrate()
        before = self.snapshot()

        # 순위·팀은 바뀌고, 마지막 쪽 분석 단계(2025 team_games)가 깨진다.
        write_csvs(self.root, wins=7, extra_team=True, break_season=2025)
        with self.assertRaises(KeyError):
            self.run_migrate()

        self.assertEqual(self.snapshot(), before)
        self.assertNotIn('모든 마이그레이션 완료', self.out.getvalue())

    def test_final_commit_failure_rolls_back_and_propagates(self):
        write_csvs(self.root)
        self.run_migrate()
        before = self.snapshot()

        rollbacks = []

        class CommitFailingSession(Session):
            def commit(self):
                raise OperationalError('COMMIT', {}, Exception('disk I/O error'))

            def rollback(self):
                rollbacks.append(True)
                super().rollback()

        failing = sessionmaker(class_=CommitFailingSession, autocommit=False, autoflush=False, bind=self.engine)
        write_csvs(self.root, wins=7, extra_team=True)  # 모든 단계는 성공, 최종 commit 만 실패
        with patch.object(migrate, 'SessionLocal', failing):
            with self.assertRaises(OperationalError):
                self.run_migrate()

        self.assertEqual(rollbacks, [True])
        self.assertNotIn('모든 마이그레이션 완료', self.out.getvalue())
        self.assertEqual(self.snapshot(), before)

    def test_failed_first_seed_leaves_db_empty(self):
        write_csvs(self.root, break_season=2025)
        with self.assertRaises(KeyError):
            self.run_migrate()
        # 비어 있어야 seed_if_empty.already_seeded() 가 다음 기동 때 다시 시드한다.
        self.assertTrue(all(n == 0 for n in self.counts().values()), self.counts())


if __name__ == '__main__':
    unittest.main()
