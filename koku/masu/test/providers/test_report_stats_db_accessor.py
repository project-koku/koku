#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ReportStatsDBAccessor utility object."""
from datetime import datetime

from dateutil import parser

from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.test import MasuTestCase
from reporting_common.models import CostUsageReportStatus


class ReportStatsDBAccessorTest(MasuTestCase):
    """Test Cases for the ReportStatsDBAccessor object."""

    def setUp(self):
        """Set up the test class."""
        super().setUp()
        billing_start = datetime.utcnow().replace(day=1)
        manifest_dict = {
            "assembly_id": "1234",
            "billing_period_start_datetime": billing_start,
            "num_total_files": 2,
            "provider_uuid": self.aws_provider_uuid,
        }
        self.manifest_accessor = ReportManifestDBAccessor()

        manifest = self.manifest_accessor.add(**manifest_dict)
        self.manifest_id = manifest.id

    def test_initializer(self):
        """Test Initializer."""
        saver = ReportStatsDBAccessor("myreport", self.manifest_id)
        self.assertIsNotNone(saver._obj)

    def test_initializer_preexisting_report(self):
        """Test getting a new accessor stats on a preexisting report."""
        saver = ReportStatsDBAccessor("myreport", self.manifest_id)
        saver.update(
            cursor_position=33,
            last_completed_datetime="2011-1-1 11:11:11",
            last_started_datetime="2022-2-2 22:22:22",
            etag="myetag",
        )

        self.assertIsNotNone(saver._obj)

        # Get another accessor for the same report and verify we get back the right information.
        saver2 = ReportStatsDBAccessor("myreport", self.manifest_id)
        last_completed = saver2.get_last_completed_datetime()

        self.assertEqual(last_completed.year, 2011)
        self.assertEqual(last_completed.month, 1)
        self.assertEqual(last_completed.day, 1)
        self.assertEqual(last_completed.hour, 11)
        self.assertEqual(last_completed.minute, 11)
        self.assertEqual(last_completed.second, 11)

        self.assertEqual(saver.get_etag(), "myetag")

    def test_add_remove(self):
        """Test basic add/remove logic."""
        saver = ReportStatsDBAccessor("myreport", self.manifest_id)

        self.assertTrue(saver.does_db_entry_exist())
        returned_obj = saver._get_db_obj_query()
        self.assertEqual(returned_obj.first().report_name, "myreport")

        saver.delete()
        returned_obj = saver._get_db_obj_query()
        self.assertIsNone(returned_obj.first())

    def test_update(self):
        """Test updating an existing row."""
        saver = ReportStatsDBAccessor("myreport", self.manifest_id)

        returned_obj = saver._get_db_obj_query()
        self.assertEqual(returned_obj.first().report_name, "myreport")

        saver.update(
            cursor_position=33,
            last_completed_datetime=parser.parse("2011-1-1 11:11:11"),
            last_started_datetime=parser.parse("2022-2-2 22:22:22"),
            etag="myetag",
        )

        last_completed = saver.get_last_completed_datetime()
        self.assertEqual(last_completed.year, 2011)
        self.assertEqual(last_completed.month, 1)
        self.assertEqual(last_completed.day, 1)
        self.assertEqual(last_completed.hour, 11)
        self.assertEqual(last_completed.minute, 11)
        self.assertEqual(last_completed.second, 11)

        last_started = saver.get_last_started_datetime()
        self.assertEqual(last_started.year, 2022)
        self.assertEqual(last_started.month, 2)
        self.assertEqual(last_started.day, 2)
        self.assertEqual(last_started.hour, 22)
        self.assertEqual(last_started.minute, 22)
        self.assertEqual(last_started.second, 22)

        self.assertEqual(saver.get_etag(), "myetag")

        saver.delete()
        returned_obj = saver._get_db_obj_query()
        self.assertIsNone(returned_obj.first())

    def test_log_last_started_datetime(self):
        """Test convience function for last started processing time."""
        initial_count = CostUsageReportStatus.objects.count()
        saver = ReportStatsDBAccessor("myreport", self.manifest_id)
        saver.log_last_started_datetime()
        self.assertIsNotNone(saver.get_last_started_datetime())
        saver.delete()
        self.assertEqual(CostUsageReportStatus.objects.count(), initial_count)

    def test_log_last_completed_datetime(self):
        """Test convience function for last completed processing time."""
        initial_count = CostUsageReportStatus.objects.count()
        saver = ReportStatsDBAccessor("myreport", self.manifest_id)
        saver.log_last_completed_datetime()
        self.assertIsNotNone(saver.get_last_completed_datetime())
        saver.delete()
        self.assertEqual(CostUsageReportStatus.objects.count(), initial_count)

    def test_clear_last_started_date(self):
        """Test convience function for clear last started date."""
        saver = ReportStatsDBAccessor("myreport", self.manifest_id)
        saver.log_last_started_datetime()
        self.assertIsNotNone(saver.get_last_started_datetime())
        saver.clear_last_started_datetime()
        self.assertIsNone(saver.get_last_started_datetime())
