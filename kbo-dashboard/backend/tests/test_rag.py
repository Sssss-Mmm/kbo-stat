import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from services.rag_service import RagService, NO_EVIDENCE_ANSWER
from services.story_service import StoryService


def fixture():
    return {
        'standings': pd.DataFrame([
            {'팀명': '삼성', '순위': 1, '승': 2, '패': 1, '무': 1, '승률': 2 / 3, '최근10경기': '2승1무1패', '연속': '1승'},
            {'팀명': 'LG', '순위': 2, '승': 1, '패': 2, '무': 1, '승률': 1 / 3, '최근10경기': '1승1무2패', '연속': '1패'},
        ]),
        'team_games': pd.DataFrame([
            {'Team': '삼성', 'HomeAway': side, 'Win': w, 'Loss': l, 'Draw': d, 'Date': date, 'RunsFor': 2, 'RunsAgainst': 1}
            for side, w, l, d, date in [('home', 1, 0, 0, '2026-04-01'), ('home', 0, 0, 1, '2026-04-02'), ('away', 0, 1, 0, '2026-04-03')]
        ]),
        'team_monthly': pd.DataFrame(),
        'hitters': pd.DataFrame([
            {'Player': f'선수{i}', 'Team': '삼성', 'WARProxy': i, 'OPS': .8, 'AVG': .3, 'HR': i, 'RBI': i}
            for i in range(12)
        ]),
    }


class RagAnswersTest(unittest.TestCase):
    def setUp(self):
        self.service = RagService()
        self.data = fixture()
        self.service._load = lambda season: self.data

    def test_home_and_away_are_separate_and_exclude_draws(self):
        home = self.service.ask('삼성 홈 성적은?', 2026)
        away = self.service.ask('삼성 원정 성적은?', 2026)
        self.assertEqual(home['evidence'][0]['payload']['games'], 2)
        self.assertEqual(home['evidence'][0]['payload']['win_rate'], 1)
        self.assertEqual(away['evidence'][0]['payload']['win_rate'], 0)
        self.assertIn('2026-04-02', home['answer']['bullets'][0])

    def test_answers_cite_leaders_outside_retrieved_top_eight(self):
        result = self.service.ask('MVP는 누구야?', 2026)
        names = {item['payload']['player'] for item in result['evidence']}
        self.assertEqual(names, {'선수11', '선수10', '선수9', '선수8', '선수7'})
        self.assertIn('선수11', result['answer']['title'])

    def test_unsupported_question_does_not_fall_back_to_team_summary(self):
        for question in ('삼성 연봉 알려줘', '삼성 내일 우승 확률은?', '김치찌개 맛집 알려줘'):
            result = self.service.ask(question, 2026)
            self.assertEqual(result['answer'], NO_EVIDENCE_ANSWER)
            self.assertEqual(result['evidence'], [])

    def test_homerun_is_not_home_split(self):
        result = self.service.ask('삼성 홈런 순위는?', 2026)
        self.assertTrue(all(item['payload']['type'] == 'hitter' for item in result['evidence']))
        self.assertIn('HR', result['answer']['title'])

    def test_team_specific_recent_question_stays_on_team(self):
        result = self.service.ask('lg 최근 성적 어때?', 2026)
        self.assertIn('LG', result['answer']['title'])
        self.assertEqual(result['evidence'][0]['payload']['team'], 'LG')

    def test_ops_ranking_uses_ops_instead_of_war(self):
        self.data['hitters'].loc[0, 'OPS'] = 1.5
        result = self.service.ask('OPS 1위는 누구야?', 2026)
        self.assertIn('선수0', result['answer']['title'])
        self.assertIn('OPS', result['answer']['title'])

    def test_split_comparison_includes_both_sides(self):
        result = self.service.ask('삼성 홈 원정 비교해줘', 2026)
        self.assertEqual({item['payload']['split'] for item in result['evidence']}, {'홈', '원정'})

    def test_missing_game_totals_are_not_reported_as_zero(self):
        self.data['team_games'] = pd.DataFrame()
        result = self.service.ask('삼성 어때?', 2026)
        self.assertIsNone(result['evidence'][0]['payload']['run_diff'])
        self.assertIn('수집되지', result['answer']['summary'])

    def test_monthly_answer_cites_monthly_rows_without_claiming_causation(self):
        self.data['team_monthly'] = pd.DataFrame([
            {'Team': '삼성', 'Month': month, 'Games': wins + losses, 'Wins': wins,
             'Losses': losses, 'WinRate': wins / (wins + losses), 'RunDiff': wins - losses}
            for month, wins, losses in [(4, 6, 4), (5, 8, 2), (6, 5, 5), (7, 2, 8)]
        ])
        result = self.service.ask('삼성 왜 부진해?', 2026)
        self.assertEqual(len([item for item in result['evidence'] if item['payload']['type'] == 'monthly']), 4)
        self.assertIn('원인을 단정할 수는 없습니다', result['answer']['summary'])

    def test_missing_split_data_does_not_invent_zero_record(self):
        self.data['team_games'] = pd.DataFrame()
        result = self.service.ask('삼성 홈 성적은?', 2026)
        self.assertEqual(result['answer'], NO_EVIDENCE_ANSWER)


class CsvRefreshTest(unittest.TestCase):
    def test_rag_notices_file_creation_change_and_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('services.rag_service.RAW_DIR', root), patch('services.rag_service.PROCESSED_DIR', root):
                service = RagService()
                self.assertTrue(service._load(2026)['standings'].empty)
                path = root / 'kbo_team_rank_2026.csv'
                path.write_text('팀명,승\n삼성,1\n')
                first = service._load(2026)
                self.assertEqual(first['standings'].iloc[0]['승'], 1)
                self.assertIs(service._load(2026), first)
                path.write_text('팀명,승\n삼성,22\n')
                self.assertEqual(service._load(2026)['standings'].iloc[0]['승'], 22)
                path.unlink()
                self.assertTrue(service._load(2026)['standings'].empty)

    def test_story_csv_change_invalidates_generated_story(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('services.story_service.RAW_DIR', root), patch('services.story_service.PROCESSED_DIR', root):
                service = StoryService()
                service._load_csv(2026)
                service._story_cache['game'] = (0, {})
                path = root / 'kbo_team_rank_2026.csv'
                path.write_text('팀명,승\n삼성,2\n')
                self.assertEqual(service._load_csv(2026)['standings'].iloc[0]['승'], 2)
                self.assertEqual(service._story_cache, {})


if __name__ == '__main__':
    unittest.main()
