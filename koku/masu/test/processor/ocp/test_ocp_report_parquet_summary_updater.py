#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCPParquetReportSummaryUpdaterTest."""
import logging
from datetime import timedelta
from unittest.mock import patch

from api.utils import DateHelper
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.processor.ocp.ocp_report_parquet_summary_updater import OCPReportParquetSummaryUpdater
from masu.test import MasuTestCase

LOG = logging.getLogger(__name__)


class OCPParquetReportSummaryUpdaterTest(MasuTestCase):
    """Test cases for the OCPParquetReportSummaryUpdaterTest class."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.dh = DateHelper()

    def setUp(self):
        """Set up tests."""
        super().setUp()
        self.today = self.dh.today

    @patch(
        "masu.processor.ocp.ocp_report_parquet_summary_updater.determine_if_full_summary_update_needed",
        return_value=True,
    )
    def test_get_sql_inputs_do_month_update(self, mock_full_summary):
        """Test that dates are returned."""
        # Previous month
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest_by_id(1)
        updater = OCPReportParquetSummaryUpdater(self.schema_name, self.ocp_provider, manifest)
        start_str = (self.dh.last_month_end - timedelta(days=3)).isoformat()
        end_str = self.dh.last_month_end.isoformat()
        start, end = updater._get_sql_inputs(start_str, end_str)
        self.assertEqual(start, self.dh.last_month_start.date())
        self.assertEqual(end, self.dh.last_month_end.date())

        # Current month
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest_by_id(2)
        updater = OCPReportParquetSummaryUpdater(self.schema_name, self.ocp_provider, manifest)
        start_str = self.dh.this_month_start.isoformat()
        end_str = self.dh.this_month_end.isoformat()
        start, end = updater._get_sql_inputs(start_str, end_str)
        self.assertEqual(start, self.dh.this_month_start.date())
        expected_end = self.dh.this_month_end.replace(day=self.today.day)
        self.assertEqual(end, expected_end.date())
