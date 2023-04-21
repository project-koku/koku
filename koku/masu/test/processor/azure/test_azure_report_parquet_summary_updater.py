#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AzureReportParquetSummaryUpdater."""
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django_tenants.utils import schema_context

from api.utils import DateHelper
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.processor.azure.azure_report_parquet_summary_updater import AzureReportParquetSummaryUpdater
from masu.test import MasuTestCase
from masu.util.common import date_range_pair


class AzureReportParquetSummaryUpdaterTest(MasuTestCase):
    """Test cases for the AzureReportParquetSummaryUpdater."""

    def setUp(self):
        """Setup up shared variables."""
        super().setUp()
        self.dh = DateHelper()
        manifest_id = 1
        with ReportManifestDBAccessor() as manifest_accessor:
            self.manifest = manifest_accessor.get_manifest_by_id(manifest_id)
        self.updater = AzureReportParquetSummaryUpdater(self.schema_name, self.azure_provider, self.manifest)

    def test_get_sql_inputs(self):
        """Test that dates are returned."""
        # Previous month
        start_str = (self.dh.last_month_end - timedelta(days=3)).isoformat()
        end_str = self.dh.last_month_end.isoformat()
        start, end = self.updater._get_sql_inputs(start_str, end_str)
        self.assertEqual(start, self.dh.last_month_start.date())
        self.assertEqual(end, self.dh.last_month_end.date())

        # Current month
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest_by_id(2)
        updater = AzureReportParquetSummaryUpdater(self.schema_name, self.azure_provider, manifest)
        start_str = self.dh.this_month_start.isoformat()
        end_str = self.dh.this_month_end.isoformat()
        start, end = updater._get_sql_inputs(start_str, end_str)
        self.assertEqual(start, self.dh.this_month_start.date())
        self.assertEqual(end, self.dh.this_month_end.date())

        # No manifest
        updater = AzureReportParquetSummaryUpdater(self.schema_name, self.azure_provider, None)
        start_date = self.dh.last_month_end - timedelta(days=3)
        start_str = start_date.isoformat()
        end_str = self.dh.last_month_end.isoformat()
        start, end = updater._get_sql_inputs(start_str, end_str)
        self.assertEqual(start, start_date.date())
        self.assertEqual(end, self.dh.last_month_end.date())

    def test_update_daily_tables(self):
        """Test that this is a placeholder method."""
        start_str = self.dh.this_month_start.isoformat()
        end_str = self.dh.this_month_end.isoformat()
        expected_start, expected_end = self.updater._get_sql_inputs(start_str, end_str)

        expected_log = (
            "INFO:masu.processor.azure.azure_report_parquet_summary_updater:"
            f"update_daily_tables for: {expected_start}-{expected_end}"
        )

        with self.assertLogs("masu.processor.azure.azure_report_parquet_summary_updater", level="INFO") as logger:
            start, end = self.updater.update_daily_tables(start_str, end_str)
            self.assertIn(expected_log, logger.output)
        self.assertEqual(start, expected_start)
        self.assertEqual(end, expected_end)

    @patch(
        "masu.processor.azure.azure_report_parquet_summary_updater.AzureReportDBAccessor.delete_line_item_daily_summary_entries_for_date_range_raw"  # noqa: E501
    )
    @patch(
        "masu.processor.azure.azure_report_parquet_summary_updater.AzureReportDBAccessor.populate_tags_summary_table"
    )
    @patch(
        "masu.processor.azure.azure_report_parquet_summary_updater.AzureReportDBAccessor.populate_line_item_daily_summary_table_trino"  # noqa: E501
    )
    def test_update_daily_summary_tables(self, mock_trino, mock_tag_update, mock_delete):
        """Test that we run Trino summary."""
        start_str = self.dh.this_month_start.isoformat()
        end_str = self.dh.this_month_end.isoformat()
        start, end = self.updater._get_sql_inputs(start_str, end_str)

        for s, e in date_range_pair(start, end, step=settings.TRINO_DATE_STEP):
            expected_start, expected_end = s, e

        with AzureReportDBAccessor(self.schema) as accessor:
            with schema_context(self.schema):
                bills = accessor.bills_for_provider_uuid(self.azure_provider.uuid, start)
                bill_ids = [str(bill.id) for bill in bills]
                current_bill_id = bills.first().id if bills else None

        with CostModelDBAccessor(self.schema, self.azure_provider.uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100

        start_return, end_return = self.updater.update_summary_tables(start, end)
        mock_delete.assert_called_with(
            self.azure_provider.uuid, expected_start, expected_end, {"cost_entry_bill_id": current_bill_id}
        )
        mock_trino.assert_called_with(
            expected_start, expected_end, self.azure_provider.uuid, current_bill_id, markup_value
        )
        mock_tag_update.assert_called_with(bill_ids, start, end)

        self.assertEqual(start_return, start)
        self.assertEqual(end_return, end)
