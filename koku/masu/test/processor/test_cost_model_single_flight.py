#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for single-flight cost model updates per provider and month (COST-8575)."""
from contextlib import contextmanager
from datetime import date
from datetime import timedelta
from unittest.mock import patch

from masu.processor.tasks import defer_busy_cost_model_update
from masu.processor.tasks import delayed_update_cost_model_costs
from masu.processor.tasks import update_cost_model_costs
from masu.processor.tasks import UPDATE_COST_MODEL_COSTS_TASK
from masu.test import MasuTestCase
from reporting_common.models import DelayedCeleryTasks


def _locks(acquired):
    calls = []

    @contextmanager
    def fake(provider_uuid, months):
        calls.append((provider_uuid, months))
        yield acquired

    return fake, calls


@patch("masu.processor.tasks.CostModelCostUpdater")
class CostModelSingleFlightTaskTest(MasuTestCase):
    """update_cost_model_costs under the single-flight flag."""

    def setUp(self):
        super().setUp()
        self.worker_cache = patch("masu.processor.tasks.WorkerCache").start()
        self.worker_cache.return_value.single_task_is_running.return_value = False
        self.addCleanup(patch.stopall)

    def _rows(self):
        return DelayedCeleryTasks.objects.filter(
            task_name=UPDATE_COST_MODEL_COSTS_TASK, provider_uuid=self.ocp_provider_uuid
        )

    @patch("masu.processor.tasks.is_cost_model_single_flight_enabled", return_value=False)
    def test_flag_off_runs_without_the_lock(self, _flag, mock_updater):
        """Flag off: no provider-month lock, the update runs as before."""
        fake, calls = _locks(True)
        with patch("masu.processor.tasks.provider_month_locks", fake):
            update_cost_model_costs(self.schema, self.ocp_provider_uuid, "2026-06-01", "2026-06-10")
        self.assertEqual(calls, [])
        mock_updater.return_value.update_cost_model_costs.assert_called_once_with("2026-06-01", "2026-06-10")

    @patch("masu.processor.tasks.is_cost_model_single_flight_enabled", return_value=True)
    def test_flag_on_runs_under_the_lock_of_every_month(self, _flag, mock_updater):
        """Flag on: the update runs while holding the lock of each billing month of its range."""
        fake, calls = _locks(True)
        with patch("masu.processor.tasks.provider_month_locks", fake):
            update_cost_model_costs(self.schema, self.ocp_provider_uuid, "2026-06-20", "2026-07-03")
        self.assertEqual(calls, [(self.ocp_provider_uuid, [date(2026, 6, 1), date(2026, 7, 1)])])
        mock_updater.return_value.update_cost_model_costs.assert_called_once_with("2026-06-20", "2026-07-03")
        self.assertFalse(self._rows().exists())

    @patch("masu.processor.tasks.is_cost_model_single_flight_enabled", return_value=True)
    def test_busy_lock_defers_instead_of_writing(self, _flag, mock_updater):
        """Flag on, lock busy: nothing is written; the window goes to the delayed tasks and the worker is free."""
        fake, _ = _locks(False)
        with patch("masu.processor.tasks.provider_month_locks", fake):
            update_cost_model_costs(
                self.schema, self.ocp_provider_uuid, "2026-06-05", "2026-06-10", queue_name="cost_model"
            )
        mock_updater.return_value.update_cost_model_costs.assert_not_called()
        self.worker_cache.return_value.release_single_task.assert_called_once()
        row = self._rows().get()
        self.assertEqual(row.task_args, [self.schema, str(self.ocp_provider_uuid)])
        self.assertEqual(row.task_kwargs["start_date"], "2026-06-05")
        self.assertEqual(row.task_kwargs["end_date"], "2026-06-10")
        self.assertEqual(row.queue_name, "cost_model")
        self.assertEqual(row.metadata, {"billing_month": "2026-06-01", "keep_earlier_deadline": True})

    @patch("masu.processor.tasks.is_cost_model_single_flight_enabled", return_value=True)
    def test_synchronous_runs_without_the_lock(self, _flag, mock_updater):
        """Synchronous calls keep today's behaviour: deferring would leave the caller without costs."""
        fake, calls = _locks(False)
        with patch("masu.processor.tasks.provider_month_locks", fake):
            update_cost_model_costs(self.schema, self.ocp_provider_uuid, "2026-06-01", "2026-06-10", synchronous=True)
        self.assertEqual(calls, [])
        mock_updater.return_value.update_cost_model_costs.assert_called_once()


