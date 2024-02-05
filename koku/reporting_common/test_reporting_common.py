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
