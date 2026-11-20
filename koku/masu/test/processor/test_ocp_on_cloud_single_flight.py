#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for single-flight OCP-on-cloud summaries per source pair and month (COST-8410)."""
from contextlib import contextmanager
from datetime import date
from datetime import timedelta
from unittest.mock import patch

from api.provider.models import Provider
from masu.processor.tasks import defer_busy_openshift_on_cloud
from masu.processor.tasks import update_openshift_on_cloud
from masu.processor.tasks import UPDATE_OPENSHIFT_ON_CLOUD_TASK
from masu.test import MasuTestCase
from reporting_common.models import DelayedCeleryTasks


def _locks(acquired):
    calls = []

    @contextmanager
    def fake(openshift_provider_uuid, infrastructure_provider_uuid, months):
        calls.append((openshift_provider_uuid, infrastructure_provider_uuid, months))
        yield acquired

    return fake, calls


@patch("masu.processor.tasks.update_cost_model_costs.s")
@patch("masu.processor.tasks.validate_daily_data.s")
@patch("masu.processor.tasks.ReportSummaryUpdater.update_openshift_on_cloud_summary_tables")
class OcpOnCloudSingleFlightTaskTest(MasuTestCase):
    """update_openshift_on_cloud under the single-flight flag."""

    def setUp(self):
        super().setUp()
        self.worker_cache = patch("masu.processor.tasks.WorkerCache").start()
        self.worker_cache.return_value.single_task_is_running.return_value = False
        self.addCleanup(patch.stopall)

    def _rows(self):
        return DelayedCeleryTasks.objects.filter(
            task_name=UPDATE_OPENSHIFT_ON_CLOUD_TASK, provider_uuid=self.ocpaws_provider_uuid
        )

    def _run(self, start_date=date(2026, 6, 20), end_date=date(2026, 6, 30), **kwargs):
        update_openshift_on_cloud(
            self.schema,
            self.ocpaws_provider_uuid,
            self.aws_provider_uuid,
            Provider.PROVIDER_AWS,
            start_date,
            end_date,
            **kwargs,
        )

    @patch("masu.processor.tasks.is_ocp_on_cloud_single_flight_enabled", return_value=False)
    def test_flag_off_runs_without_the_lock(self, _flag, mock_update, mock_validate, mock_cost_model):
        """Flag off: no source-pair month lock, the summary runs as before."""
        fake, calls = _locks(True)
        with patch("masu.processor.tasks.ocp_on_cloud_month_locks", fake):
            self._run()
        self.assertEqual(calls, [])
        mock_update.assert_called_once_with(
            date(2026, 6, 20), date(2026, 6, 30), self.ocpaws_provider_uuid, self.aws_provider_uuid, "AWS", None
        )

    @patch("masu.processor.tasks.is_ocp_on_cloud_single_flight_enabled", return_value=True)
    def test_flag_on_runs_under_the_lock_of_every_month(self, _flag, mock_update, mock_validate, mock_cost_model):
        """Flag on: the summary runs while holding the lock of each billing month of its range."""
        fake, calls = _locks(True)
        with patch("masu.processor.tasks.ocp_on_cloud_month_locks", fake):
            self._run(start_date=date(2026, 6, 20), end_date=date(2026, 7, 3))
        self.assertEqual(
            calls, [(self.ocpaws_provider_uuid, self.aws_provider_uuid, [date(2026, 6, 1), date(2026, 7, 1)])]
        )
        mock_update.assert_called_once_with(
            date(2026, 6, 20), date(2026, 7, 3), self.ocpaws_provider_uuid, self.aws_provider_uuid, "AWS", None
        )
        self.assertFalse(self._rows().exists())

    @patch("masu.processor.tasks.is_ocp_on_cloud_single_flight_enabled", return_value=True)
    def test_busy_lock_defers_instead_of_writing(self, _flag, mock_update, mock_validate, mock_cost_model):
        """Flag on, lock busy: nothing is written; the window goes to the delayed tasks and the worker is free."""
        fake, _ = _locks(False)
        with patch("masu.processor.tasks.ocp_on_cloud_month_locks", fake):
            self._run(start_date=date(2026, 6, 5), end_date=date(2026, 6, 10), queue_name="customer.q")
        mock_update.assert_not_called()
        mock_cost_model.assert_not_called()
        mock_validate.assert_not_called()
        self.worker_cache.return_value.release_single_task.assert_called_once()
        row = self._rows().get()
        self.assertEqual(row.task_args, [self.schema, str(self.ocpaws_provider_uuid), str(self.aws_provider_uuid)])
        self.assertEqual(row.task_kwargs["start_date"], "2026-06-05")
        self.assertEqual(row.task_kwargs["end_date"], "2026-06-10")
        self.assertEqual(row.task_kwargs["infrastructure_provider_type"], "AWS")
        self.assertEqual(row.queue_name, "customer.q")
        self.assertEqual(
            row.metadata,
            {"billing_month": "2026-06-01", "keep_earlier_deadline": True, "work_key": str(self.aws_provider_uuid)},
        )

    @patch("masu.processor.tasks.is_ocp_on_cloud_single_flight_enabled", return_value=True)
    @patch("masu.processor.tasks.update_openshift_on_cloud.s")
    def test_busy_gate_defers_instead_of_requeuing(
        self, mock_requeue, _flag, mock_update, mock_validate, mock_cost_model
    ):
        """Flag on, WorkerCache gate busy: the copy becomes one delayed successor, not a requeued message."""
        self.worker_cache.return_value.single_task_is_running.return_value = True
        self._run(manifest_id="14315308")
        mock_requeue.assert_not_called()
        mock_update.assert_not_called()
        self.worker_cache.return_value.lock_single_task.assert_not_called()
        row = self._rows().get()
        self.assertEqual(row.task_kwargs["manifest_id"], "14315308")

    @patch("masu.processor.tasks.is_ocp_on_cloud_single_flight_enabled", return_value=False)
    @patch("masu.processor.tasks.update_openshift_on_cloud.s")
    def test_flag_off_keeps_the_immediate_requeue(
        self, mock_requeue, _flag, mock_update, mock_validate, mock_cost_model
    ):
        """Flag off, gate busy: today's behaviour, the copy republishes itself immediately."""
        self.worker_cache.return_value.single_task_is_running.return_value = True
        self._run()
        mock_requeue.assert_called()
        mock_update.assert_not_called()
        self.assertFalse(self._rows().exists())

    @patch("masu.processor.tasks.is_ocp_on_cloud_single_flight_enabled", return_value=True)
    def test_synchronous_runs_without_the_lock(self, _flag, mock_update, mock_validate, mock_cost_model):
        """Synchronous calls keep today's behaviour: deferring would leave the caller without a summary."""
        fake, calls = _locks(False)
        with patch("masu.processor.tasks.ocp_on_cloud_month_locks", fake):
            self._run(synchronous=True)
        self.assertEqual(calls, [])
        mock_update.assert_called_once()


