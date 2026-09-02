#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for liveness/readiness probe servers."""
import json
import logging
import threading
import time
from unittest.mock import Mock
from unittest.mock import patch

from django.test import SimpleTestCase

from koku.celery import app as celery_app
from koku.celery import ParentHeartbeatStep
from koku.celery import wait_for_migrations
from koku.celery import WorkerProbeServer
from koku.probe_server import BasicProbeServer
from koku.probe_server import consumer_thread_is_alive
from koku.probe_server import get_probe_liveness_heartbeat_seconds
from koku.probe_server import install_parent_heartbeat
from koku.probe_server import parent_heartbeat_is_fresh
from koku.probe_server import ProbeServer
from koku.probe_server import register_consumer_thread
from koku.probe_server import reset_consumer_thread
from koku.probe_server import reset_parent_heartbeat
from koku.probe_server import touch_parent_heartbeat
from masu.external.kafka_msg_handler import initialize_kafka_handler
from masu.management.commands.listener import ListenerProbeServer
from sources.kafka_listener import initialize_sources_integration
from sources.management.commands.sources_listener import SourcesProbeServer


class ProbeServerTestCase(SimpleTestCase):
    """Shared probe-handler helpers."""

    def setUp(self):
        super().setUp()
        reset_parent_heartbeat()
        reset_consumer_thread()
        ProbeServer.ready = False
        WorkerProbeServer.ready = False
        ListenerProbeServer.ready = False
        SourcesProbeServer.ready = False
        BasicProbeServer.ready = False

    def tearDown(self):
        reset_parent_heartbeat()
        reset_consumer_thread()
        ProbeServer.ready = False
        WorkerProbeServer.ready = False
        ListenerProbeServer.ready = False
        SourcesProbeServer.ready = False
        BasicProbeServer.ready = False
        super().tearDown()

    def bind_handler(self, cls, *, ready=False, path="/livez"):
        """Build a handler without a real HTTP socket."""
        handler = cls.__new__(cls)
        handler.ready = ready
        handler.path = path
        handler.logger = logging.getLogger("koku.test.test_probe_server")
        handler.log_level = None
        handler.written = None

        def _write_response(response):
            handler.written = response

        handler._write_response = _write_response
        return handler

    def response_payload(self, handler):
        self.assertIsNotNone(handler.written)
        return json.loads(handler.written.json)

    def assert_livez_status(self, handler, status_code):
        handler.liveness_check()
        payload = self.response_payload(handler)
        self.assertEqual(payload["status"], status_code)
        self.assertEqual(handler.written.status_code, status_code)
        return payload

    def start_blocked_thread(self):
        """Thread blocked in wait(), standing in for listen_for_messages."""
        release = threading.Event()
        started = threading.Event()

        def _run():
            started.set()
            release.wait(timeout=30)

        thread = threading.Thread(target=_run, name="test-blocked-consumer")
        thread.start()

        def _stop():
            release.set()
            thread.join(timeout=2)

        self.addCleanup(_stop)
        self.assertTrue(started.wait(timeout=2))
        return thread

    def dead_thread(self):
        thread = threading.Thread(target=lambda: None, name="test-dead-consumer")
        thread.start()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        return thread


class WorkerProbeLivenessTests(ProbeServerTestCase):
    """Worker /livez uses the parent heartbeat, not child or task-finished state."""

    def test_livez_fails_when_parent_heartbeat_missing_after_startup(self):
        """Wedged/missing parent heartbeat after startup must not stay 200."""
        handler = self.bind_handler(WorkerProbeServer, ready=True)
        payload = self.assert_livez_status(handler, 503)
        self.assertIn("heartbeat", payload["msg"].lower())

    def test_livez_fails_when_parent_heartbeat_is_stale_after_startup(self):
        """Heartbeat older than the threshold is treated as a wedged parent."""
        now = time.monotonic()
        threshold = get_probe_liveness_heartbeat_seconds()
        with patch("koku.probe_server.time.monotonic", return_value=now):
            touch_parent_heartbeat()
        with patch("koku.probe_server.time.monotonic", return_value=now + threshold + 1):
            handler = self.bind_handler(WorkerProbeServer, ready=True)
            payload = self.assert_livez_status(handler, 503)
        self.assertIn("heartbeat", payload["msg"].lower())

    def test_livez_200_when_parent_heartbeat_fresh_and_child_busy(self):
        """A child busy in SQL must not fail /livez while the parent still ticks."""
        touch_parent_heartbeat()
        handler = self.bind_handler(WorkerProbeServer, ready=True)
        handler.busy_children = ["child-pid-in-sql"]
        self.assert_livez_status(handler, 200)

    def test_livez_ignores_last_task_finished_clock(self):
        """Heartbeat is not last-task-finished: a 25h-old task clock still yields 200."""
        touch_parent_heartbeat()
        handler = self.bind_handler(WorkerProbeServer, ready=True)
        handler.last_task_finished = time.monotonic() - 25 * 3600
        self.assert_livez_status(handler, 200)
        self.assertFalse(hasattr(WorkerProbeServer, "last_task_finished"))

    def test_readyz_unchanged_no_db_or_redis(self):
        """Worker /readyz still follows ready only (no DB/Redis)."""
        handler = self.bind_handler(WorkerProbeServer, ready=False)
        handler.readiness_check()
        self.assertEqual(handler.written.status_code, 424)

        handler = self.bind_handler(WorkerProbeServer, ready=True)
        handler.readiness_check()
        self.assertEqual(handler.written.status_code, 200)
        self.assertEqual(self.response_payload(handler)["msg"], "ok")


