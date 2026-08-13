#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test Celery utility functions."""
import os
import unittest
from unittest.mock import patch
from urllib.parse import unquote
from urllib.parse import urlparse

from celery.schedules import crontab
from django.conf import settings
from django.test import SimpleTestCase
from redis.exceptions import AuthenticationError

from api.iam.test.iam_test_case import IamTestCase
from koku import is_task_currently_running
from koku.celery import app as celery_app
from koku.celery import CURRENCY_RATES_BEAT_NAME
from koku.celery import register_daily_currency_rates_beat


class CeleryTest(IamTestCase):
    @patch("koku.celery.CELERY_INSPECT")
    def test_is_task_currently_running(self, mock_inspect):
        """Test the various conditions for our running task checker."""
        mock_inspect.active.return_value = {
            "celery@koku-worker-1": [
                {
                    "id": "26256b1d-b0d8-4822-ba70-73da82af9542",
                    "name": "masu.processor.tasks.update_summary_tables",
                    "args": ["org1234567", "AWS-local", "2878097c-7693-4a4a-9726-e75124457805", "2020-08-01", None],
                    "kwargs": {},
                    "type": "masu.processor.tasks.update_summary_tables",
                    "hostname": "celery@koku-worker-1",
                    "time_start": 1597940661.4609702,
                    "acknowledged": True,
                    "delivery_info": {"exchange": "", "routing_key": "celery", "priority": 0, "redelivered": False},
                    "worker_pid": 68,
                }
            ]
        }

        # No task ID
        self.assertTrue(
            is_task_currently_running("masu.processor.tasks.update_summary_tables", None, check_args=["org1234567"])
        )
        # Different task ID running the check than the listed currently running task
        self.assertTrue(
            is_task_currently_running(
                "masu.processor.tasks.update_summary_tables",
                "26256b1d-b0d8-4822-ba70-73da82af9543",
                check_args=["org1234567"],
            )
        )
        # No check args
        self.assertTrue(is_task_currently_running("masu.processor.tasks.update_summary_tables", None))

        # The task ID of the currently running task
        self.assertFalse(
            is_task_currently_running(
                "masu.processor.tasks.update_summary_tables",
                "26256b1d-b0d8-4822-ba70-73da82af9542",
                check_args=["org1234567"],
            )
        )

        # An incomplete task name
        self.assertFalse(is_task_currently_running("update_summary_tables", None, check_args=["org1234567"]))
        # A different check arg
        self.assertFalse(
            is_task_currently_running("masu.processor.tasks.update_summary_tables", None, check_args=["org2222222"])
        )
        # A different task
        self.assertFalse(is_task_currently_running("masu.processor.tasks.update_cost_model_costs", None))


class CurrencyRatesBeatScheduleTest(SimpleTestCase):
    """Tests for conditional registration of the daily currency rates beat."""

    def test_register_daily_currency_rates_beat_with_url(self):
        """Beat is registered when CURRENCY_URL is set."""
        beat_schedule = {}
        scheduled = register_daily_currency_rates_beat(
            beat_schedule, "https://exchange-rates.example/v6/latest/USD", schedule=crontab(hour=1, minute=0)
        )

        self.assertTrue(scheduled)
        self.assertIn(CURRENCY_RATES_BEAT_NAME, beat_schedule)
        self.assertEqual(
            beat_schedule[CURRENCY_RATES_BEAT_NAME]["task"],
            "masu.celery.tasks.get_daily_currency_rates",
        )

    def test_register_daily_currency_rates_beat_without_url(self):
        """Beat is not registered when CURRENCY_URL is empty, None, or whitespace."""
        for invalid_url in ("", "   ", None):
            with self.subTest(invalid_url=invalid_url):
                beat_schedule = {}
                scheduled = register_daily_currency_rates_beat(beat_schedule, invalid_url)

                self.assertFalse(scheduled)
                self.assertNotIn(CURRENCY_RATES_BEAT_NAME, beat_schedule)


class CeleryBrokerSecurityTest(SimpleTestCase):
    """COST-7860: Celery broker security settings and optional auth check."""

    def test_serializers_are_json_only(self):
        """Workers must accept JSON only — pickle is never allowed."""
        self.assertEqual(settings.CELERY_TASK_SERIALIZER, "json")
        self.assertEqual(settings.CELERY_RESULT_SERIALIZER, "json")
        self.assertEqual(settings.CELERY_ACCEPT_CONTENT, ["json"])
        self.assertNotIn("pickle", settings.CELERY_ACCEPT_CONTENT)
        self.assertEqual(celery_app.conf.task_serializer, "json")
        self.assertEqual(list(celery_app.conf.accept_content), ["json"])
        self.assertEqual(celery_app.conf.result_serializer, "json")

    def test_worker_does_not_hijack_root_logger(self):
        """Disable Celery's root-logger hijack for predictable process logging."""
        self.assertIs(settings.CELERY_WORKER_HIJACK_ROOT_LOGGER, False)
        self.assertIs(celery_app.conf.worker_hijack_root_logger, False)

    def test_task_always_eager_not_enabled_in_settings(self):
        """CELERY_TASK_ALWAYS_EAGER must not be enabled outside of tests."""
        self.assertFalse(getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False))
        self.assertFalse(celery_app.conf.task_always_eager)

    def test_broker_and_results_use_redis_url(self):
        """Broker and result backend share REDIS_URL (cache + Celery)."""
        self.assertEqual(settings.CELERY_BROKER_URL, settings.REDIS_URL)
        self.assertEqual(settings.CELERY_RESULTS_URL, settings.REDIS_URL)
        self.assertEqual(celery_app.conf.broker_url, settings.CELERY_BROKER_URL)
        self.assertEqual(
            celery_app.conf.result_backend,
            settings.CELERY_RESULTS_URL or getattr(settings, "CELERY_RESULT_BACKEND", None),
        )

    @unittest.skipUnless(
        os.environ.get("COST_7860_AUTH_BROKER_URL"),
        "Set COST_7860_AUTH_BROKER_URL=redis://:password@host:6379/1 to run broker auth pentest",
    )
    def test_unauthenticated_broker_connection_rejected(self):
        """Manual/CI pentest: connecting without the password must fail when Valkey requires auth.

        Example:
            docker run -d --name valkey-auth -p 6380:6379 valkey/valkey:8 \\
              valkey-server --requirepass pentest-secret
            COST_7860_AUTH_BROKER_URL=redis://:pentest-secret@127.0.0.1:6380/1 \\
              pipenv run python manage.py test koku.test.test_celery.CeleryBrokerSecurityTest
        """
        import redis

        auth_url = os.environ["COST_7860_AUTH_BROKER_URL"]
        parsed = urlparse(auth_url)
        password = unquote(parsed.password) if parsed.password else None
        self.assertTrue(password, "COST_7860_AUTH_BROKER_URL must include a password")

        authed = redis.Redis.from_url(auth_url, socket_connect_timeout=2, socket_timeout=2)
        self.assertEqual(authed.ping(), True)

        # Same host/port/db/query without credentials — must be rejected by requirepass.
        host = parsed.hostname
        port = parsed.port or 6379
        if host and ":" in host and not host.startswith("["):
            netloc = f"[{host}]:{port}"
        else:
            netloc = f"{host}:{port}"
        open_url = parsed._replace(netloc=netloc).geturl()
        unauth = redis.Redis.from_url(open_url, socket_connect_timeout=2, socket_timeout=2)
        with self.assertRaises(AuthenticationError):
            unauth.ping()