class DeferBusyOpenshiftOnCloudTest(MasuTestCase):
    """defer_busy_openshift_on_cloud coalesces per source pair month and never postpones."""

    def _rows(self):
        return DelayedCeleryTasks.objects.filter(
            task_name=UPDATE_OPENSHIFT_ON_CLOUD_TASK, provider_uuid=self.ocpaws_provider_uuid
        )

    def _defer(self, start_date, end_date, infrastructure_provider_uuid=None, **kwargs):
        defer_busy_openshift_on_cloud(
            self.schema,
            self.ocpaws_provider_uuid,
            infrastructure_provider_uuid or self.aws_provider_uuid,
            Provider.PROVIDER_AWS,
            start_date,
            end_date,
            kwargs.pop("manifest_id", None),
            kwargs.pop("queue_name", "q"),
            **kwargs,
        )

    def test_one_row_per_month_with_the_widest_range(self):
        """Waiting copies of one source pair month become one row covering all of their windows."""
        self._defer("2026-06-20", "2026-07-02")
        self._defer("2026-06-03", "2026-06-05")
        june = self._rows().get(metadata__billing_month="2026-06-01")
        july = self._rows().get(metadata__billing_month="2026-07-01")
        self.assertEqual((june.task_kwargs["start_date"], june.task_kwargs["end_date"]), ("2026-06-03", "2026-06-30"))
        self.assertEqual((july.task_kwargs["start_date"], july.task_kwargs["end_date"]), ("2026-07-01", "2026-07-02"))

    def test_deferring_again_does_not_postpone_the_run(self):
        """A pending row's deadline stays put when more copies are deferred into it."""
        self._defer("2026-06-01", "2026-06-02")
        deadline = self._rows().get().timeout_timestamp
        # Defer again 10 minutes later, before the beat fired the row: a plain reset would move the deadline there.
        with patch("reporting_common.models.timezone.now", return_value=deadline + timedelta(minutes=10)):
            self._defer("2026-06-03", "2026-06-04")
        self.assertEqual(self._rows().get().timeout_timestamp, deadline)

    def test_work_key_separates_cloud_sources_of_one_openshift_source(self):
        """The same OpenShift source against two cloud sources keeps two successors, one per cloud source."""
        other_cloud = "4d0b6d80-7d2d-4dd1-9c1d-1d4b7e53a111"
        self._defer("2026-06-01", "2026-06-10")
        self._defer("2026-06-05", "2026-06-12", infrastructure_provider_uuid=other_cloud)
        rows = self._rows().filter(metadata__billing_month="2026-06-01")
        self.assertEqual(rows.count(), 2)
        first = rows.get(metadata__work_key=str(self.aws_provider_uuid))
        second = rows.get(metadata__work_key=other_cloud)
        self.assertEqual(first.task_args[2], str(self.aws_provider_uuid))
        self.assertEqual(second.task_args[2], other_cloud)

    def test_latest_manifest_wins_on_the_row(self):
        """A newer manifest deferred into a pending row replaces the older payload."""
        self._defer("2026-06-01", "2026-06-10", manifest_id="1")
        self._defer("2026-06-05", "2026-06-12", manifest_id="2")
        row = self._rows().get(metadata__billing_month="2026-06-01")
        self.assertEqual(row.task_kwargs["manifest_id"], "2")
        self.assertEqual((row.task_kwargs["start_date"], row.task_kwargs["end_date"]), ("2026-06-01", "2026-06-12"))

    @patch("masu.processor.tasks.is_celery_task_delay_disabled", return_value=True)
    def test_row_is_kept_when_task_delays_are_disabled(self, _delay_disabled):
        """The row is not fired at once: it would only meet the same busy lock."""
        self._defer("2026-06-01", "2026-06-02")
        self.assertTrue(self._rows().exists())
