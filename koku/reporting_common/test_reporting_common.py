#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test Reporting Common."""
from django.utils import timezone

from masu.test import MasuTestCase
from reporting_common.models import CombinedChoices
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus


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
