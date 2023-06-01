#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCPReportParquetProcessor."""
import datetime

from django_tenants.utils import schema_context

from api.utils import DateHelper
from masu.processor.ocp.ocp_report_parquet_processor import OCPReportParquetProcessor
from masu.test import MasuTestCase
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting.provider.ocp.models import TRINO_LINE_ITEM_TABLE_DAILY_MAP
from reporting.provider.ocp.models import TRINO_LINE_ITEM_TABLE_MAP


class OCPReportProcessorParquetTest(MasuTestCase):
    """Test cases for the OCPReportParquetProcessor."""

    def setUp(self):
        """Setup up shared variables."""
        super().setUp()

        self.manifest_id = 1
        self.s3_schema_name = "org1234567"
        self.s3_path = "/s3/path"
        self.provider_uuid = self.ocp_provider_uuid
        self.local_parquet = "/local/path"
        self.report_type = "pod_usage"
        self.processor = OCPReportParquetProcessor(
            self.manifest_id,
            self.s3_schema_name,
            self.s3_path,
            self.provider_uuid,
            self.local_parquet,
            self.report_type,
        )

    def test_ocp_table_name(self):
        """Test the OCP table name generation."""
        self.assertEqual(self.processor._table_name, TRINO_LINE_ITEM_TABLE_MAP[self.report_type])

        s3_path = "/s3/path/daily"
        processor = OCPReportParquetProcessor(
            self.manifest_id, self.s3_schema_name, s3_path, self.provider_uuid, self.local_parquet, self.report_type
        )
        self.assertEqual(processor._table_name, TRINO_LINE_ITEM_TABLE_DAILY_MAP[self.report_type])

    def test_postgres_summary_table(self):
        """Test that the correct table is returned."""
        self.assertEqual(self.processor.postgres_summary_table, OCPUsageLineItemDailySummary)

    def test_create_bill(self):
        """Test that a bill is created in the Postgres database."""
        bill_date = DateHelper().next_month_start
        start_date = bill_date
        end_date = DateHelper().next_month_end + datetime.timedelta(days=1)
        self.processor.create_bill(bill_date.date())

        with schema_context(self.schema_name):
            report_period = OCPUsageReportPeriod.objects.filter(
                cluster_id=self.ocp_cluster_id,
                report_period_start=start_date,
                report_period_end=end_date,
                provider=self.ocp_provider_uuid,
            )
            self.assertIsNotNone(report_period.first())

    def test_create_bill_with_string_arg(self):
        """Test that a bill is created in the Postgres database."""
        bill_date = DateHelper().next_month_start
        start_date = bill_date
        end_date = DateHelper().next_month_end + datetime.timedelta(days=1)

        self.processor.create_bill(str(bill_date.date()))

        with schema_context(self.schema_name):
            report_period = OCPUsageReportPeriod.objects.filter(
                cluster_id=self.ocp_cluster_id,
                report_period_start=start_date,
                report_period_end=end_date,
                provider=self.ocp_provider_uuid,
            )
            self.assertIsNotNone(report_period.first())
