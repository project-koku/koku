#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for single-flight OCP-on-cloud summaries per source pair and month (COST-8410)."""
from contextlib import contextmanager
from datetime import date
from datetime import timedelta
from unittest.mock import MagicMock
from unittest.mock import patch
from unittest.mock import PropertyMock

from api.provider.models import Provider
from api.utils import DateHelper
from masu.processor.ocp.ocp_cloud_parquet_summary_updater import OCPCloudParquetReportSummaryUpdater
from masu.processor.report_summary_updater import ReportSummaryUpdaterCloudError
from masu.processor.tasks import apply_openshift_on_cloud_window_deletes
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
        self.window_deletes = patch("masu.processor.tasks.apply_openshift_on_cloud_window_deletes").start()
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
        self.window_deletes.assert_not_called()
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
        self.window_deletes.assert_called_once()
        self.assertEqual(
            self.window_deletes.call_args[0][1:], (self.ocpaws_provider_uuid, date(2026, 6, 20), date(2026, 7, 3))
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
        self.window_deletes.assert_not_called()
        mock_update.assert_called_once()

    @patch("masu.processor.tasks.is_ocp_on_cloud_single_flight_enabled", return_value=True)
    def test_window_deletes_run_inside_the_lock(self, _flag, mock_update, mock_validate, mock_cost_model):
        """The run's own window clears happen while the run lock is held."""
        events = []

        @contextmanager
        def recording_lock(openshift_provider_uuid, infrastructure_provider_uuid, months):
            events.append("enter")
            yield True
            events.append("exit")

        self.window_deletes.side_effect = lambda *args: events.append("deletes")
        with patch("masu.processor.tasks.ocp_on_cloud_month_locks", recording_lock):
            self._run()
        self.assertEqual(events, ["enter", "deletes", "exit"])


class ApplyOpenshiftOnCloudWindowDeletesTest(MasuTestCase):
    """apply_openshift_on_cloud_window_deletes clears the rebuilt cluster's window."""

    def test_clears_through_the_cluster_scoped_window_delete(self):
        updater = MagicMock()
        apply_openshift_on_cloud_window_deletes(updater, "ocp-uuid", date(2026, 6, 1), date(2026, 6, 30))
        updater._ocp_cloud_updater.delete_cluster_scoped_window_data.assert_called_once_with(
            "ocp-uuid", date(2026, 6, 1), date(2026, 6, 30)
        )

    def test_failures_follow_the_task_retry_path(self):
        updater = MagicMock()
        updater._ocp_cloud_updater.delete_cluster_scoped_window_data.side_effect = RuntimeError("delete failed")
        with self.assertRaises(ReportSummaryUpdaterCloudError) as raised:
            apply_openshift_on_cloud_window_deletes(updater, "ocp-uuid", date(2026, 6, 1), date(2026, 6, 30))
        self.assertIsInstance(raised.exception.__cause__, RuntimeError)


class DeleteClusterScopedWindowDataTest(MasuTestCase):
    """delete_cluster_scoped_window_data derives the cluster's bill and report period."""

    def setUp(self):
        super().setUp()
        self.updater = OCPCloudParquetReportSummaryUpdater(self.schema, self.aws_provider, None)

    def _run(self, report_period, bills):
        scoped_delete = MagicMock()
        with (
            patch("masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor") as ocp_acc_cls,
            patch.object(OCPCloudParquetReportSummaryUpdater, "db_accessor", new_callable=PropertyMock) as db_acc,
            patch.object(self.updater, "_delete_cluster_scoped_ocp_on_cloud_pg_data", scoped_delete),
            patch(
                "masu.processor.ocp.ocp_cloud_parquet_summary_updater.get_cluster_id_from_provider",
                return_value="cluster-a",
            ),
        ):
            ocp_acc = ocp_acc_cls.return_value.__enter__.return_value
            ocp_acc.report_periods_for_provider_uuid.return_value = report_period
            infra_acc = db_acc.return_value.return_value.__enter__.return_value
            infra_acc.bills_for_provider_uuid.return_value = bills
            self.updater.delete_cluster_scoped_window_data(
                self.ocpaws_provider_uuid, date(2026, 6, 1), date(2026, 6, 30)
            )
        return scoped_delete, ocp_acc, infra_acc

    def test_deletes_with_the_cluster_bill_and_report_period(self):
        bills = MagicMock()
        bills.first.return_value = MagicMock(id=42)
        scoped_delete, ocp_acc, infra_acc = self._run(MagicMock(id=17), bills)
        ocp_acc.report_periods_for_provider_uuid.assert_called_once_with(self.ocpaws_provider_uuid, date(2026, 6, 1))
        infra_acc.bills_for_provider_uuid.assert_called_once_with(
            self.aws_provider.uuid, start_date=DateHelper().month_start(date(2026, 6, 1))
        )
        scoped_delete.assert_called_once_with(infra_acc, date(2026, 6, 1), date(2026, 6, 30), 42, 17, "cluster-a")

    def test_skips_the_clear_when_the_cluster_has_no_bill_or_period(self):
        scoped_delete, _, _ = self._run(None, [])
        scoped_delete.assert_not_called()


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
