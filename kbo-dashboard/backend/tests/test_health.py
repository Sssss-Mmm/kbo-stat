import importlib
import unittest
from unittest.mock import patch, MagicMock

from sqlalchemy.exc import OperationalError


class ReadinessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_module = importlib.import_module('main')  # import 만으로는 DB 에 접속하지 않는다

    def setUp(self):
        # DB 판정만 본다 — 데이터 준비 판정은 고정(로컬 data/ 유무와 무관하게). 데이터 쪽은 test_data_check 가 본다.
        ready = {'ready': True, 'mount': 'image', 'season': 2026, 'problems': [], 'optional_missing': [], 'required': {}}
        patcher = patch.object(self.app_module.data_check, 'check', return_value=ready)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_available_database_is_ready(self):
        connection = MagicMock()
        with patch.object(self.app_module.engine, 'connect') as connect:
            connect.return_value.__enter__.return_value = connection
            self.assertEqual(self.app_module.readiness_check()['status'], 'ready')
            self.assertEqual(str(connection.execute.call_args.args[0]), 'SELECT 1')

    def test_unavailable_database_returns_503(self):
        with patch.object(self.app_module.engine, 'connect', side_effect=OperationalError('SELECT 1', {}, Exception('offline'))):
            response = self.app_module.readiness_check()
            self.assertEqual(response.status_code, 503)
            self.assertIn(b'unavailable', response.body)