class DeferBusyCostModelUpdateTest(MasuTestCase):
    """defer_busy_cost_model_update coalesces per provider month and never postpones."""

    def _rows(self):
        return DelayedCeleryTasks.objects.filter(
            task_name=UPDATE_COST_MODEL_COSTS_TASK, provider_uuid=self.ocp_provider_uuid
        )

    def test_one_row_per_month_with_the_widest_range(self):
        """Waiting runs of one provider month become one row covering all of their windows."""
        defer_busy_cost_model_update(self.schema, self.ocp_provider_uuid, "2026-06-20", "2026-07-02", "q")
        defer_busy_cost_model_update(self.schema, self.ocp_provider_uuid, "2026-06-03", "2026-06-05", "q")
        june = self._rows().get(metadata__billing_month="2026-06-01")
        july = self._rows().get(metadata__billing_month="2026-07-01")
        self.assertEqual((june.task_kwargs["start_date"], june.task_kwargs["end_date"]), ("2026-06-03", "2026-06-30"))
        self.assertEqual((july.task_kwargs["start_date"], july.task_kwargs["end_date"]), ("2026-07-01", "2026-07-02"))

    def test_deferring_again_does_not_postpone_the_run(self):
        """A pending row's deadline stays put when more runs are deferred into it."""
        defer_busy_cost_model_update(self.schema, self.ocp_provider_uuid, "2026-06-01", "2026-06-02", "q")
        deadline = self._rows().get().timeout_timestamp
        # Defer again 10 minutes later, before the beat fired the row: a plain reset would move the deadline there.
        with patch("reporting_common.models.timezone.now", return_value=deadline + timedelta(minutes=10)):
            defer_busy_cost_model_update(self.schema, self.ocp_provider_uuid, "2026-06-03", "2026-06-04", "q")
        self.assertEqual(self._rows().get().timeout_timestamp, deadline)

    @patch("masu.processor.tasks.is_celery_task_delay_disabled", return_value=True)
    def test_row_is_kept_when_task_delays_are_disabled(self, _delay_disabled):
        """Unlike delayed_update_cost_model_costs, the row is not fired at once: it would meet the busy lock."""
        defer_busy_cost_model_update(self.schema, self.ocp_provider_uuid, "2026-06-01", "2026-06-02", "q")
        self.assertTrue(self._rows().exists())

    @patch("masu.processor.tasks.is_celery_task_delay_disabled", return_value=False)
    def test_cost_model_edit_does_not_postpone_a_busy_retry(self, _delay_disabled):
        """A cost model edit for the same provider month keeps a pending busy retry's deadline.

        Both use one row per provider and billing month; the edit's ordinary debounce
        (DELAYED_TASK_TIME) must not move the busy retry's deadline later.
        """
        defer_busy_cost_model_update(self.schema, self.ocp_provider_uuid, "2026-06-01", "2026-06-02", "q")
        deadline = self._rows().get().timeout_timestamp

        delayed_update_cost_model_costs(self.schema, self.ocp_provider_uuid, "2026-06-01", "2026-06-30", "q")

        row = self._rows().get()
        self.assertEqual(row.timeout_timestamp, deadline)
        self.assertEqual((row.task_kwargs["start_date"], row.task_kwargs["end_date"]), ("2026-06-01", "2026-06-30"))
