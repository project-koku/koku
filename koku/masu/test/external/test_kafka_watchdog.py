"""Tests for diagnostic-only Kafka listener watchdog behavior."""
import json
from unittest.mock import Mock
from unittest.mock import patch

from django.test import SimpleTestCase

import masu.external.kafka_msg_handler as msg_handler
from masu.config import Config


class KafkaMessageWatchdogTest(SimpleTestCase):
    """Test the watchdog without requiring database fixtures."""

    def test_stops_after_normal_completion(self):
        """A completed handler does not produce a timeout diagnostic."""
        watchdog = msg_handler.KafkaMessageWatchdog({"request_id": "request-1"}, timeout_seconds=1)
        with patch.object(watchdog, "_emit_diagnostic") as emit_diagnostic:
            with watchdog:
                pass
        emit_diagnostic.assert_not_called()

    def test_emits_when_threshold_is_reached(self):
        """The monitor emits once the in-flight message reaches its threshold."""
        watchdog = msg_handler.KafkaMessageWatchdog({"request_id": "request-1"}, timeout_seconds=1)
        with (
            patch.object(
                watchdog, "_emit_diagnostic", side_effect=lambda *_args: watchdog._stop_event.set()
            ) as emit_diagnostic,
            patch(
                "masu.external.kafka_msg_handler.time.monotonic",
                return_value=watchdog._start_monotonic + watchdog.timeout_seconds,
            ),
        ):
            watchdog._monitor()
        emit_diagnostic.assert_called_once_with(watchdog.timeout_seconds)

    @patch("masu.external.kafka_msg_handler.sentry_sdk.capture_message")
    @patch("masu.external.kafka_msg_handler.KAFKA_LISTENER_WATCHDOG_DIAGNOSTICS_COUNTER")
    def test_emits_context_and_thread_stacks(self, diagnostics_counter, capture_message):
        """A slow message records the facts needed to investigate a listener hang."""
        context = {
            "request_id": "request-1",
            "topic": "platform.upload.announce",
            "partition": 2,
            "offset": 42,
            "schema": "org1234567",
        }
        watchdog = msg_handler.KafkaMessageWatchdog(context, timeout_seconds=1)

        with self.assertLogs("masu.external.kafka_msg_handler", level="ERROR") as logs:
            watchdog._emit_diagnostic(1.25)

        self.assertIn("Kafka listener message processing exceeded watchdog threshold", logs.output[0])
        self.assertIn("thread_stacks", logs.output[0])
        diagnostics_counter.inc.assert_called_once_with()
        capture_message.assert_called_once_with(
            "Kafka listener message processing exceeded watchdog threshold", level="error"
        )

    @patch("masu.external.kafka_msg_handler.KafkaMessageWatchdog")
    @patch("masu.external.kafka_msg_handler.process_messages")
    def test_observes_without_changing_commit(self, process_messages, watchdog):
        """The watchdog wraps processing only and leaves the normal commit intact."""
        message = Mock()
        message.topic.return_value = "platform.upload.announce"
        message.offset.return_value = 42
        message.partition.return_value = 2
        message.headers.return_value = (("service", b"hccm"),)
        message.value.return_value = json.dumps(
            {"request_id": "request-1", "account": "10001", "org_id": "1234567"}
        ).encode("utf-8")
        consumer = Mock()

        msg_handler.listen_for_messages(message, consumer)

        context, timeout_seconds = watchdog.call_args.args
        self.assertEqual(context["topic"], "platform.upload.announce")
        self.assertEqual(context["partition"], 2)
        self.assertEqual(context["offset"], 42)
        self.assertEqual(context["request_id"], "request-1")
        self.assertEqual(context["schema"], "org1234567")
        self.assertEqual(timeout_seconds, Config.KAFKA_LISTENER_WATCHDOG_TIMEOUT_SECONDS)
        process_messages.assert_called_once_with(message)
        consumer.commit.assert_called_once_with()
