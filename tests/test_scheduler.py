import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.executors.base import run_job
from apscheduler.job import Job
from apscheduler.triggers.date import DateTrigger

from app.core.scheduler import _job_error_listener, _run_sync, scheduler


class SchedulerRetryTests(unittest.TestCase):
    @patch('time.sleep')
    def test_exhausted_retry_raises_original_error(self, sleep):
        error = RuntimeError('fake collector unavailable')
        collect = Mock(side_effect=error, __name__='fake_collect')
        with self.assertRaises(RuntimeError) as raised:
            _run_sync(collect)
        self.assertIs(raised.exception, error)
        self.assertEqual(collect.call_count, 2)
        sleep.assert_called_once_with(30)

    @patch('time.sleep')
    def test_second_attempt_can_recover(self, sleep):
        collect = Mock(side_effect=[RuntimeError('temporary'), None], __name__='fake_collect')
        _run_sync(collect)
        self.assertEqual(collect.call_count, 2)
        sleep.assert_called_once_with(30)

    @patch('time.sleep')
    def test_first_attempt_does_not_retry(self, sleep):
        collect = Mock(__name__='fake_collect')
        _run_sync(collect, 1200)
        collect.assert_called_once_with(1200)
        sleep.assert_not_called()

    @patch('time.sleep')
    def test_real_executor_emits_failure_event_and_listener_logs(self, sleep):
        error = RuntimeError('fake persistent outage')
        collect = Mock(side_effect=error, __name__='fake_collect')
        job = Job(scheduler, id='test-collect', func=_run_sync,
                  args=[collect], kwargs={}, misfire_grace_time=None,
                  trigger=DateTrigger())
        with self.assertLogs('test.scheduler', level='ERROR') as logs:
            events = run_job(job, 'default', [datetime.now(timezone.utc)], 'test.scheduler')
        self.assertIn('raised an exception', logs.output[0])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].code, EVENT_JOB_ERROR)
        self.assertNotEqual(events[0].code, EVENT_JOB_EXECUTED)
        self.assertIs(events[0].exception, error)
        with patch('app.core.scheduler.logger') as logger:
            _job_error_listener(events[0])
            self.assertIn('test-collect', logger.error.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
