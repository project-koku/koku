#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the GCPReportParquetProcessor."""
from datetime import date
from unittest.mock import patch

import pandas as pd
from django_tenants.utils import schema_context

from api.common import log_json
from api.utils import DateHelper
from masu.processor.gcp.gcp_report_parquet_processor import GCPReportParquetProcessor
from masu.test import MasuTestCase
from reporting.models import PartitionedTable
from reporting.provider.gcp.models import GCPCostEntryBill
from reporting.provider.gcp.models import GCPCostEntryLineItemDailySummary
from reporting.provider.gcp.models import TRINO_LINE_ITEM_DAILY_TABLE
from reporting.provider.gcp.models import TRINO_LINE_ITEM_TABLE
from reporting.provider.gcp.models import TRINO_OCP_ON_GCP_DAILY_TABLE
from reporting.provider.gcp.self_hosted_models import SELF_HOSTED_DAILY_MODEL_MAP
from reporting.provider.gcp.self_hosted_models import SELF_HOSTED_MODEL_MAP


class GCPReportProcessorParquetTest(MasuTestCase):
    """Test cases for the GCPReportParquetProcessor."""

    def setUp(self):
        """Setup up shared variables."""
        super().setUp()

        self.manifest_id = 1
        self.account = "org1234567"
        self.s3_path = "/s3/path"
        self.start_date = date(2024, 1, 15)
        self.processor = GCPReportParquetProcessor(
            self.manifest_id, self.account, self.s3_path, self.gcp_provider_uuid, self.start_date
        )

    def test_gcp_table_name(self):
        """Test the GCP table name generation."""
        self.assertEqual(self.processor._table_name, TRINO_LINE_ITEM_TABLE)

        s3_path = "/s3/path/openshift/daily"
        processor = GCPReportParquetProcessor(
            self.manifest_id, self.account, s3_path, self.gcp_provider_uuid, self.start_date
        )
        self.assertEqual(processor._table_name, TRINO_OCP_ON_GCP_DAILY_TABLE)

        s3_path = "/s3/path/daily"
        processor = GCPReportParquetProcessor(
            self.manifest_id, self.account, s3_path, self.gcp_provider_uuid, self.start_date
        )
        self.assertEqual(processor._table_name, TRINO_LINE_ITEM_DAILY_TABLE)

    def test_postgres_summary_table(self):
        """Test that the correct table is returned."""
        self.assertEqual(self.processor.postgres_summary_table, GCPCostEntryLineItemDailySummary)

    @patch("masu.processor.gcp.gcp_report_parquet_processor.GCPReportParquetProcessor._execute_trino_sql")
    def test_create_bill(self, mock_execute_sql):
        """Test that a bill is created in the Postgres database."""
        bill_date = DateHelper().this_month_start
        start_date = bill_date
        end_date = DateHelper().this_month_end
        account_id = "9999999999"
        mock_execute_sql.return_value = [[account_id]]

        self.processor.create_bill(bill_date.date())
        with schema_context(self.schema):
            bill = GCPCostEntryBill.objects.filter(
                billing_period_start=start_date,
                billing_period_end=end_date,
                provider=self.gcp_provider_uuid,
            )
            self.assertIsNotNone(bill.first())

    @patch("masu.processor.gcp.gcp_report_parquet_processor.GCPReportParquetProcessor._execute_trino_sql")
    def test_create_bill_with_string_arg(self, mock_execute_sql):
        """Test that a bill is created in the Postgres database."""
        bill_date = DateHelper().this_month_start
        start_date = bill_date
        end_date = DateHelper().this_month_end
        account_id = "9999999999"
        mock_execute_sql.return_value = [[account_id]]

        self.processor.create_bill(str(bill_date.date()))
        with schema_context(self.schema):
            bill = GCPCostEntryBill.objects.filter(
                billing_period_start=start_date,
                billing_period_end=end_date,
                provider=self.gcp_provider_uuid,
            )
            self.assertIsNotNone(bill.first())

    def test_get_or_create_postgres_partition(self):
        """Test that a Postgres daily summary partition is created."""
        bill_date = DateHelper().next_month_start
        pg_table = self.processor.postgres_summary_table._meta.db_table
        table_name = f"{pg_table}_{bill_date.strftime('%Y_%m')}"
        log_format = log_json(
            msg="created a new partition", schema=self.schema_name, table=pg_table, partition=table_name
        )
        expected_log = "INFO:masu.processor.report_parquet_processor_base:" + str(log_format)

        with self.assertLogs("masu.processor.report_parquet_processor_base", level="INFO") as logger:
            self.processor.get_or_create_postgres_partition(bill_date)
            self.assertIn(expected_log, logger.output)

        with schema_context(self.schema):
            self.assertNotEqual(PartitionedTable.objects.filter(table_name=table_name).count(), 0)

    def test_is_daily_flag(self):
        """Test that _is_daily is set correctly based on s3_path."""
        processor = GCPReportParquetProcessor(
            self.manifest_id, self.account, "/s3/path", self.gcp_provider_uuid, self.start_date
        )
        self.assertFalse(processor._is_daily)

        processor_daily = GCPReportParquetProcessor(
            self.manifest_id, self.account, "/s3/path/daily", self.gcp_provider_uuid, self.start_date
        )
        self.assertTrue(processor_daily._is_daily)

    def test_self_hosted_line_item_model(self):
        """Test that self_hosted_line_item_model returns correct model."""
        processor = GCPReportParquetProcessor(
            self.manifest_id, self.account, "/s3/path", self.gcp_provider_uuid, self.start_date
        )
        self.assertEqual(processor.self_hosted_line_item_model, SELF_HOSTED_MODEL_MAP.get("gcp_line_items"))

        processor_daily = GCPReportParquetProcessor(
            self.manifest_id, self.account, "/s3/path/daily", self.gcp_provider_uuid, self.start_date
        )
        self.assertEqual(
            processor_daily.self_hosted_line_item_model, SELF_HOSTED_DAILY_MODEL_MAP.get("gcp_line_items")
        )

    def test_get_table_names_for_delete(self):
        """Test that all GCP table names are returned."""
        table_names = self.processor.get_table_names_for_delete()
        self.assertEqual(len(table_names), 3)
        self.assertIn(TRINO_LINE_ITEM_TABLE, table_names)
        self.assertIn(TRINO_LINE_ITEM_DAILY_TABLE, table_names)
        self.assertIn(TRINO_OCP_ON_GCP_DAILY_TABLE, table_names)

    def test_prepare_dataframe_for_write(self):
        """Test that manifestid is added to dataframe."""
        data_frame = pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})
        metadata = {}
        self.processor._prepare_dataframe_for_write(data_frame, metadata)
        self.assertIn("manifestid", data_frame.columns)
        self.assertEqual(data_frame["manifestid"].iloc[0], str(self.manifest_id))

    @patch("masu.processor.report_parquet_processor_base.get_report_db_accessor")
    @patch(
        "masu.processor.gcp.gcp_report_parquet_processor.GCPReportParquetProcessor.get_or_create_postgres_partition"
    )
    def test_write_to_self_hosted_table(self, mock_partition, mock_get_accessor):
        """Test write_to_self_hosted_table writes data correctly."""
        processor = GCPReportParquetProcessor(
            self.manifest_id,
            self.account,
            "/s3/path/daily",
            self.gcp_provider_uuid,
            self.start_date,
        )

        data_frame = pd.DataFrame({"col1": [1, 2], "usage_start_time": pd.to_datetime(["2024-01-15", "2024-01-15"])})
        metadata = {}

        with patch("pandas.DataFrame.to_sql") as mock_to_sql:
            processor.write_to_self_hosted_table(data_frame, metadata)

            self.assertIn("manifestid", data_frame.columns)
            self.assertIn("year", data_frame.columns)
            self.assertIn("month", data_frame.columns)
            self.assertIn("source", data_frame.columns)
            self.assertIn("usage_start", data_frame.columns)
            self.assertIn("id", data_frame.columns)

            mock_partition.assert_called_once()
            mock_to_sql.assert_called_once()

    @patch("masu.processor.report_parquet_processor_base.get_report_db_accessor")
    def test_delete_day_postgres(self, mock_get_accessor):
        """Test delete_day_postgres."""
        mock_conn = mock_get_accessor.return_value.connect.return_value.__enter__.return_value
        mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
        mock_cursor.fetchone.return_value = None
        mock_cursor.rowcount = 0

        self.processor.delete_day_postgres(self.start_date)
