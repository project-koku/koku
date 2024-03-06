#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test Reporting Common."""
from unittest.mock import patch

from django.utils import timezone
from django_tenants.utils import schema_context

from api.models import Provider
from api.utils import DateHelper
from masu.processor.tasks import delayed_summarize_current_month
from masu.processor.tasks import UPDATE_SUMMARY_TABLES_QUEUE
from masu.processor.tasks import UPDATE_SUMMARY_TABLES_QUEUE_XL
from masu.processor.tasks import UPDATE_SUMMARY_TABLES_TASK
from masu.test import MasuTestCase
from reporting_common.models import CombinedChoices
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus
from reporting_common.models import DelayedCeleryTasks


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

    @patch("masu.processor.tasks.is_customer_large")
    def test_delayed_summarize_current_month(self, mock_large_customer):
        mock_large_customer.return_value = False
        test_matrix = {
            Provider.PROVIDER_AWS: self.aws_provider,
            Provider.PROVIDER_AZURE: self.azure_provider,
            Provider.PROVIDER_GCP: self.gcp_provider,
            Provider.PROVIDER_OCI: self.oci_provider,
            Provider.PROVIDER_OCP: self.ocp_provider,
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
                    self.assertEqual(db_entry.queue_name, UPDATE_SUMMARY_TABLES_QUEUE)

    @patch("masu.processor.tasks.is_customer_large")
    def test_large_customer(self, mock_large_customer):
        mock_large_customer.return_value = True
        delayed_summarize_current_month(self.schema_name, [self.aws_provider.uuid], Provider.PROVIDER_AWS)
        with schema_context(self.schema):
            db_entry = DelayedCeleryTasks.objects.get(provider_uuid=self.aws_provider.uuid)
            self.assertEqual(db_entry.queue_name, UPDATE_SUMMARY_TABLES_QUEUE_XL)