class WaitForMigrationsHeartbeatTests(ProbeServerTestCase):
    """wait_for_migrations must touch the parent heartbeat and install the timer."""

    def test_heartbeat_touched_during_migration_wait_livez_200_readyz_424(self):
        """Kube must not kill the pod while migrations sleep; /readyz stays 424."""
        fake_timer = Mock()
        instance = Mock()
        instance.timer = fake_timer
        httpd = Mock()
        httpd.RequestHandlerClass = WorkerProbeServer

        def on_sleep(_seconds):
            self.assertFalse(WorkerProbeServer.ready)
            self.assertTrue(parent_heartbeat_is_fresh())
            live = self.bind_handler(WorkerProbeServer, ready=False)
            self.assert_livez_status(live, 200)
            live.readiness_check()
            self.assertEqual(live.written.status_code, 424)

        with (
            patch("koku.celery.start_probe_server", return_value=httpd) as mock_start,
            patch("koku.database.check_migrations", side_effect=[False, True]),
            patch("koku.celery.time.sleep", side_effect=on_sleep) as mock_sleep,
        ):
            wait_for_migrations(sender="celery@test", instance=instance)

        mock_start.assert_called_once_with(WorkerProbeServer)
        mock_sleep.assert_called_once_with(5)
        self.assertTrue(WorkerProbeServer.ready)
        self.assertTrue(parent_heartbeat_is_fresh())
        fake_timer.call_repeatedly.assert_called()

    def test_wait_for_migrations_touches_heartbeat_when_migrations_already_done(self):
        """Immediate-ready workers still seed a heartbeat before the hub runs."""
        fake_timer = Mock()
        instance = Mock()
        instance.timer = fake_timer
        httpd = Mock()
        httpd.RequestHandlerClass = WorkerProbeServer

        with (
            patch("koku.celery.start_probe_server", return_value=httpd),
            patch("koku.database.check_migrations", return_value=True),
            patch("koku.celery.time.sleep") as mock_sleep,
        ):
            wait_for_migrations(sender="celery@test", instance=instance)

        mock_sleep.assert_not_called()
        self.assertTrue(parent_heartbeat_is_fresh())
        fake_timer.call_repeatedly.assert_called()


class ParentHeartbeatHelperTests(ProbeServerTestCase):
    """install_parent_heartbeat must tick via the provided timer, not a daemon thread."""

    def test_install_parent_heartbeat_registers_timer_and_touches(self):
        fake_timer = Mock()
        install_parent_heartbeat(fake_timer)

        self.assertTrue(parent_heartbeat_is_fresh())
        fake_timer.call_repeatedly.assert_called_once()
        interval, callback = fake_timer.call_repeatedly.call_args[0][:2]
        self.assertLess(interval, get_probe_liveness_heartbeat_seconds())
        self.assertGreaterEqual(interval, 1)

        reset_parent_heartbeat()
        self.assertFalse(parent_heartbeat_is_fresh())
        callback()
        self.assertTrue(parent_heartbeat_is_fresh())

    def test_install_parent_heartbeat_does_not_start_a_thread(self):
        before = threading.active_count()
        install_parent_heartbeat(Mock())
        self.assertEqual(threading.active_count(), before)


