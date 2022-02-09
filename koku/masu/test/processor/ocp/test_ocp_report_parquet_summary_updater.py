#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCPReportProcessor."""
import datetime
from unittest.mock import patch

from api.utils import DateHelper
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.processor.ocp.ocp_report_parquet_summary_updater import OCPReportParquetSummaryUpdater
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator
from reporting_common.models import CostUsageReportManifest


class OCPReportSummaryUpdaterTest(MasuTestCase):
    """Test cases for the OCPReportSummaryUpdater class."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()

        cls.accessor = OCPReportDBAccessor(cls.schema)
        cls.report_schema = cls.accessor.report_schema
        cls.all_tables = list(OCP_REPORT_TABLE_MAP.values())
        cls.creator = ReportObjectCreator(cls.schema)
        cls.date_accessor = DateHelper()
        cls.manifest_accessor = ReportManifestDBAccessor()
        cls.dh = DateHelper()

    def setUp(self):
        """Set up each test."""
        super().setUp()

        self.provider = self.ocp_provider

        self.today = self.dh.today
        billing_start = datetime.datetime(year=self.today.year, month=self.today.month, day=self.today.day).replace(
            day=1
        )
        self.manifest_dict = {
            "assembly_id": "1234",
            "billing_period_start_datetime": billing_start,
            "num_total_files": 2,
            "num_processed_files": 1,
            "provider_uuid": self.ocp_provider_uuid,
        }

        self.cluster_id = self.ocp_cluster_id
        self.manifest = CostUsageReportManifest.objects.filter(
            provider_id=self.ocp_provider_uuid, billing_period_start_datetime=self.dh.this_month_start
        ).first()
        self.manifest.num_total_files = 2
        self.manifest.save()
        self.updater = OCPReportParquetSummaryUpdater(self.schema, self.provider, self.manifest)

    @patch(
        "masu.processor.ocp.ocp_report_parquet_summary_updater.OCPReportParquetSummaryUpdater._check_parquet_date_range"
    )
    @patch(
        "masu.processor.ocp.ocp_report_parquet_summary_updater.OCPReportDBAccessor.populate_openshift_cluster_information_tables"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_report_parquet_summary_updater.OCPReportDBAccessor.delete_line_item_daily_summary_entries_for_date_range"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_report_parquet_summary_updater."
        "OCPReportDBAccessor.populate_volume_label_summary_table"
    )
    @patch(
        "masu.processor.ocp.ocp_report_parquet_summary_updater." "OCPReportDBAccessor.populate_pod_label_summary_table"
    )
    @patch(
        "masu.processor.ocp.ocp_report_parquet_summary_updater."
        "OCPReportDBAccessor.populate_line_item_daily_summary_table_presto"
    )
    def test_update_summary_tables(
        self, mock_sum, mock_tag_sum, mock_vol_tag_sum, mock_delete, mock_cluster_populate, mock_date_check
    ):
        """Test that summary tables are run for a full month when no report period is found."""
        start_date = self.dh.today
        end_date = start_date

        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")

        mock_date_check.return_value = (start_date, end_date)

        self.updater.update_summary_tables(start_date_str, end_date_str)
        mock_delete.assert_called_with(self.ocp_provider.uuid, start_date.date(), end_date.date())
        mock_sum.assert_called()
        mock_tag_sum.assert_called()
        mock_vol_tag_sum.assert_called()
        mock_date_check.assert_called()

    def test_update_daily_tables(self):
        start_date = self.dh.today
        end_date = start_date
        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")
        expected = (
            "INFO:masu.processor.ocp.ocp_report_parquet_summary_updater:"
            "NO-OP update_daily_tables for: %s-%s" % (start_date_str, end_date_str)
        )
        with self.assertLogs("masu.processor.ocp.ocp_report_parquet_summary_updater", level="INFO") as _logger:
            self.updater.update_daily_tables(start_date_str, end_date_str)
            self.assertIn(expected, _logger.output)

    @patch(
        "masu.processor.ocp.ocp_report_parquet_summary_updater.OCPReportDBAccessor."
        "get_max_min_timestamp_from_parquet"  # noqa: E501
    )
    def test_check_parquet_date_range(self, mock_get_timestamps):
        """Check that we modify start date when needed."""
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.this_month_end.date()

        parquet_start_date = self.dh.this_month_start.replace(tzinfo=None) + datetime.timedelta(days=1)
        parquet_end_date = self.dh.today.replace(tzinfo=None)
        mock_get_timestamps.return_value = (parquet_start_date, parquet_end_date)

        result_start, result_end = self.updater._check_parquet_date_range(start_date, end_date)
        self.assertNotEqual(start_date, result_start)
        self.assertEqual(parquet_start_date.date(), result_start)
