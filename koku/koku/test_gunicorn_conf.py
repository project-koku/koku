import inspect
import sys
from unittest import TestCase
from unittest.mock import Mock
from unittest.mock import patch

import gunicorn_conf


class GunicornConfigTest(TestCase):
    @patch("gunicorn_conf.UNLEASH_CLIENT")
    def test_post_fork_initializes_unleash(self, mock_unleash):
        worker = Mock(pid=123)

        gunicorn_conf.post_fork(Mock(), worker)

        mock_unleash.initialize_client.assert_called_once_with()

    @patch("gunicorn_conf.threading.enumerate")
    @patch("gunicorn_conf.sys._current_frames")
    @patch("gunicorn_conf.ENVIRONMENT.bool", return_value=True)
    def test_worker_abort_reports_all_thread_stacks(self, mock_sentry_enabled, mock_current_frames, mock_threads):
        frame = inspect.currentframe()
        mock_current_frames.return_value = {123: frame}
        thread = Mock(ident=123)
        thread.name = "gunicorn-worker"
        mock_threads.return_value = [thread]
        sentry_sdk = Mock()
        worker = Mock(pid=456)

        with patch.dict(sys.modules, {"sentry_sdk": sentry_sdk}):
            gunicorn_conf.worker_abort(worker)

        event = sentry_sdk.capture_event.call_args.args[0]
        self.assertEqual(event["tags"], {"timeout": "hard"})
        self.assertEqual(event["message"], "Gunicorn worker timeout (pid:456)")
        self.assertEqual(event["threads"]["values"][0]["name"], "gunicorn-worker")
        self.assertNotIn("current", event["threads"]["values"][0])
        self.assertTrue(event["threads"]["values"][0]["stacktrace"]["frames"])
        sentry_sdk.flush.assert_called_once_with(timeout=1)
        self.assertIn("Thread gunicorn-worker (id: 123):", worker.log.warning.call_args.args[0])

    @patch("gunicorn_conf.ENVIRONMENT.bool", return_value=False)
    def test_worker_abort_skips_sentry_when_disabled(self, mock_sentry_enabled):
        sentry_sdk = Mock()
        worker = Mock(pid=456)

        with patch.dict(sys.modules, {"sentry_sdk": sentry_sdk}):
            gunicorn_conf.worker_abort(worker)

        sentry_sdk.capture_event.assert_not_called()
        worker.log.warning.assert_called_once()

    @patch("gunicorn_conf.ENVIRONMENT.bool", return_value=True)
    def test_worker_abort_survives_sentry_failure(self, mock_sentry_enabled):
        sentry_sdk = Mock()
        sentry_sdk.capture_event.side_effect = RuntimeError("Sentry unavailable")
        worker = Mock(pid=456)

        with patch.dict(sys.modules, {"sentry_sdk": sentry_sdk}):
            gunicorn_conf.worker_abort(worker)

        self.assertEqual(worker.log.warning.call_count, 2)
