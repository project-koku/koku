#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test Reporting Common."""
from django.utils import timezone

from masu.test import MasuTestCase
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

    def test_update_last_started_datetime(self):
        """Test update_last_started_datetime sets the last_started_datetime."""
        stats = CostUsageReportStatus(
            report_name=self.report_name,
            manifest_id=self.manifest.id,
        )
        stats.save()
        self.assertIsNone(stats.last_started_datetime)
        stats.update_last_started_datetime()
        self.assertIsNotNone(stats.last_started_datetime)

        old_datetime = stats.last_started_datetime
        stats.update_last_started_datetime()
        self.assertNotEqual(stats.last_started_datetime, old_datetime)

    def test_clear_last_started_datetime(self):
        """Test clear_last_started_datetime deletes the last_started_datetime."""
        stats = CostUsageReportStatus(
            report_name=self.report_name,
            manifest_id=self.manifest.id,
            last_started_datetime=timezone.now(),
        )
        stats.save()
        self.assertIsNotNone(stats.last_started_datetime)
        stats.clear_last_started_datetime()
        self.assertIsNone(stats.last_started_datetime)

    def test_set_last_completed_datetime(self):
        """Test set_last_completed_datetime set the last_completed_datetime."""
        stats = CostUsageReportStatus(
            report_name=self.report_name,
            manifest_id=self.manifest.id,
            last_started_datetime=timezone.now(),
        )
        stats.save()
        self.assertIsNone(stats.last_completed_datetime)
        stats.set_last_completed_datetime()
        self.assertIsNotNone(stats.last_completed_datetime)
