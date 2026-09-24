#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCPReportParquetSummaryUpdater."""
from contextlib import nullcontext
from datetime import date
from datetime import datetime
from unittest.mock import call
from unittest.mock import Mock
from unittest.mock import patch

from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.processor.ocp.ocp_cloud_updater_base import OCPCloudUpdaterBase
from masu.processor.ocp.ocp_report_parquet_summary_updater import OCPReportParquetSummaryUpdater
from masu.processor.ocp.ocp_report_parquet_summary_updater import OCPReportParquetSummaryUpdaterClusterNotFound
from masu.test import MasuTestCase
from masu.util.ocp.common import get_cluster_alias_from_cluster_id
from masu.util.ocp.common import get_cluster_id_from_provider


class OCPReportParquetSummaryUpdaterTest(MasuTestCase):
    """Test cases for the OCPReportParquetSummaryUpdater."""

    def setUp(self):
        """Set up shared variables."""
        super().setUp()
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
        with self.assertRaises(OCPReportParquetSummaryUpdaterClusterNotFound) as context:
            OCPReportParquetSummaryUpdater(self.schema_name, self.ocp_provider, "test_manifest")

        expected_error_msg = "missing cluster_id for provider"
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

    @patch(
        "masu.processor.ocp.ocp_report_parquet_summary_updater.schema_context",
        side_effect=lambda _schema: nullcontext(),
    )
    @patch.object(OCPReportParquetSummaryUpdater, "check_cluster_infrastructure")
    @patch.object(OCPReportParquetSummaryUpdater, "_handle_partitions")
    @patch.object(OCPReportParquetSummaryUpdater, "_check_parquet_date_range")
    @patch.object(OCPReportParquetSummaryUpdater, "_get_sql_inputs")
    @patch("masu.processor.ocp.ocp_report_parquet_summary_updater.is_feature_flag_enabled_by_schema", create=True)
    @patch("masu.processor.ocp.ocp_report_parquet_summary_updater.OCPReportDBAccessor")
    def test_flagged_summary_serializes_daily_chunks_and_tagmaps_each_day(
        self,
        accessor_class,
        flag_enabled,
        get_sql_inputs,
        check_parquet_date_range,
        handle_partitions,
        check_cluster_infrastructure,
        schema_context_mock,
    ):
        """The flagged path holds period/day locks only for one calendar day."""
        start_date = date(2026, 9, 1)
        end_date = date(2026, 9, 3)
        get_sql_inputs.return_value = (start_date, end_date)
        check_parquet_date_range.return_value = (start_date, end_date)
        flag_enabled.return_value = True

        accessor = accessor_class.return_value.__enter__.return_value
        report_period = Mock(id=42, summary_data_creation_datetime=None)
        accessor.report_periods_for_provider_uuid.return_value = report_period
        accessor.summary_period_lock.return_value = nullcontext()
        accessor.summary_day_lock.return_value = nullcontext()

        self.updater.update_summary_tables(start_date, end_date)

        self.assertEqual(
            accessor.summary_period_lock.call_args_list,
            [call(42, wait=False, shared=True)] * 6,
        )
        self.assertEqual(
            accessor.summary_day_lock.call_args_list,
            [
                call(42, date(2026, 9, 1), wait=False),
                call(42, date(2026, 9, 2), wait=False),
                call(42, date(2026, 9, 3), wait=False),
                call(42, date(2026, 9, 1), wait=False),
                call(42, date(2026, 9, 2), wait=False),
                call(42, date(2026, 9, 3), wait=False),
            ],
        )
        self.assertEqual(
            accessor.update_line_item_daily_summary_with_tag_mapping.call_args_list,
            [
                call(date(2026, 9, 1), date(2026, 9, 1), [42]),
                call(date(2026, 9, 2), date(2026, 9, 2), [42]),
                call(date(2026, 9, 3), date(2026, 9, 3), [42]),
            ],
        )
        method_names = [method_name for method_name, _args, _kwargs in accessor.method_calls]
        self.assertLess(
            method_names.index("populate_volume_label_summary_table"),
            method_names.index("update_line_item_daily_summary_with_tag_mapping"),
        )

    @patch(
        "masu.processor.ocp.ocp_report_parquet_summary_updater.schema_context",
        side_effect=lambda _schema: nullcontext(),
    )
    @patch.object(OCPReportParquetSummaryUpdater, "check_cluster_infrastructure")
    @patch.object(OCPReportParquetSummaryUpdater, "_handle_partitions")
    @patch.object(OCPReportParquetSummaryUpdater, "_check_parquet_date_range")
    @patch.object(OCPReportParquetSummaryUpdater, "_get_sql_inputs")
    @patch("masu.processor.ocp.ocp_report_parquet_summary_updater.is_feature_flag_enabled_by_schema", create=True)
    @patch("masu.processor.ocp.ocp_report_parquet_summary_updater.OCPReportDBAccessor")
    def test_legacy_summary_keeps_single_full_range_tag_mapping(
        self,
        accessor_class,
        flag_enabled,
        get_sql_inputs,
        check_parquet_date_range,
        handle_partitions,
        check_cluster_infrastructure,
        schema_context_mock,
    ):
        """Flag OFF preserves the legacy full-range tag-mapping statement."""
        start_date = date(2026, 9, 1)
        end_date = date(2026, 9, 3)
        get_sql_inputs.return_value = (start_date, end_date)
        check_parquet_date_range.return_value = (start_date, end_date)
        flag_enabled.return_value = False

        accessor = accessor_class.return_value.__enter__.return_value
        report_period = Mock(id=42, summary_data_creation_datetime=None)
        accessor.report_periods_for_provider_uuid.return_value = report_period

        self.updater.update_summary_tables(start_date, end_date)

        accessor.summary_period_lock.assert_not_called()
        accessor.update_line_item_daily_summary_with_tag_mapping.assert_called_once_with(start_date, end_date, [42])
