#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test Celery utility functions."""
from unittest.mock import patch

from celery.schedules import crontab
from django.test import SimpleTestCase

from api.iam.test.iam_test_case import IamTestCase
from koku import is_task_currently_running
from koku.celery import CHECK_REPORT_UPDATES_BEAT_NAME
from koku.celery import CURRENCY_RATES_BEAT_NAME
from koku.celery import register_daily_currency_rates_beat
from koku.celery import register_report_check_beat
from koku.celery import register_saas_only_beats
from koku.celery import SAAS_ONLY_BEAT_NAMES


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
        """Beat is registered when CURRENCY_URL is set and not on-prem."""
        beat_schedule = {}
        scheduled = register_daily_currency_rates_beat(
            beat_schedule,
            "https://exchange-rates.example/v6/latest/USD",
            schedule=crontab(hour=1, minute=0),
            onprem=False,
        )

        self.assertTrue(scheduled)
        self.assertIn(CURRENCY_RATES_BEAT_NAME, beat_schedule)
        self.assertEqual(
            beat_schedule[CURRENCY_RATES_BEAT_NAME]["task"],
            "masu.celery.tasks.get_daily_currency_rates",
        )

    def test_register_daily_currency_rates_beat_with_url_when_not_onprem(self):
        """SaaS still registers the currency beat when a URL is configured."""
        beat_schedule = {}
        scheduled = register_daily_currency_rates_beat(
            beat_schedule,
            "https://exchange-rates.example/v6/latest/USD",
            onprem=False,
        )

        self.assertTrue(scheduled)
        self.assertIn(CURRENCY_RATES_BEAT_NAME, beat_schedule)
        self.assertEqual(
            beat_schedule[CURRENCY_RATES_BEAT_NAME]["task"],
            "masu.celery.tasks.get_daily_currency_rates",
        )

    def test_register_daily_currency_rates_beat_skipped_when_onprem(self):
        """Beat is not registered on-prem even when CURRENCY_URL is set."""
        beat_schedule = {}
        scheduled = register_daily_currency_rates_beat(
            beat_schedule,
            "https://exchange-rates.example/v6/latest/USD",
            onprem=True,
        )

        self.assertFalse(scheduled)
        self.assertNotIn(CURRENCY_RATES_BEAT_NAME, beat_schedule)

    def test_register_daily_currency_rates_beat_without_url(self):
        """Beat is not registered when CURRENCY_URL is empty, None, or whitespace."""
        for invalid_url in ("", "   ", None):
            with self.subTest(invalid_url=invalid_url):
                beat_schedule = {}
                scheduled = register_daily_currency_rates_beat(beat_schedule, invalid_url)

                self.assertFalse(scheduled)
                self.assertNotIn(CURRENCY_RATES_BEAT_NAME, beat_schedule)


class SaasOnlyBeatScheduleTest(SimpleTestCase):
    """Tests for SaaS-only Celery beat registration gated by ONPREM."""

    EXPECTED_SAAS_ONLY_TASKS = {
        "finalize_hcs_reports": "hcs.tasks.collect_hcs_report_finalization",
        "scrape_azure_storage_capacities": "masu.celery.tasks.scrape_azure_storage_capacities",
        "crawl_account_hierarchy": "masu.celery.tasks.crawl_account_hierarchy",
        "source_status_beat": "sources.tasks.source_status_beat",
        "delete_source_beat": "sources.tasks.delete_source_beat",
    }

    def test_saas_only_beats_not_registered_when_onprem(self):
        """SaaS-only beats are omitted when onprem=True."""
        beat_schedule = {}
        scheduled = register_saas_only_beats(beat_schedule, onprem=True)

        self.assertFalse(scheduled)
        for beat_name in self.EXPECTED_SAAS_ONLY_TASKS:
            with self.subTest(beat_name=beat_name):
                self.assertNotIn(beat_name, beat_schedule)
        for beat_name in SAAS_ONLY_BEAT_NAMES:
            with self.subTest(constant_beat_name=beat_name):
                self.assertNotIn(beat_name, beat_schedule)

    def test_saas_only_beats_registered_when_not_onprem(self):
        """SaaS-only beats are registered with current task wiring when onprem=False."""
        beat_schedule = {}
        scheduled = register_saas_only_beats(beat_schedule, onprem=False)

        self.assertTrue(scheduled)
        for beat_name, task_name in self.EXPECTED_SAAS_ONLY_TASKS.items():
            with self.subTest(beat_name=beat_name):
                self.assertIn(beat_name, beat_schedule)
                self.assertEqual(beat_schedule[beat_name]["task"], task_name)


class ReportCheckBeatScheduleTest(SimpleTestCase):
    """Tests for check-report-updates-batched beat registration."""

    def test_report_check_beat_not_registered_when_onprem_even_if_schedule_enabled(self):
        """On-prem never registers report-check beat even if SCHEDULE_REPORT_CHECKS is true."""
        beat_schedule = {}
        scheduled = register_report_check_beat(
            beat_schedule,
            onprem=True,
            schedule_report_checks=True,
            schedule=crontab(minute=0),
        )

        self.assertFalse(scheduled)
        self.assertNotIn(CHECK_REPORT_UPDATES_BEAT_NAME, beat_schedule)

    def test_report_check_beat_registered_when_not_onprem_and_schedule_enabled(self):
        """SaaS registers report-check beat when SCHEDULE_REPORT_CHECKS is enabled."""
        beat_schedule = {}
        scheduled = register_report_check_beat(
            beat_schedule,
            onprem=False,
            schedule_report_checks=True,
            schedule=crontab(minute=0),
        )

        self.assertTrue(scheduled)
        self.assertIn(CHECK_REPORT_UPDATES_BEAT_NAME, beat_schedule)
        self.assertEqual(
            beat_schedule[CHECK_REPORT_UPDATES_BEAT_NAME]["task"],
            "masu.celery.tasks.check_report_updates",
        )

    def test_report_check_beat_not_registered_when_schedule_disabled(self):
        """Report-check beat stays unregistered when SCHEDULE_REPORT_CHECKS is false."""
        beat_schedule = {}
        scheduled = register_report_check_beat(
            beat_schedule,
            onprem=False,
            schedule_report_checks=False,
            schedule=crontab(minute=0),
        )

        self.assertFalse(scheduled)
        self.assertNotIn(CHECK_REPORT_UPDATES_BEAT_NAME, beat_schedule)
