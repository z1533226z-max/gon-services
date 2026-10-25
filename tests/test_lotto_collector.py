import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.executors.base import run_job
from apscheduler.job import Job
from apscheduler.triggers.date import DateTrigger

from app.core.scheduler import _run_sync, scheduler

ROOT = Path(__file__).resolve().parents[1]
ROUND = {'draw_no': 1201, 'date': '2026-10-24',
         'numbers': [1, 2, 3, 4, 5, 6], 'bonus_no': 7}


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.config = ModuleType('app.config')
        self.config.get_settings = lambda: SimpleNamespace(lotto_api_url='https://test.invalid')
        self.database = ModuleType('app.core.database')
        self.database.execute_one = Mock(return_value={'max_round': 1200})
        self.database.execute_query = Mock(return_value=[])
        self.database.execute_insert = Mock()
        self.database.test_connection = Mock(return_value=True)
        self.modules = {'app.config': self.config, 'app.core.database': self.database}
        with patch.dict(sys.modules, self.modules):
            self.collector = self.load('app/services/lotto_collector.py', 'test_collector')
        self.client = Mock()
        factory = patch.object(httpx, 'Client').start()
        factory.return_value.__enter__.return_value = self.client
        self.sleep = patch('time.sleep').start()
        self.addCleanup(patch.stopall)

    def load(self, relative, name):
        spec = importlib.util.spec_from_file_location(name, ROOT / relative)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def response(self, status, data=None):
        return httpx.Response(status, request=httpx.Request('GET', 'https://test.invalid'), json=data)

    def run_job(self):
        job = Job(scheduler, id='collector-test', func=_run_sync,
                  args=[self.collector.collect_latest], kwargs={},
                  misfire_grace_time=None, trigger=DateTrigger())
        return run_job(job, 'default', [datetime.now(timezone.utc)], 'test.collector')

    def test_actual_failures_retry_and_emit_error(self):
        for case in ('timeout', 'http503', 'insert-failure'):
            with self.subTest(case=case):
                self.client.get.reset_mock(side_effect=True)
                self.database.execute_insert.reset_mock(side_effect=True)
                self.sleep.reset_mock()
                self.client.get.return_value = self.response(503 if case == 'http503' else 200, ROUND)
                if case == 'timeout':
                    self.client.get.side_effect = httpx.TimeoutException('synthetic timeout')
                if case == 'insert-failure':
                    self.database.execute_insert.side_effect = RuntimeError('synthetic insert failure')
                events = self.run_job()
                self.assertEqual([event.code for event in events], [EVENT_JOB_ERROR])
                self.assertEqual(self.client.get.call_count, 2)
                self.sleep.assert_called_once_with(30)

    def test_unpublished_round_is_success_without_retry(self):
        self.client.get.return_value = self.response(404)
        self.assertEqual([event.code for event in self.run_job()], [EVENT_JOB_EXECUTED])
        self.sleep.assert_not_called()
        self.database.execute_insert.assert_not_called()

    def test_success_inserts_then_stops_at_unpublished_round(self):
        self.client.get.side_effect = [self.response(200, ROUND), self.response(404)]
        self.assertEqual(self.collector.collect_latest(), 'collected 1 rounds (1201~1201)')
        values = self.database.execute_insert.call_args.args[1]
        self.assertEqual(values[:9], (1201, '2026-10-24', 1, 2, 3, 4, 5, 6, 7))

    def test_invalid_payload_is_failure(self):
        for data in ({}, None, []):
            with self.subTest(data=data):
                self.client.get.return_value = self.response(200, data)
                with self.assertRaises(ValueError):
                    self.collector.collect_latest()

    def test_range_skips_existing_and_unpublished_rounds(self):
        self.database.execute_query.return_value = [{'round': 1200}]
        self.client.get.side_effect = [self.response(200, ROUND), self.response(404)]
        self.assertEqual(self.collector.collect_range(1200, 1202), 'collected=1, skipped=1')
        self.assertEqual(self.client.get.call_count, 2)

    def test_range_propagates_server_and_storage_failures(self):
        self.client.get.return_value = self.response(503)
        with self.assertRaises(httpx.HTTPStatusError):
            self.collector.collect_range(1201, 1201)
        self.client.get.return_value = self.response(200, ROUND)
        self.database.execute_insert.side_effect = RuntimeError('synthetic insert failure')
        with self.assertRaises(RuntimeError):
            self.collector.collect_range(1201, 1201)

    def test_manual_api_returns_500_for_real_collector_failure(self):
        from fastapi import HTTPException
        with patch.dict(sys.modules, {**self.modules, 'app.services.lotto_collector': self.collector}):
            api = self.load('app/api/endpoints/lotto.py', 'test_lotto_api')
            self.client.get.return_value = self.response(503)
            with self.assertRaises(HTTPException) as raised:
                api.trigger_collect()
        self.assertEqual(raised.exception.status_code, 500)
        self.assertEqual(raised.exception.detail, '수집 실패')

    def test_seeding_does_not_report_success_after_collection_failure(self):
        migrations = ModuleType('app.core.migrations')
        migrations.run_migrations = Mock()
        with patch.dict(sys.modules, {**self.modules, 'app.core.migrations': migrations,
                                     'app.services.lotto_collector': self.collector}), \
             patch.object(sys, 'argv', ['seed_from_api', '--from', '1201', '--to', '1201']):
            seed = self.load('scripts/seed_from_api.py', 'test_seed')
            self.client.get.return_value = self.response(503)
            with self.assertRaises(httpx.HTTPStatusError):
                seed.main()
