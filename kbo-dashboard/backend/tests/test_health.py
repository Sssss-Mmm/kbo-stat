import importlib
import unittest
from unittest.mock import patch, MagicMock

from sqlalchemy.exc import OperationalError


class ReadinessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch('database.init_db'):
            cls.app_module = importlib.import_module('main')

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
