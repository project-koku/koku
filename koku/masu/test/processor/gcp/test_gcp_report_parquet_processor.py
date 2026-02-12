#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the GCPReportParquetProcessor."""
from datetime import date
from unittest.mock import patch

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
