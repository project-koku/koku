#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the provider-month cost model run lock."""
import uuid
from datetime import date
from datetime import timedelta
from unittest.mock import patch

from django.db import connections
from django.test import TestCase

from api.utils import DateHelper
from masu.processor.cost_model_run_lock import billing_months
from masu.processor.cost_model_run_lock import cost_model_run_months
from masu.processor.cost_model_run_lock import LOCK_NAMESPACE
from masu.processor.cost_model_run_lock import provider_month_locks

JUNE = date(2026, 6, 1)
JULY = date(2026, 7, 1)


class ProviderMonthLocksTest(TestCase):
    """provider_month_locks against a second database session."""

    def setUp(self):
        self.provider_uuid = str(uuid.uuid4())
        self.other = connections.create_connection("default")
        self.addCleanup(self.other.close)

    def _other_try(self, month):
        """Try the lock from the other session; release it again when taken."""
        key = f"{self.provider_uuid}:{month.isoformat()}"
        with self.other.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(hashtext(%s), hashtext(%s))", [LOCK_NAMESPACE, key])
            taken = cursor.fetchone()[0]
            if taken:
                cursor.execute("SELECT pg_advisory_unlock(hashtext(%s), hashtext(%s))", [LOCK_NAMESPACE, key])
        return taken

    def _other_hold(self, month):
        key = f"{self.provider_uuid}:{month.isoformat()}"
        with self.other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(hashtext(%s), hashtext(%s))", [LOCK_NAMESPACE, key])

    def test_billing_months(self):
        """Every billing month of the range, first days, in order."""
        self.assertEqual(billing_months(date(2026, 6, 15), date(2026, 6, 20)), [JUNE])
        self.assertEqual(billing_months(date(2026, 6, 15), date(2026, 8, 2)), [JUNE, JULY, date(2026, 8, 1)])

    def _run_months_on_day(self, day, start, end):
        class OnDay(DateHelper):
            @property
            def now_utc(self):
                return super().now_utc.replace(day=day)

        with patch("masu.processor.cost_model_run_lock.DateHelper", OnDay):
            return cost_model_run_months(start, end)

    def test_run_months_add_the_previous_month_on_the_2nd(self):
        """On the 2nd a run covering the current month also writes the previous month (GPU, COST-8586)."""
        dh = DateHelper()
        current, previous = dh.this_month_start.date(), dh.last_month_start.date()
        self.assertEqual(self._run_months_on_day(2, current, current + timedelta(days=1)), [previous, current])

    def test_run_months_are_the_range_on_other_days_and_for_past_months(self):
        """Any other day, or a range without the current month, locks only the range's own months."""
        dh = DateHelper()
        current, previous = dh.this_month_start.date(), dh.last_month_start.date()
        self.assertEqual(self._run_months_on_day(15, current, current + timedelta(days=1)), [current])
        self.assertEqual(self._run_months_on_day(2, previous, previous + timedelta(days=3)), [previous])
        self.assertEqual(self._run_months_on_day(2, previous, current), [previous, current])

    def test_holds_the_lock_and_releases_it(self):
        """Another session cannot take a held month; it can once the context exits."""
        with provider_month_locks(self.provider_uuid, [JUNE], wait_seconds=0) as acquired:
            self.assertTrue(acquired)
            self.assertFalse(self._other_try(JUNE))
            self.assertTrue(self._other_try(JULY), "a different month of the provider is not locked")
        self.assertTrue(self._other_try(JUNE))

    def test_busy_month_yields_false_after_the_wait(self):
        """A month held elsewhere stays busy: the context yields False once the wait runs out."""
        self._other_hold(JUNE)
        with provider_month_locks(self.provider_uuid, [JUNE], wait_seconds=0.2, poll_seconds=0.05) as acquired:
            self.assertFalse(acquired)

    def test_busy_month_releases_the_months_taken_before_it(self):
        """When a later month is busy, the earlier months taken are released again."""
        self._other_hold(JULY)
        with provider_month_locks(self.provider_uuid, [JULY, JUNE], wait_seconds=0.2, poll_seconds=0.05) as acquired:
            self.assertFalse(acquired)
            self.assertTrue(self._other_try(JUNE), "June must not stay locked while the run gives up")

    def test_releases_the_lock_when_the_body_raises(self):
        """An error inside the context still releases the locks."""
        with self.assertRaises(RuntimeError):
            with provider_month_locks(self.provider_uuid, [JUNE], wait_seconds=0):
                raise RuntimeError("writer failed")
        self.assertTrue(self._other_try(JUNE))
