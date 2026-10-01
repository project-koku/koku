#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test Reporting Common."""
from datetime import date
from unittest.mock import MagicMock
from unittest.mock import patch

from django.utils import timezone
from django_tenants.utils import schema_context

from api.models import Provider
from api.utils import DateHelper
from common.queues import PriorityQueue
from common.queues import SummaryQueue
from masu.processor.tasks import delayed_summarize_current_month
from masu.processor.tasks import delayed_update_cost_model_costs
from masu.processor.tasks import UPDATE_COST_MODEL_COSTS_TASK
from masu.processor.tasks import UPDATE_SUMMARY_TABLES_TASK
from masu.test import MasuTestCase
from reporting_common.models import CombinedChoices
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus
from reporting_common.models import DelayedCeleryTasks
from reporting_common.models import trigger_celery_task


class TestCostUsageReportStatus(MasuTestCase):
    def setUp(self):
        super().setUp()
        self.manifest = CostUsageReportManifest(
            **{
                "assembly_id": "1",
                "provider_id": self.aws_provider_uuid,
                "num_total_files": 1,
                "billing_period_start_datetime": timezone.now(),
            }
        )
        self.manifest.save()
        self.report_name = self.fake.name

    def test_set_started_datetime(self):
        """Test set_started_datetime sets the started_datetime."""
        stats = CostUsageReportStatus(
            report_name=self.report_name,
            manifest_id=self.manifest.id,
        )
        stats.save()
        self.assertIsNone(stats.started_datetime)
        stats.set_started_datetime()
        self.assertIsNotNone(stats.started_datetime)

        old_datetime = stats.started_datetime
        stats.set_started_datetime()
        self.assertNotEqual(stats.started_datetime, old_datetime)

    def test_clear_started_datetime(self):
        """Test clear_started_datetime deletes the started_datetime."""
        stats = CostUsageReportStatus(
            report_name=self.report_name,
            manifest_id=self.manifest.id,
            started_datetime=timezone.now(),
        )
        stats.save()
        self.assertIsNotNone(stats.started_datetime)
        stats.clear_started_datetime()
        self.assertIsNone(stats.started_datetime)

    def test_set_completed_datetime(self):
        """Test set_completed_datetime set the completed_datetime."""
        stats = CostUsageReportStatus(
            report_name=self.report_name,
            manifest_id=self.manifest.id,
            started_datetime=timezone.now(),
        )
        stats.save()
        self.assertIsNone(stats.completed_datetime)
        stats.set_completed_datetime()
        self.assertIsNotNone(stats.completed_datetime)

    def test_set_celery_task_id(self):
        """
        Test setting celery_task_id field to match the report task id.
        """
        task_id = "aabfdddb-4ed5-421e-a041-532b45daf532"
        stats = CostUsageReportStatus(
            report_name=self.report_name,
            manifest_id=self.manifest.id,
            started_datetime=timezone.now(),
        )
        stats.save()
        self.assertIsNotNone(stats.set_celery_task_id)
        stats.set_celery_task_id(task_id)
        self.assertEqual(stats.celery_task_id, task_id)

    def test_update_status(self):
        """
        Test updating the status of the current report.
        """
        stats = CostUsageReportStatus(
            report_name=self.report_name,
            manifest_id=self.manifest.id,
            started_datetime=timezone.now(),
        )
        stats.save()
        self.assertEqual(stats.status, CombinedChoices.DOWNLOADING)
        stats.update_status(CombinedChoices.DONE)
        self.assertEqual(stats.status, CombinedChoices.DONE)

    def test_set_failed_status(self):
        """
        Test setting the failed state of a processing report.
        """
        stats = CostUsageReportStatus(
            report_name=self.report_name,
            manifest_id=self.manifest.id,
            started_datetime=timezone.now(),
        )
        stats.save()
        self.assertIsNone(stats.failed_status)
        stats.update_status(CombinedChoices.FAILED)
        self.assertIsNotNone(stats.failed_status)
        self.assertEqual(stats.status, CombinedChoices.FAILED)

    @patch("masu.processor.tasks.is_celery_task_delay_disabled", return_value=False)
    @patch("masu.processor.tasks.get_customer_queue")
    def test_delayed_summarize_current_month(self, mock_get_customer_queue, _mock_delay_disabled):
        mock_get_customer_queue.return_value = SummaryQueue.DEFAULT
        test_matrix = {
            Provider.PROVIDER_AWS: self.aws_provider,
            Provider.PROVIDER_AZURE: self.azure_provider,
            Provider.PROVIDER_GCP: self.gcp_provider,
        }
        count = 0
        for test_provider_type, test_provider in test_matrix.items():
            with self.subTest(test_provider_type=test_provider_type, test_provider=test_provider):
                with schema_context(self.schema):
                    delayed_summarize_current_month(self.schema_name, [test_provider.uuid], test_provider_type)
                    count += 1
                    self.assertEqual(DelayedCeleryTasks.objects.all().count(), count)
                    db_entry = DelayedCeleryTasks.objects.get(provider_uuid=test_provider.uuid)
                    self.assertEqual(db_entry.task_name, UPDATE_SUMMARY_TABLES_TASK)
                    self.assertTrue(
                        db_entry.task_kwargs,
                        {
                            "provider_type": test_provider_type,
                            "provider_uuid": str(test_provider.uuid),
                            "start_date": str(DateHelper().this_month_start),
                        },
                    )

                    self.assertEqual(db_entry.task_args, [self.schema_name])
                    self.assertEqual(db_entry.queue_name, SummaryQueue.DEFAULT)

    @patch("masu.processor.tasks.is_celery_task_delay_disabled", return_value=False)
    @patch("masu.processor.tasks.get_customer_queue")
    def test_large_customer(self, mock_get_customer_queue, _mock_delay_disabled):
        mock_get_customer_queue.return_value = SummaryQueue.XL
        delayed_summarize_current_month(self.schema_name, [self.aws_provider.uuid], Provider.PROVIDER_AWS)
        with schema_context(self.schema):
            db_entry = DelayedCeleryTasks.objects.get(provider_uuid=self.aws_provider.uuid)
            self.assertEqual(db_entry.queue_name, SummaryQueue.XL)

    @patch("reporting_common.models.celery_app")
    @patch("masu.processor.tasks.is_celery_task_delay_disabled", return_value=True)
    @patch("masu.processor.tasks.get_customer_queue")
    def test_delayed_summarize_bypasses_when_flag_enabled(
        self, mock_get_customer_queue, _mock_delay_disabled, mock_celery_app
    ):
        """When disable-celery-task-delay is ON, the row is deleted and send_task fires."""
        mock_get_customer_queue.return_value = SummaryQueue.DEFAULT
        result = MagicMock()
        result.id = "mocked_result_id"
        mock_celery_app.send_task.return_value = result

        delayed_summarize_current_month(self.schema_name, [self.aws_provider.uuid], Provider.PROVIDER_AWS)

        with schema_context(self.schema):
            self.assertFalse(DelayedCeleryTasks.objects.filter(provider_uuid=self.aws_provider.uuid).exists())
        mock_celery_app.send_task.assert_called_once()

    @patch("reporting_common.models.celery_app")
    def test_trigger_celery_task(self, mock_celery_app):
        # Building Mocks
        result = MagicMock()
        result.id = "mocked_result_id"
        mock_celery_app.send_task.return_value = result
        # Building Test data
        expected_task_name = "test_task"
        expected_args = ["arg1", "arg2"]
        expected_task_kwargs = {"tracing_id": "123"}
        expected_queue = "test_queue"
        task_instance = DelayedCeleryTasks.create_or_reset_timeout(
            task_name=expected_task_name,
            task_args=expected_args,
            task_kwargs=expected_task_kwargs,
            provider_uuid=self.aws_provider_uuid,
            queue_name=expected_queue,
        )

        with self.assertLogs("reporting_common.models", level="INFO") as cm:
            trigger_celery_task(sender=None, instance=task_instance)

        log_message = "delay period ended starting task"
        self.assertTrue(any(log_message in log for log in cm.output))

        mock_celery_app.send_task.assert_called_once_with(
            task_instance.task_name,
            args=task_instance.task_args,
            kwargs=task_instance.task_kwargs,
            queue=task_instance.queue_name,
        )

    def test_create_or_reset_timeout_refreshes_payload(self):
        """Resetting a delayed task refreshes args/kwargs/queue and extends timeout."""
        provider_uuid = self.aws_provider_uuid
        first = DelayedCeleryTasks.create_or_reset_timeout(
            task_name="test_task",
            task_args=["old_arg"],
            task_kwargs={"tracing_id": "keep-me", "value": 1},
            provider_uuid=provider_uuid,
            queue_name="old_queue",
            timeout_seconds=60,
        )
        original_timeout = first.timeout_timestamp

        second = DelayedCeleryTasks.create_or_reset_timeout(
            task_name="test_task",
            task_args=["new_arg"],
            task_kwargs={"value": 2},
            provider_uuid=provider_uuid,
            queue_name="new_queue",
            timeout_seconds=120,
        )

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            DelayedCeleryTasks.objects.filter(task_name="test_task", provider_uuid=provider_uuid).count(), 1
        )
        second.refresh_from_db()
        self.assertEqual(second.task_args, ["new_arg"])
        self.assertEqual(second.task_kwargs, {"tracing_id": "keep-me", "value": 2})
        self.assertEqual(second.queue_name, "new_queue")
        self.assertGreater(second.timeout_timestamp, original_timeout)

    def test_create_or_reset_timeout_merge_date_range(self):
        """merge_date_range widens start/end against the locked existing row."""
        provider_uuid = self.aws_provider_uuid
        billing_month = date(2026, 7, 1)
        first = DelayedCeleryTasks.create_or_reset_timeout(
            task_name=UPDATE_COST_MODEL_COSTS_TASK,
            task_args=[self.schema_name, str(provider_uuid)],
            task_kwargs={
                "start_date": "2026-07-10",
                "end_date": "2026-07-15",
                "tracing_id": "keep-me",
            },
            provider_uuid=provider_uuid,
            queue_name=PriorityQueue.DEFAULT,
            billing_month=billing_month,
            merge_date_range=True,
        )
        second = DelayedCeleryTasks.create_or_reset_timeout(
            task_name=UPDATE_COST_MODEL_COSTS_TASK,
            task_args=[self.schema_name, str(provider_uuid)],
            task_kwargs={
                "start_date": "2026-07-01",
                "end_date": "2026-07-12",
                "queue_name": PriorityQueue.XL,
            },
            provider_uuid=provider_uuid,
            queue_name=PriorityQueue.XL,
            billing_month=billing_month,
            merge_date_range=True,
        )

        self.assertEqual(first.pk, second.pk)
        second.refresh_from_db()
        self.assertEqual(second.task_kwargs.get("start_date"), "2026-07-01")
        self.assertEqual(second.task_kwargs.get("end_date"), "2026-07-15")
        self.assertEqual(second.task_kwargs.get("tracing_id"), "keep-me")
        self.assertEqual(second.queue_name, PriorityQueue.XL)
        self.assertEqual(
            DelayedCeleryTasks.objects.filter(
                task_name=UPDATE_COST_MODEL_COSTS_TASK,
                provider_uuid=provider_uuid,
                metadata__billing_month="2026-07-01",
            ).count(),
            1,
        )

    @patch("masu.processor.tasks.is_celery_task_delay_disabled", return_value=False)
    def test_delayed_update_cost_model_costs_coalesces_max_range(self, _mock_delay_disabled):
        """Same-month edits coalesce to one row with the widest date range."""
        provider_uuid = self.aws_provider.uuid
        delayed_update_cost_model_costs(
            self.schema_name,
            provider_uuid,
            date(2026, 7, 7),
            date(2026, 7, 13),
            queue_name=PriorityQueue.DEFAULT,
            tracing_id="trace-1",
        )
        delayed_update_cost_model_costs(
            self.schema_name,
            provider_uuid,
            date(2026, 7, 9),
            date(2026, 7, 31),
            queue_name=PriorityQueue.XL,
            tracing_id="trace-2",
        )

        rows = DelayedCeleryTasks.objects.filter(task_name=UPDATE_COST_MODEL_COSTS_TASK, provider_uuid=provider_uuid)
        self.assertEqual(rows.count(), 1)
        row = rows.get()
        self.assertEqual(row.metadata.get("billing_month"), "2026-07-01")
        self.assertEqual(row.task_args, [self.schema_name, str(provider_uuid)])
        self.assertEqual(row.task_kwargs.get("start_date"), "2026-07-07")
        self.assertEqual(row.task_kwargs.get("end_date"), "2026-07-31")
        self.assertEqual(row.queue_name, PriorityQueue.XL)
        self.assertEqual(row.task_kwargs.get("tracing_id"), "trace-2")

    @patch("masu.processor.tasks.is_celery_task_delay_disabled", return_value=False)
    def test_delayed_update_cost_model_costs_splits_cross_month(self, _mock_delay_disabled):
        """Cross-month ranges create one delayed row per calendar month."""
        provider_uuid = self.aws_provider.uuid
        delayed_update_cost_model_costs(
            self.schema_name,
            provider_uuid,
            date(2026, 7, 27),
            date(2026, 8, 5),
            queue_name=PriorityQueue.DEFAULT,
        )

        rows = list(
            DelayedCeleryTasks.objects.filter(
                task_name=UPDATE_COST_MODEL_COSTS_TASK, provider_uuid=provider_uuid
            ).order_by("metadata__billing_month")
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].metadata.get("billing_month"), "2026-07-01")
        self.assertEqual(rows[0].task_args, [self.schema_name, str(provider_uuid)])
        self.assertEqual(rows[0].task_kwargs.get("start_date"), "2026-07-27")
        self.assertEqual(rows[0].task_kwargs.get("end_date"), "2026-07-31")
        self.assertEqual(rows[1].metadata.get("billing_month"), "2026-08-01")
        self.assertEqual(rows[1].task_kwargs.get("start_date"), "2026-08-01")
        self.assertEqual(rows[1].task_kwargs.get("end_date"), "2026-08-05")

    @patch("masu.processor.tasks.is_celery_task_delay_disabled", return_value=False)
    def test_delayed_update_cost_model_costs_invalid_date_range(self, _mock_delay_disabled):
        """Inverted start/end creates no delayed rows."""
        provider_uuid = self.aws_provider.uuid
        delayed_update_cost_model_costs(
            self.schema_name,
            provider_uuid,
            date(2026, 8, 21),
            date(2026, 8, 1),
            queue_name=PriorityQueue.DEFAULT,
            tracing_id="bad-range",
        )

        self.assertEqual(
            DelayedCeleryTasks.objects.filter(
                task_name=UPDATE_COST_MODEL_COSTS_TASK, provider_uuid=provider_uuid
            ).count(),
            0,
        )

    @patch("masu.processor.tasks.is_celery_task_delay_disabled", return_value=False)
    def test_delayed_update_cost_model_costs_independent_months(self, _mock_delay_disabled):
        """A new month slice does not change an existing prior-month delayed row."""
        provider_uuid = self.aws_provider.uuid
        delayed_update_cost_model_costs(
            self.schema_name,
            provider_uuid,
            date(2026, 7, 27),
            date(2026, 7, 31),
            queue_name=PriorityQueue.DEFAULT,
        )
        delayed_update_cost_model_costs(
            self.schema_name,
            provider_uuid,
            date(2026, 8, 1),
            date(2026, 8, 5),
            queue_name=PriorityQueue.DEFAULT,
        )

        july = DelayedCeleryTasks.objects.get(
            task_name=UPDATE_COST_MODEL_COSTS_TASK,
            provider_uuid=provider_uuid,
            metadata__billing_month="2026-07-01",
        )
        self.assertEqual(july.task_kwargs.get("start_date"), "2026-07-27")
        self.assertEqual(july.task_kwargs.get("end_date"), "2026-07-31")
        self.assertEqual(
            DelayedCeleryTasks.objects.filter(
                task_name=UPDATE_COST_MODEL_COSTS_TASK, provider_uuid=provider_uuid
            ).count(),
            2,
        )

    @patch("reporting_common.models.celery_app")
    @patch("masu.processor.tasks.is_celery_task_delay_disabled", return_value=True)
    def test_delayed_update_cost_model_costs_delay_bypass(self, _mock_delay_disabled, mock_celery_app):
        """When disable-celery-task-delay is ON, the row is deleted and send_task fires."""
        result = MagicMock()
        result.id = "qe_result_id"
        mock_celery_app.send_task.return_value = result

        provider_uuid = self.aws_provider.uuid
        delayed_update_cost_model_costs(
            self.schema_name,
            provider_uuid,
            date(2026, 7, 1),
            date(2026, 7, 15),
            queue_name=PriorityQueue.DEFAULT,
            tracing_id="qe-trace",
        )

        self.assertEqual(
            DelayedCeleryTasks.objects.filter(
                task_name=UPDATE_COST_MODEL_COSTS_TASK, provider_uuid=provider_uuid
            ).count(),
            0,
        )
        mock_celery_app.send_task.assert_called_once()
        args, kwargs = mock_celery_app.send_task.call_args
        self.assertEqual(args[0], UPDATE_COST_MODEL_COSTS_TASK)
        self.assertEqual(kwargs["args"], [self.schema_name, str(provider_uuid)])
        self.assertEqual(kwargs["kwargs"]["start_date"], "2026-07-01")
        self.assertEqual(kwargs["kwargs"]["end_date"], "2026-07-15")
        self.assertEqual(kwargs["queue"], PriorityQueue.DEFAULT)
