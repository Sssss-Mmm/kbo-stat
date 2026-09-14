import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers.rag import router, qa_service
from security import limit_expensive_requests


class QAApiTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router, prefix='/api')
        app.dependency_overrides[limit_expensive_requests] = lambda: None
        self.client = TestClient(app)

    def test_history_is_passed_and_system_role_is_rejected(self):
        body = {'question': '그럼 LG랑 비교하면?', 'season': 2026,
                'history': [{'role': 'user', 'content': '삼성 최근 성적은?'}]}
        with patch.object(qa_service, 'ask', return_value={'status': 'success'}) as ask:
            self.assertEqual(self.client.post('/api/rag/ask', json=body).status_code, 200)
            self.assertEqual(ask.call_args.args[2], body['history'])
            body['history'][0]['role'] = 'system'
            self.assertEqual(self.client.post('/api/rag/ask', json=body).status_code, 422)
            self.assertEqual(ask.call_count, 1)

    def test_history_and_question_size_limits(self):
        for body in ({'question': '가' * 2001},
                     {'question': '삼성', 'history': [{'role': 'user', 'content': '가' * 1001}]},
                     {'question': '삼성', 'history': [{'role': 'user', 'content': '질문'}] * 5}):
            self.assertEqual(self.client.post('/api/rag/ask', json=body).status_code, 422)


if __name__ == '__main__':
    unittest.main()
