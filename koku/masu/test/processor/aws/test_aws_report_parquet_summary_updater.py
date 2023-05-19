#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AWSReportParquetSummaryUpdater."""
from datetime import timedelta
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django_tenants.utils import schema_context

from api.utils import DateHelper
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.processor.aws.aws_report_parquet_summary_updater import AWSReportParquetSummaryUpdater
from masu.test import MasuTestCase
from masu.util.common import date_range_pair


class AWSReportParquetSummaryUpdaterTest(MasuTestCase):
    """Test cases for the AWSReportParquetSummaryUpdater."""

    def setUp(self):
        """Setup up shared variables."""
        super().setUp()
        self.dh = DateHelper()
        manifest_id = 1
        with ReportManifestDBAccessor() as manifest_accessor:
            self.manifest = manifest_accessor.get_manifest_by_id(manifest_id)
        self.updater = AWSReportParquetSummaryUpdater(self.schema_name, self.aws_provider, self.manifest)

    @patch("masu.processor.aws.aws_report_parquet_summary_updater.AWSReportDBAccessor.check_for_invoice_id_trino")
    def test_get_sql_inputs(self, _):
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
        updater = AWSReportParquetSummaryUpdater(self.schema_name, self.aws_provider, manifest)
        start_str = self.dh.this_month_start.isoformat()
        end_str = self.dh.this_month_end.isoformat()
        start, end = updater._get_sql_inputs(start_str, end_str)
        self.assertEqual(start, self.dh.this_month_start.date())
        self.assertEqual(end, self.dh.this_month_end.date())

        # No manifest
        updater = AWSReportParquetSummaryUpdater(self.schema_name, self.aws_provider, None)
        start_date = self.dh.last_month_end - timedelta(days=3)
        start_str = start_date.isoformat()
        end_str = self.dh.last_month_end.isoformat()
        start, end = updater._get_sql_inputs(start_str, end_str)
        self.assertEqual(start, start_date.date())
        self.assertEqual(end, self.dh.last_month_end.date())

    @patch("masu.processor.aws.aws_report_parquet_summary_updater.AWSReportDBAccessor.check_for_invoice_id_trino")
    def test_check_for_finalized_report(self, mock_invoice_check):
        """Test that we properly adjust start date for non-finalized reports."""
        dh = DateHelper()

        # Test current month
        mock_invoice_check.return_value = []
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        bill_date = dh.this_month_start
        result_start_date, result_end_date = self.updater._adjust_start_date_if_finalized(
            bill_date, start_date, end_date
        )
        self.assertEqual(result_start_date, start_date)
        self.assertEqual(result_end_date, end_date)

        mock_invoice_check.reset_mock()
        # Test previous month IS finalized
        mock_invoice_check.return_value = ["1"]
        start_date = dh.last_month_start
        end_date = dh.last_month_end
        bill_date = dh.last_month_start
        result_start_date, result_end_date = self.updater._adjust_start_date_if_finalized(
            bill_date, start_date, end_date
        )
        self.assertEqual(result_start_date, start_date)
        self.assertEqual(result_end_date, end_date)

        mock_invoice_check.reset_mock()
        # Test previous month NOT finalized
        mock_invoice_check.return_value = []
        start_date = dh.last_month_start
        end_date = dh.last_month_end
        bill_date = dh.last_month_start
        expected_start_date = end_date - relativedelta(days=2)
        result_start_date, result_end_date = self.updater._adjust_start_date_if_finalized(
            bill_date, start_date, end_date
        )
        self.assertNotEqual(result_start_date, start_date)
        self.assertEqual(result_start_date, expected_start_date)
        self.assertEqual(result_end_date, end_date)

    @patch("masu.processor.aws.aws_report_parquet_summary_updater.AWSReportDBAccessor.populate_category_summary_table")
    @patch("masu.processor.aws.aws_report_parquet_summary_updater.AWSReportDBAccessor.check_for_invoice_id_trino")
    @patch(
        "masu.processor.aws.aws_report_parquet_summary_updater.AWSReportDBAccessor.delete_line_item_daily_summary_entries_for_date_range_raw"  # noqa: E501
    )
    @patch("masu.processor.aws.aws_report_parquet_summary_updater.AWSReportDBAccessor.populate_tags_summary_table")
    @patch(
        "masu.processor.aws.aws_report_parquet_summary_updater.AWSReportDBAccessor.populate_line_item_daily_summary_table_trino"  # noqa: E501
    )
    def test_update_daily_summary_tables(self, mock_trino, mock_tag_update, mock_delete, _, mock_category_update):
        """Test that we run Trino summary."""
        start_str = self.dh.this_month_start.isoformat()
        end_str = self.dh.this_month_end.isoformat()
        start, end = self.updater._get_sql_inputs(start_str, end_str)

        for s, e in date_range_pair(start, end, step=settings.TRINO_DATE_STEP):
            expected_start, expected_end = s, e

        with AWSReportDBAccessor(self.schema) as accessor:
            with schema_context(self.schema):
                bills = accessor.bills_for_provider_uuid(self.aws_provider.uuid, start)
                bill_ids = [str(bill.id) for bill in bills]
                current_bill_id = bills.first().id if bills else None

        with CostModelDBAccessor(self.schema, self.aws_provider.uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100

        start_return, end_return = self.updater.update_summary_tables(start, end)

        mock_delete.assert_called_with(
            self.aws_provider.uuid, expected_start, expected_end, {"cost_entry_bill_id": current_bill_id}
        )
        mock_trino.assert_called_with(
            expected_start, expected_end, self.aws_provider.uuid, current_bill_id, markup_value
        )
        mock_tag_update.assert_called_with(bill_ids, start, end)
        mock_category_update.assert_called_with(bill_ids, start, end)

        self.assertEqual(start_return, start)
        self.assertEqual(end_return, end)

    @patch("masu.processor.aws.aws_report_parquet_summary_updater.AWSReportDBAccessor.check_for_invoice_id_trino")
    @patch(
        "masu.processor.aws.aws_report_parquet_summary_updater.AWSReportDBAccessor.populate_line_item_daily_summary_table_trino"  # noqa: E501
    )
    def test_update_summary_tables_no_bills(self, *args):
        """Test that summarization is skipped if no bill id found."""

        start_str = self.dh.this_month_start.isoformat()
        end_str = self.dh.this_month_end.isoformat()
        start, end = self.updater._get_sql_inputs(start_str, end_str)

        with patch(
            "masu.processor.aws.aws_report_parquet_summary_updater.AWSReportDBAccessor.bills_for_provider_uuid",
            return_value=[],
        ):
            with self.assertLogs("masu.processor.aws.aws_report_parquet_summary_updater", level="INFO") as logs:
                start_return, end_return = self.updater.update_summary_tables(start_str, end_str)
                expected_log_msg = f"No bill was found for {start_return}. Skipping summarization"

        self.assertEqual(start_return, start)
        self.assertEqual(end_return, end)
        self.assertIn(expected_log_msg, logs.output[-1])
