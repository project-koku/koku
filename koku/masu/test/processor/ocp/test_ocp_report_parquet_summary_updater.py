#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCPReportParquetSummaryUpdater."""
from contextlib import contextmanager
from contextlib import nullcontext
from datetime import date
from datetime import datetime
from datetime import timedelta
from unittest.mock import call
from unittest.mock import Mock
from unittest.mock import patch

from django.test import override_settings

from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.exceptions import SummaryPeriodLockUnavailable
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

    @override_settings(ONPREM=False)
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

    @override_settings(ONPREM=True)
    @patch("masu.processor.ocp.ocp_report_parquet_summary_updater.OCPCloudUpdaterBase")
    def test_check_cluster_infrastructure_skips_unsupported_onprem_cloud_probe(self, cloud_updater):
        """On-prem supports OCP only and must not load SaaS cloud-provider SQL."""
        self.updater.check_cluster_infrastructure(self.dh.last_month_start, self.dh.last_month_end)

        cloud_updater.assert_not_called()

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
        """The flagged path keeps daily tag mapping and covers each main-chunk day."""
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
            [call(42, wait=False, shared=True)],
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

    @override_settings(TRINO_DATE_STEP=3)
    @patch(
        "masu.processor.ocp.ocp_report_parquet_summary_updater.schema_context",
        side_effect=lambda _schema: nullcontext(),
    )
    @patch.object(OCPReportParquetSummaryUpdater, "check_cluster_infrastructure")
    @patch.object(OCPReportParquetSummaryUpdater, "_handle_partitions")
    @patch.object(OCPReportParquetSummaryUpdater, "_check_parquet_date_range")
    @patch.object(OCPReportParquetSummaryUpdater, "_get_sql_inputs")
    @patch("masu.processor.ocp.ocp_report_parquet_summary_updater.is_feature_flag_enabled_by_schema")
    @patch("masu.processor.ocp.ocp_report_parquet_summary_updater.OCPReportDBAccessor")
    def test_flagged_summary_keeps_one_period_lock_and_locks_every_chunk_day(
        self,
        accessor_class,
        flag_enabled,
        get_sql_inputs,
        check_parquet_date_range,
        handle_partitions,
        check_cluster_infrastructure,
        schema_context_mock,
    ):
        """Preserve Trino chunk size while excluding cost-model writes throughout summary work."""
        start_date = date(2026, 9, 1)
        end_date = date(2026, 9, 7)
        get_sql_inputs.return_value = (start_date, end_date)
        check_parquet_date_range.return_value = (start_date, end_date)
        flag_enabled.return_value = True
        accessor = accessor_class.return_value.__enter__.return_value
        report_period = Mock(id=42, summary_data_creation_datetime=None)
        accessor.report_periods_for_provider_uuid.return_value = report_period
        period_held = False
        locked_days = set()

        @contextmanager
        def period_lock(*_args, **_kwargs):
            nonlocal period_held
            self.assertFalse(period_held)
            period_held = True
            try:
                yield
            finally:
                period_held = False

        @contextmanager
        def day_lock(_period_id, summary_date, **_kwargs):
            self.assertTrue(period_held)
            self.assertNotIn(summary_date, locked_days)
            locked_days.add(summary_date)
            try:
                yield
            finally:
                locked_days.remove(summary_date)

        def assert_chunk_locked(_source_uuid, _period_id, chunk_start, chunk_end):
            expected_days = {
                chunk_start + timedelta(days=offset) for offset in range((chunk_end - chunk_start).days + 1)
            }
            self.assertTrue(period_held)
            self.assertEqual(locked_days, expected_days)

        def assert_tag_mapping_locked(day_start, day_end, _period_ids):
            self.assertTrue(period_held)
            self.assertEqual(day_start, day_end)
            self.assertEqual(locked_days, {day_start})

        accessor.summary_period_lock.side_effect = period_lock
        accessor.summary_day_lock.side_effect = day_lock
        accessor.delete_all_except_infrastructure_raw_cost_from_daily_summary.side_effect = assert_chunk_locked
        accessor.update_line_item_daily_summary_with_tag_mapping.side_effect = assert_tag_mapping_locked
        accessor.populate_pod_label_summary_table.side_effect = lambda *_args: self.assertTrue(period_held)
        accessor.populate_volume_label_summary_table.side_effect = lambda *_args: self.assertTrue(period_held)
        report_period.save.side_effect = lambda: self.assertTrue(period_held)
        check_cluster_infrastructure.side_effect = lambda *_args: self.assertFalse(period_held)

        with self.assertLogs("masu.processor.ocp.ocp_report_parquet_summary_updater", level="INFO") as captured:
            self.updater.update_summary_tables(start_date, end_date)

        accessor.summary_period_lock.assert_called_once_with(42, wait=False, shared=True)
        self.assertEqual(
            accessor.delete_all_except_infrastructure_raw_cost_from_daily_summary.call_args_list,
            [
                call(self.ocp_provider.uuid, 42, date(2026, 9, 1), date(2026, 9, 4)),
                call(self.ocp_provider.uuid, 42, date(2026, 9, 5), date(2026, 9, 7)),
            ],
        )
        self.assertEqual(accessor.summary_day_lock.call_count, 14)
        self.assertEqual(accessor.update_line_item_daily_summary_with_tag_mapping.call_count, 7)
        timed_logs = [record.msg for record in captured.records if isinstance(record.msg, dict)]
        for message, expected_count in (
            ("updated OCP report summary chunk", 2),
            ("updated OCP label summary tables", 1),
            ("updated OCP tag mapping day", 7),
            ("completed OCP summary write phase", 1),
        ):
            matching = [entry for entry in timed_logs if entry.get("message") == message]
            self.assertEqual(len(matching), expected_count, message)
            self.assertTrue(all(entry["running_time"] >= 0 for entry in matching))
        self.assertFalse(period_held)
        self.assertFalse(locked_days)

    @override_settings(TRINO_DATE_STEP=3)
    @patch(
        "masu.processor.ocp.ocp_report_parquet_summary_updater.schema_context",
        side_effect=lambda _schema: nullcontext(),
    )
    @patch.object(OCPReportParquetSummaryUpdater, "check_cluster_infrastructure")
    @patch.object(OCPReportParquetSummaryUpdater, "_handle_partitions")
    @patch.object(OCPReportParquetSummaryUpdater, "_check_parquet_date_range")
    @patch.object(OCPReportParquetSummaryUpdater, "_get_sql_inputs")
    @patch("masu.processor.ocp.ocp_report_parquet_summary_updater.is_feature_flag_enabled_by_schema")
    @patch("masu.processor.ocp.ocp_report_parquet_summary_updater.OCPReportDBAccessor")
    def test_flagged_summary_releases_partial_day_locks_before_retry(
        self,
        accessor_class,
        flag_enabled,
        get_sql_inputs,
        check_parquet_date_range,
        handle_partitions,
        check_cluster_infrastructure,
        schema_context_mock,
    ):
        """A contended later day releases earlier locks without starting the chunk."""
        start_date = date(2026, 9, 1)
        end_date = date(2026, 9, 4)
        get_sql_inputs.return_value = (start_date, end_date)
        check_parquet_date_range.return_value = (start_date, end_date)
        flag_enabled.return_value = True
        accessor = accessor_class.return_value.__enter__.return_value
        accessor.report_periods_for_provider_uuid.return_value = Mock(id=42)
        period_held = False
        locked_days = set()

        @contextmanager
        def period_lock(*_args, **_kwargs):
            nonlocal period_held
            period_held = True
            try:
                yield
            finally:
                period_held = False

        @contextmanager
        def day_lock(_period_id, summary_date, **_kwargs):
            if summary_date == date(2026, 9, 3):
                raise SummaryPeriodLockUnavailable("third day held")
            locked_days.add(summary_date)
            try:
                yield
            finally:
                locked_days.remove(summary_date)

        accessor.summary_period_lock.side_effect = period_lock
        accessor.summary_day_lock.side_effect = day_lock

        with self.assertRaises(SummaryPeriodLockUnavailable):
            self.updater.update_summary_tables(start_date, end_date)

        self.assertFalse(period_held)
        self.assertFalse(locked_days)
        accessor.delete_all_except_infrastructure_raw_cost_from_daily_summary.assert_not_called()
        accessor.populate_line_item_daily_summary_table_trino.assert_not_called()
        accessor.update_line_item_daily_summary_with_tag_mapping.assert_not_called()
        check_cluster_infrastructure.assert_not_called()

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
