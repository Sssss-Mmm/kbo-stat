import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pandas as pd

from services.ai_budget import AIBudget
from services.qa_analysis import analyze, AnalysisUnavailable
from services.qa_models import AnalysisPlan, AnalysisAnswer
from services.qa_service import QuestionAnswerService, AIUnavailable


def fixture():
    games = []
    for team in ('삼성', 'LG'):
        for i, day in enumerate(pd.date_range('2026-04-01', periods=24)):
            won = i < 14 if team == '삼성' else i >= 14
            games.append(dict(Team=team, Opponent='LG' if team == '삼성' else '삼성', Date=str(day.date()),
                GameId=str(i), HomeAway='home' if i % 2 else 'away', Win=int(won), Loss=int(not won), Draw=0,
                RunsFor=6 if won else 2, RunsAgainst=2 if won else 6))
    return {'team_games': pd.DataFrame(games), 'standings': pd.DataFrame(), 'team_monthly': pd.DataFrame(), 'hitters': pd.DataFrame(),
        'batters': pd.DataFrame([{'선수명': '김도영', '팀명': '삼성', 'OPS': .9, 'WAR': 5., '규정충족': True},
                                {'선수명': '오스틴', '팀명': 'LG', 'OPS': 1., 'WAR': 6., '규정충족': True}]),
        'pitchers': pd.DataFrame([{'선수명': '곽빈', '팀명': '삼성', 'ERA': 2., 'WHIP': 1., '규정충족': True},
                                 {'선수명': '표본작음', '팀명': 'LG', 'ERA': 0., 'WHIP': .5, '규정충족': False}])}


class AnalysisTests(unittest.TestCase):
    def test_recent_uses_latest_collected_games_and_disjoint_previous_window(self):
        evidence, notes, scope = analyze(AnalysisPlan(kind='team', season=2026, teams=['삼성'], period='recent'), fixture())
        change = next(e['payload'] for e in evidence if 'previous' in e['payload'])
        self.assertEqual(change['current']['games'], 10)
        self.assertEqual(change['previous']['games'], 10)
        self.assertEqual(change['current']['from'], '2026-04-15')
        self.assertEqual(change['previous']['through'], '2026-04-14')
        self.assertEqual(change['win_rate_change'], -1.)
        self.assertEqual(change['runs_per_game_change'], -4.)
        self.assertEqual(change['allowed_per_game_change'], 4.)
        self.assertIn('2026-04-24', scope)

    def test_team_comparison_keeps_both_teams(self):
        evidence, _, _ = analyze(AnalysisPlan(kind='team', season=2026, teams=['삼성', 'LG']), fixture())
        comparison = next(e['payload']['comparison'] for e in evidence if 'comparison' in e['payload'])
        self.assertEqual({r['team'] for r in comparison}, {'삼성', 'LG'})

    def test_draws_excluded_and_missing_games_not_zero(self):
        data = fixture()
        data['team_games'].loc[0, ['Win', 'Loss', 'Draw']] = [0, 0, 1]
        evidence, _, _ = analyze(AnalysisPlan(kind='team', season=2026, teams=['삼성']), data)
        self.assertEqual(evidence[0]['payload']['win_rate'], round(13 / 23, 3))
        with self.assertRaises(AnalysisUnavailable):
            analyze(AnalysisPlan(kind='team', season=2026, teams=['삼성'], period='month', month=8), data)

    def test_home_away_and_opponent_filters(self):
        evidence, _, _ = analyze(AnalysisPlan(kind='team', season=2026, teams=['삼성'], split='compare', opponent='LG'), fixture())
        splits = [e['payload'] for e in evidence if 'split' in e['payload']]
        self.assertEqual({p['split'] for p in splits}, {'홈', '원정'})
        self.assertEqual([p['games'] for p in splits], [12, 12])

    def test_player_qualification_sorting_and_no_fake_recent_stats(self):
        plan = AnalysisPlan(kind='player', season=2026, role='pitcher', metric='ERA')
        evidence, _, _ = analyze(plan, fixture())
        self.assertEqual(len(evidence), 1)
        self.assertIn('곽빈', evidence[0]['title'])
        evidence, _, _ = analyze(plan.model_copy(update={'qualified_only': False}), fixture())
        self.assertIn('표본작음', evidence[0]['title'])
        with self.assertRaises(AnalysisUnavailable):
            analyze(plan.model_copy(update={'period': 'recent'}), fixture())

    def test_bad_date_and_missing_player_are_not_silently_ignored(self):
        with self.assertRaises(AnalysisUnavailable):
            analyze(AnalysisPlan(kind='team', season=2026, period='range', start_date='2026-02-30', end_date='2026-03-01'), fixture())
        with self.assertRaises(AnalysisUnavailable):
            analyze(AnalysisPlan(kind='player', season=2026, players=['없는선수']), fixture())

    def test_same_name_on_two_teams_asks_for_team(self):
        data = fixture()
        data['batters'] = pd.concat([data['batters'], pd.DataFrame([{'선수명': '김도영', '팀명': 'LG', 'OPS': .5, '규정충족': True}])])
        with self.assertRaisesRegex(AnalysisUnavailable, 'LG·삼성'):
            analyze(AnalysisPlan(kind='player', season=2026, players=['김도영']), data)
        evidence, _, _ = analyze(AnalysisPlan(kind='player', season=2026, players=['김도영'], teams=['삼성']), data)
        self.assertEqual(evidence[0]['payload']['OPS'], .9)


class OrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.service = QuestionAnswerService()
        self.service._load = lambda season: fixture()

    def test_fallback_followup_retains_target_and_period(self):
        with patch('services.qa_service.structured_call', side_effect=AIUnavailable('offline')):
            response = self.service.ask('그럼 LG랑 비교하면?', 2026, [{'role': 'user', 'content': '삼성 최근 10경기 분석해줘'}])
        self.assertEqual(set(response['plan']['teams']), {'삼성', 'LG'})
        self.assertEqual(response['plan']['period'], 'recent')
        self.assertTrue(response['evidence'])

    def test_fallback_new_question_ending_with_eun_does_not_inherit_teams(self):
        with patch('services.qa_service.structured_call', side_effect=AIUnavailable('offline')):
            response = self.service.ask('삼성 홈 성적은?', 2026, [{'role': 'user', 'content': 'LG 최근 10경기 분석해줘'}])
        self.assertEqual(response['plan']['teams'], ['삼성'])
        self.assertEqual(response['plan']['period'], 'all')

    def test_league_followups_do_not_name_a_default_team(self):
        with patch('services.qa_service.structured_call', side_effect=AIUnavailable('offline')):
            response = self.service.ask('최근 가장 뜨거운 팀은?', 2026)
        self.assertFalse(any('삼성' in f for f in response['answer']['followups']))

    def test_budget_reserves_both_calls_and_refunds_unused(self):
        budget = AIBudget()
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test', 'AI_MAX_CALLS_PER_DAY': '3'}), patch('services.qa_service.ai_budget', budget):
            with patch('services.qa_service.structured_call', return_value=AnalysisPlan(kind='unsupported', season=2026)):
                self.service.ask('삼성 연봉 알려줘', 2026)
            self.assertEqual(len(budget.calls), 1)
            budget.take()
            with patch('services.qa_service.structured_call') as call:
                response = self.service.ask('삼성 최근 10경기', 2026)
            call.assert_not_called()
            self.assertIn('한도', response['notice'])
            self.assertEqual(len(budget.calls), 2)

    def test_ai_plan_executes_before_explanation_and_rejects_invalid_citations(self):
        plan = AnalysisPlan(kind='team', season=2026, teams=['삼성'], period='recent')
        answer = AnalysisAnswer(title='하락했습니다', summary='직전보다 승률이 낮습니다 [E1]', bullets=[], limitations=[], followups=[], evidence_ids=['E1'])
        with patch('services.qa_service.structured_call', side_effect=[plan, answer]) as call:
            response = self.service.ask('삼성 왜 못해?', 2026)
        self.assertEqual(response['mode'], 'ai')
        self.assertTrue(call.call_args_list[1].args[2]['evidence'])
        self.assertNotIn('metric', call.call_args_list[1].args[2]['plan'])
        with patch('services.qa_service.structured_call', side_effect=[plan, answer.model_copy(update={'evidence_ids': ['E999']})]):
            response = self.service.ask('삼성 왜 못해?', 2026)
        self.assertEqual(response['mode'], 'analysis')
        self.assertIn('인용', response['notice'])

    def test_unsupported_request_never_calls_explanation(self):
        with patch('services.qa_service.structured_call', return_value=AnalysisPlan(kind='unsupported', season=2026, clarification='연봉 데이터가 없습니다.')) as call:
            response = self.service.ask('삼성 연봉 알려줘', 2026)
        self.assertEqual(response['mode'], 'clarification')
        self.assertEqual(call.call_count, 1)
        self.assertEqual(response['evidence'], [])

    def test_response_is_json_safe(self):
        with patch('services.qa_service.structured_call', side_effect=AIUnavailable('offline')):
            response = self.service.ask('곽빈 ERA 알려줘', 2026)
        json.dumps(response, allow_nan=False)

    def test_shared_budget_is_atomic(self):
        budget = AIBudget()
        with patch.dict(os.environ, {'AI_MAX_CALLS_PER_DAY': '3'}):
            with ThreadPoolExecutor(max_workers=8) as pool:
                self.assertEqual(sum(pool.map(lambda _: budget.take(), range(20))), 3)


if __name__ == '__main__':
    unittest.main()
