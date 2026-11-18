#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AzureReportParquetProcessor."""
from datetime import date

from django_tenants.utils import schema_context

from api.utils import DateHelper
from masu.processor.azure.azure_report_parquet_processor import AzureReportParquetProcessor
from masu.test import MasuTestCase
from reporting.provider.azure.models import AzureCostEntryBill
from reporting.provider.azure.models import AzureCostEntryLineItemDailySummary
from reporting.provider.azure.models import TRINO_LINE_ITEM_TABLE
from reporting.provider.azure.models import TRINO_OCP_ON_AZURE_DAILY_TABLE


class AzureReportParquetProcessorTest(MasuTestCase):
    """Test cases for the AzureReportParquetProcessor."""

    def setUp(self):
        """Setup up shared variables."""
        super().setUp()

        self.manifest_id = 1
        self.account = "org1234567"
        self.s3_path = "/s3/path"
        self.provider_uuid = self.azure_provider_uuid
        self.start_date = date(2024, 1, 15)
        self.processor = AzureReportParquetProcessor(
            self.manifest_id, self.account, self.s3_path, self.provider_uuid, self.start_date
        )

    def test_azure_table_name(self):
        """Test the Azure table name generation."""
        self.assertEqual(self.processor._table_name, TRINO_LINE_ITEM_TABLE)

        s3_path = "/s3/path/openshift/daily"
        processor = AzureReportParquetProcessor(
            self.manifest_id, self.account, s3_path, self.aws_provider_uuid, self.start_date
        )
        self.assertEqual(processor._table_name, TRINO_OCP_ON_AZURE_DAILY_TABLE)

    def test_postgres_summary_table(self):
        """Test that the correct table is returned."""
        self.assertEqual(self.processor.postgres_summary_table, AzureCostEntryLineItemDailySummary)

    def test_create_bill(self):
        """Test that a bill is created in the Postgres database."""
        bill_date = DateHelper().this_month_start
        start_date = bill_date
        end_date = DateHelper().this_month_end

        self.processor.create_bill(bill_date.date())

        with schema_context(self.schema):
            bill = AzureCostEntryBill.objects.filter(
                billing_period_start=start_date,
                billing_period_end=end_date,
                provider=self.azure_provider_uuid,
            )
            self.assertIsNotNone(bill.first())

    def test_create_bill_with_string_arg(self):
        """Test that a bill is created in the Postgres database."""
        bill_date = DateHelper().this_month_start
        start_date = bill_date
        end_date = DateHelper().this_month_end

        self.processor.create_bill(str(bill_date.date()))

        with schema_context(self.schema):
            bill = AzureCostEntryBill.objects.filter(
                billing_period_start=start_date,
                billing_period_end=end_date,
                provider=self.azure_provider_uuid,
            )
            self.assertIsNotNone(bill.first())