class _FakeHubTimer:
    """Stand-in for kombu hub.timer: call_repeatedly + clear, no daemon thread."""

    def __init__(self):
        self.entries = []

    def call_repeatedly(self, interval, fun, *args, **kwargs):
        self.entries.append((interval, fun, args, kwargs))

    def clear(self):
        self.entries.clear()

    def fire(self):
        for _interval, fun, args, kwargs in list(self.entries):
            fun(*args, **kwargs)


class ParentHeartbeatReconnectTests(ProbeServerTestCase):
    """Celery asynloop hub.timer.clear() on broker errors must re-arm /livez."""

    def _worker_and_hub(self, timer):
        hub = Mock()
        hub.timer = timer
        worker = Mock()
        worker.timer = timer
        worker.hub = hub
        return worker, hub

    def test_parent_heartbeat_step_is_on_worker_blueprint(self):
        self.assertIn(ParentHeartbeatStep, celery_app.steps["worker"])

    def test_rearm_after_timer_clear_keeps_livez_200(self):
        """Reconnect re-arm: after clear(), advancing past the threshold stays 200."""
        timer = _FakeHubTimer()
        worker, hub = self._worker_and_hub(timer)
        now = 1_000.0
        threshold = get_probe_liveness_heartbeat_seconds()

        with patch("koku.probe_server.time.monotonic", return_value=now):
            install_parent_heartbeat(timer)

        timer.clear()
        self.assertEqual(timer.entries, [])

        rearm_at = now + 5
        with patch("koku.probe_server.time.monotonic", return_value=rearm_at):
            ParentHeartbeatStep(worker).register_with_event_loop(worker, hub)
        self.assertTrue(timer.entries)

        later = rearm_at + threshold + 1
        with patch("koku.probe_server.time.monotonic", return_value=later):
            timer.fire()
            handler = self.bind_handler(WorkerProbeServer, ready=True)
            self.assert_livez_status(handler, 200)

    def test_timer_clear_without_rearm_fails_livez_after_threshold(self):
        """If call_repeatedly is not put back, a healthy-looking probe thread still 503s."""
        timer = _FakeHubTimer()
        now = 1_000.0
        threshold = get_probe_liveness_heartbeat_seconds()

        with patch("koku.probe_server.time.monotonic", return_value=now):
            install_parent_heartbeat(timer)

        timer.clear()
        self.assertEqual(timer.entries, [])

        later = now + threshold + 1
        with patch("koku.probe_server.time.monotonic", return_value=later):
            timer.fire()
            handler = self.bind_handler(WorkerProbeServer, ready=True)
            payload = self.assert_livez_status(handler, 503)
        self.assertIn("heartbeat", payload["msg"].lower())

    def test_rearm_does_not_start_a_thread(self):
        timer = _FakeHubTimer()
        worker, hub = self._worker_and_hub(timer)
        before = threading.active_count()
        ParentHeartbeatStep(worker).register_with_event_loop(worker, hub)
        self.assertEqual(threading.active_count(), before)


class ListenerProbeLivenessTests(ProbeServerTestCase):
    """Listener /livez fails only when the consumer thread is dead after ready."""

    def test_livez_fails_when_ready_and_consumer_thread_dead(self):
        register_consumer_thread(self.dead_thread())
        handler = self.bind_handler(ListenerProbeServer, ready=True)
        payload = self.assert_livez_status(handler, 503)
        self.assertIn("thread", payload["msg"].lower())

    def test_livez_fails_when_ready_and_consumer_thread_missing(self):
        handler = self.bind_handler(ListenerProbeServer, ready=True)
        payload = self.assert_livez_status(handler, 503)
        self.assertIn("thread", payload["msg"].lower())

    def test_livez_200_when_consumer_thread_blocked_in_processing(self):
        register_consumer_thread(self.start_blocked_thread())
        handler = self.bind_handler(ListenerProbeServer, ready=True)
        self.assert_livez_status(handler, 200)

    def test_livez_200_before_ready_without_consumer_thread(self):
        handler = self.bind_handler(ListenerProbeServer, ready=False)
        self.assert_livez_status(handler, 200)

    @patch("masu.management.commands.listener.check_kafka_connection")
    def test_readyz_still_checks_kafka_when_ready(self, mock_kafka):
        handler = self.bind_handler(ListenerProbeServer, ready=True)

        mock_kafka.return_value = False
        handler.readiness_check()
        self.assertEqual(handler.written.status_code, 424)
        self.assertIn("kafka", self.response_payload(handler)["msg"].lower())
        mock_kafka.assert_called_once()

        mock_kafka.reset_mock()
        mock_kafka.return_value = True
        handler.readiness_check()
        self.assertEqual(handler.written.status_code, 200)
        self.assertEqual(self.response_payload(handler)["msg"], "ok")
        mock_kafka.assert_called_once()

    def test_readyz_424_when_not_ready_without_kafka_check(self):
        handler = self.bind_handler(ListenerProbeServer, ready=False)
        with patch("masu.management.commands.listener.check_kafka_connection") as mock_kafka:
            handler.readiness_check()
        self.assertEqual(handler.written.status_code, 424)
        mock_kafka.assert_not_called()


