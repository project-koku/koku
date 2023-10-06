#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCPReportParquetSummaryUpdater."""
from datetime import datetime
from unittest.mock import patch

from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.processor.ocp.ocp_cloud_updater_base import OCPCloudUpdaterBase
from masu.processor.ocp.ocp_report_parquet_summary_updater import OCPReportParquetSummaryUpdater
from masu.test import MasuTestCase
from masu.util.ocp.common import get_cluster_alias_from_cluster_id
from masu.util.ocp.common import get_cluster_id_from_provider


class OCPReportParquetSummaryUpdaterTest(MasuTestCase):
    """Test cases for the OCPReportParquetSummaryUpdater."""

    def setUp(self):
        """Set up shared variables."""
        super().setUp()
        self.ocp_accessor = OCPReportDBAccessor(schema=self.schema)

        manifest_id = 1
        with ReportManifestDBAccessor() as manifest_accessor:
            self.manifest = manifest_accessor.get_manifest_by_id(manifest_id)
        self.updater = OCPReportParquetSummaryUpdater(self.schema_name, self.ocp_provider, self.manifest)

    def test_initialization_with_valid_params(self):
        """Test the valid initialization of OCPReportParquetSummaryUpdater."""

        cluster_id = get_cluster_id_from_provider(self.ocp_provider_uuid)
        cluster_alias = get_cluster_alias_from_cluster_id(cluster_id)

        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest_by_id(1)
        updater = OCPReportParquetSummaryUpdater(self.schema_name, self.ocp_provider, manifest)

        self.assertEqual(updater._cluster_id, cluster_id)
        self.assertEqual(updater._cluster_alias, cluster_alias)
        self.assertEqual(updater._schema, self.schema_name)
        self.assertEqual(updater._provider, self.ocp_provider)
        self.assertEqual(updater._manifest, manifest)

    @patch("masu.processor.ocp.ocp_report_parquet_summary_updater.get_cluster_id_from_provider")
    def test_initialization_missing_cluster_id_raises_error(self, mock_get_cluster_id):
        """Test the initialization of OCPReportParquetSummaryUpdater with no cluster_id."""

        mock_get_cluster_id.return_value = None
        with self.assertRaises(ValueError) as context:
            OCPReportParquetSummaryUpdater(self.schema_name, self.ocp_provider, "test_manifest")

        expected_error_msg = f"Missing cluster_id for provider: {self.ocp_provider.uuid}"
        self.assertEqual(str(context.exception), expected_error_msg)

    @patch("masu.processor.ocp.ocp_report_parquet_summary_updater.OCPReportDBAccessor")
    def test_check_parquet_date_range_min_timestamp_greater(self, mock_db_accessor):
        """Test _check_parquet_date_range when min_timestamp is greater than start_date."""

        last_month_start = self.dh.last_month_start
        end_date = self.dh.last_month_end.date()
        start_date = self.dh.previous_month(last_month_start).date()

        # Mock the get_max_min_timestamp_from_parquet method to return a greater min_timestamp value
        mock_accessor_instance = mock_db_accessor.return_value.__enter__.return_value
        mock_min_timestamp = datetime(last_month_start.year, last_month_start.month, last_month_start.day)
        mock_accessor_instance.get_max_min_timestamp_from_parquet.return_value = (mock_min_timestamp, None)

        adjusted_start_date, adjusted_end_date = self.updater._check_parquet_date_range(start_date, end_date)

        self.assertEqual(adjusted_start_date, mock_min_timestamp.date())
        self.assertEqual(adjusted_end_date, end_date)

    @patch("masu.processor.ocp.ocp_report_parquet_summary_updater.OCPReportDBAccessor")
    def test_check_parquet_date_range_min_timestamp_lesser(self, mock_db_accessor):
        """Test _check_parquet_date_range when min_timestamp is lesser than start_date."""

        start_date = self.dh.last_month_start.date()
        end_date = self.dh.last_month_end.date()

        # Mock the get_max_min_timestamp_from_parquet method to return a lesser min_timestamp value
        mock_accessor_instance = mock_db_accessor.return_value.__enter__.return_value
        test_min_timestamp = self.dh.previous_month(self.dh.last_month_start)
        mock_min_timestamp = datetime(test_min_timestamp.year, test_min_timestamp.month, test_min_timestamp.day)
        mock_accessor_instance.get_max_min_timestamp_from_parquet.return_value = (mock_min_timestamp, None)

        adjusted_start_date, adjusted_end_date = self.updater._check_parquet_date_range(start_date, end_date)

        self.assertEqual(adjusted_start_date, start_date)
        self.assertEqual(adjusted_end_date, end_date)

    @patch.object(OCPCloudUpdaterBase, "get_infra_map_from_providers")
    def test_check_cluster_infrastructure(self, mock_get_infra_map_provider):
        """Test that check_cluster_infrastructure logs correct info based on infrastructure map."""

        start_date = self.dh.last_month_start
        end_date = self.dh.last_month_end
        infra_map = {self.ocp_provider.uuid: ("infra_provider_uuid", "infra_provider_type")}
        mock_get_infra_map_provider.return_value = infra_map

        with self.assertLogs("masu.processor.ocp.ocp_report_parquet_summary_updater", "INFO") as mock_logger:
            self.updater.check_cluster_infrastructure(start_date, end_date)

        self.assertIn("OCP cluster is running on cloud infrastructure", mock_logger.output[0])
