#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCIReportParquetProcessor."""
from unittest.mock import patch

from django_tenants.utils import schema_context

from api.utils import DateHelper
from masu.processor.oci.oci_report_parquet_processor import OCIReportParquetProcessor
from masu.test import MasuTestCase
from reporting.models import PartitionedTable
from reporting.provider.oci.models import OCICostEntryBill
from reporting.provider.oci.models import OCICostEntryLineItemDailySummary
from reporting.provider.oci.models import TRINO_LINE_ITEM_DAILY_TABLE_MAP
from reporting.provider.oci.models import TRINO_LINE_ITEM_TABLE_MAP


class OCIReportProcessorParquetTest(MasuTestCase):
    """Test cases for the OCIReportParquetProcessor."""

    def setUp(self):
        """Setup up shared variables."""
        super().setUp()

        self.manifest_id = 1
        self.s3_schema_name = "org1234567"
        self.s3_path = "/s3/path"
        self.local_parquet = "/local/path"
        self.processor = OCIReportParquetProcessor(
            self.manifest_id, self.s3_schema_name, self.s3_path, self.oci_provider_uuid, self.local_parquet, "usage"
        )

    def test_oci_table_name(self):
        """Test the OCI table name generation."""
        self.assertEqual(self.processor._table_name, TRINO_LINE_ITEM_TABLE_MAP["usage"])

        s3_path = "/s3/path/daily"
        processor = OCIReportParquetProcessor(
            self.manifest_id, self.s3_schema_name, s3_path, self.oci_provider_uuid, self.local_parquet, "usage"
        )
        self.assertEqual(processor._table_name, TRINO_LINE_ITEM_DAILY_TABLE_MAP["usage"])

    def test_postgres_summary_table(self):
        """Test that the correct table is returned."""
        self.assertEqual(self.processor.postgres_summary_table, OCICostEntryLineItemDailySummary)

    @patch("masu.processor.oci.oci_report_parquet_processor.OCIReportParquetProcessor._execute_sql")
    def test_create_bill(self, mock_execute_sql):
        """Test that a bill is created in the Postgres database."""
        bill_date = DateHelper().this_month_start
        start_date = bill_date
        end_date = DateHelper().this_month_end
        payer_tenant_id = "9999999999"
        mock_execute_sql.return_value = [[payer_tenant_id]]

        self.processor.create_bill(bill_date.date())
        with schema_context(self.schema_name):
            bill = OCICostEntryBill.objects.filter(
                billing_period_start=start_date,
                billing_period_end=end_date,
                payer_tenant_id=payer_tenant_id,
                provider=self.oci_provider,
            )
            self.assertIsNotNone(bill.first())

    @patch("masu.processor.oci.oci_report_parquet_processor.OCIReportParquetProcessor._execute_sql")
    def test_create_bill_with_string_arg(self, mock_execute_sql):
        """Test that a bill is created in the Postgres database."""
        bill_date = DateHelper().this_month_start
        start_date = bill_date
        end_date = DateHelper().this_month_end
        payer_tenant_id = "9999999999"
        mock_execute_sql.return_value = [[payer_tenant_id]]

        self.processor.create_bill(str(bill_date.date()))
        with schema_context(self.schema_name):
            bill = OCICostEntryBill.objects.filter(
                billing_period_start=start_date,
                billing_period_end=end_date,
                payer_tenant_id=payer_tenant_id,
                provider=self.oci_provider,
            )
            self.assertIsNotNone(bill.first())

    def test_get_or_create_postgres_partition(self):
        """Test that a Postgres daily summary partition is created."""
        bill_date = DateHelper().next_month_start
        pg_table = self.processor.postgres_summary_table._meta.db_table
        table_name = f"{pg_table}_{bill_date.strftime('%Y_%m')}"
        expected_log = (
            f"INFO:masu.processor.report_parquet_processor_base:"
            f"Created a new partition for {pg_table} : {table_name}"
        )

        with self.assertLogs("masu.processor.report_parquet_processor_base", level="INFO") as logger:
            self.processor.get_or_create_postgres_partition(bill_date)
            self.assertIn(expected_log, logger.output)

        with schema_context(self.schema_name):
            self.assertNotEqual(PartitionedTable.objects.filter(table_name=table_name).count(), 0)