class SourcesProbeLivenessTests(ProbeServerTestCase):
    """Sources-listener /livez matches listener consumer-thread behavior."""

    def test_livez_fails_when_ready_and_consumer_thread_dead(self):
        register_consumer_thread(self.dead_thread())
        handler = self.bind_handler(SourcesProbeServer, ready=True)
        payload = self.assert_livez_status(handler, 503)
        self.assertIn("thread", payload["msg"].lower())

    def test_livez_fails_when_ready_and_consumer_thread_missing(self):
        handler = self.bind_handler(SourcesProbeServer, ready=True)
        payload = self.assert_livez_status(handler, 503)
        self.assertIn("thread", payload["msg"].lower())

    def test_livez_200_when_consumer_thread_alive(self):
        register_consumer_thread(self.start_blocked_thread())
        handler = self.bind_handler(SourcesProbeServer, ready=True)
        self.assert_livez_status(handler, 200)

    def test_livez_200_before_ready_without_consumer_thread(self):
        handler = self.bind_handler(SourcesProbeServer, ready=False)
        self.assert_livez_status(handler, 200)


class BasicProbeServerTests(ProbeServerTestCase):
    """Gunicorn BasicProbeServer liveness stays always-200."""

    def test_livez_always_200(self):
        for ready in (False, True):
            with self.subTest(ready=ready):
                reset_parent_heartbeat()
                handler = self.bind_handler(BasicProbeServer, ready=ready)
                self.assert_livez_status(handler, 200)

    def test_readyz_follows_ready(self):
        handler = self.bind_handler(BasicProbeServer, ready=False)
        handler.readiness_check()
        self.assertEqual(handler.written.status_code, 424)

        handler = self.bind_handler(BasicProbeServer, ready=True)
        handler.readiness_check()
        self.assertEqual(handler.written.status_code, 200)

    def test_unknown_path_returns_404(self):
        handler = self.bind_handler(BasicProbeServer, path="/not-a-probe")
        handler.do_GET()
        self.assertEqual(handler.written.status_code, 404)

    def test_do_get_livez_routes_to_liveness_check(self):
        handler = self.bind_handler(BasicProbeServer, ready=True, path="/livez")
        handler.do_GET()
        self.assertEqual(handler.written.status_code, 200)


class ConsumerThreadRegistryTests(ProbeServerTestCase):
    """initialize_* must register the consumer thread used by /livez."""

    def test_initialize_kafka_handler_registers_consumer_thread(self):
        fake_thread = Mock()
        fake_thread.is_alive.return_value = True
        with (
            patch("masu.external.kafka_msg_handler.Config") as mock_config,
            patch("masu.external.kafka_msg_handler.threading.Thread", return_value=fake_thread),
        ):
            mock_config.KAFKA_CONNECT = True
            initialize_kafka_handler()

        fake_thread.start.assert_called_once()
        fake_thread.join.assert_called_once()
        self.assertTrue(consumer_thread_is_alive())
        handler = self.bind_handler(ListenerProbeServer, ready=True)
        self.assert_livez_status(handler, 200)

    def test_initialize_kafka_handler_skips_when_kafka_connect_disabled(self):
        with (
            patch("masu.external.kafka_msg_handler.Config") as mock_config,
            patch("masu.external.kafka_msg_handler.threading.Thread") as mock_thread_cls,
        ):
            mock_config.KAFKA_CONNECT = False
            initialize_kafka_handler()
        mock_thread_cls.assert_not_called()

    def test_initialize_sources_integration_registers_consumer_thread(self):
        fake_thread = Mock()
        fake_thread.is_alive.return_value = True
        with patch("sources.kafka_listener.threading.Thread", return_value=fake_thread):
            initialize_sources_integration()

        fake_thread.start.assert_called_once()
        fake_thread.join.assert_called_once()
        self.assertTrue(consumer_thread_is_alive())
        handler = self.bind_handler(SourcesProbeServer, ready=True)
        self.assert_livez_status(handler, 200)
