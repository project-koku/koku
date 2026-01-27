#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCPReportParquetProcessor."""
import datetime
from datetime import date
from unittest.mock import patch

import pandas as pd
from django_tenants.utils import schema_context

from api.models import Provider
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
        self.account = "org1234567"
        self.s3_path = "/s3/path"
        self.provider_uuid = self.ocp_provider_uuid
        self.start_date = date(2024, 1, 15)
        self.report_type = "pod_usage"
        self.processor = OCPReportParquetProcessor(
            self.manifest_id, self.account, self.s3_path, self.provider_uuid, self.report_type, self.start_date
        )

    def test_ocp_table_name(self):
        """Test the OCP table name generation."""
        self.assertEqual(self.processor._table_name, TRINO_LINE_ITEM_TABLE_MAP[self.report_type])

        s3_path = "/s3/path/daily"
        processor = OCPReportParquetProcessor(
            self.manifest_id, self.account, s3_path, self.provider_uuid, self.report_type, self.start_date
        )
        self.assertEqual(processor._table_name, TRINO_LINE_ITEM_TABLE_DAILY_MAP[self.report_type])

    def test_postgres_summary_table(self):
        """Test that the correct table is returned."""
        self.assertEqual(self.processor.postgres_summary_table, OCPUsageLineItemDailySummary)

    def test_create_bill(self):
        """Test that a bill is created in the Postgres database."""
        cluster_alias_orig = Provider.objects.get(uuid=self.ocp_provider_uuid).name
        cluster_alias_new = "new name"
        bill_date = DateHelper().next_month_start
        start_date = bill_date
        end_date = DateHelper().next_month_end + datetime.timedelta(days=1)
        self.processor.create_bill(bill_date.date())

        with schema_context(self.schema), self.subTest("bill is created with original cluster alias"):
            report_period = OCPUsageReportPeriod.objects.get(
                cluster_id=self.ocp_cluster_id,
                report_period_start=start_date,
                report_period_end=end_date,
                provider=self.ocp_provider_uuid,
            )
            self.assertIsNotNone(report_period)
            self.assertEqual(report_period.cluster_alias, cluster_alias_orig)

        self.processor.create_bill(bill_date.date())
        with schema_context(self.schema), self.subTest("bill is fetched, and cluster alias did not change"):
            report_period = OCPUsageReportPeriod.objects.get(id=report_period.id)
            self.assertEqual(report_period.cluster_alias, cluster_alias_orig)

        p = Provider.objects.get(uuid=self.ocp_provider_uuid)
        p.name = cluster_alias_new
        p.save()

        self.processor.create_bill(bill_date.date())
        with schema_context(self.schema), self.subTest("bill is fetched, and cluster alias is updated"):
            report_period = OCPUsageReportPeriod.objects.get(id=report_period.id)
            self.assertEqual(report_period.cluster_alias, cluster_alias_new)

    def test_create_bill_with_string_arg(self):
        """Test that a bill is created in the Postgres database."""
        bill_date = DateHelper().next_month_start
        start_date = bill_date
        end_date = DateHelper().next_month_end + datetime.timedelta(days=1)

        self.processor.create_bill(str(bill_date.date()))

        with schema_context(self.schema):
            report_period = OCPUsageReportPeriod.objects.filter(
                cluster_id=self.ocp_cluster_id,
                report_period_start=start_date,
                report_period_end=end_date,
                provider=self.ocp_provider_uuid,
            )
            self.assertIsNotNone(report_period.first())

    def test_gpu_report_type_table_name(self):
        """Test the GPU report type generates correct table names."""
        report_type = "gpu_usage"
        s3_path = "/s3/path"

        processor = OCPReportParquetProcessor(
            self.manifest_id, self.account, s3_path, self.provider_uuid, report_type, self.start_date
        )
        self.assertEqual(processor._table_name, TRINO_LINE_ITEM_TABLE_MAP[report_type])
        self.assertEqual(processor._table_name, "openshift_gpu_usage_line_items")

        # Test daily table name
        s3_path_daily = "/s3/path/daily"
        processor_daily = OCPReportParquetProcessor(
            self.manifest_id, self.account, s3_path_daily, self.provider_uuid, report_type, self.start_date
        )
        self.assertEqual(processor_daily._table_name, TRINO_LINE_ITEM_TABLE_DAILY_MAP[report_type])
        self.assertEqual(processor_daily._table_name, "openshift_gpu_usage_line_items_daily")

    def test_gpu_report_numeric_columns(self):
        """Test that GPU numeric columns are included in the processor."""
        report_type = "gpu_usage"
        processor = OCPReportParquetProcessor(
            self.manifest_id, self.account, self.s3_path, self.provider_uuid, report_type, self.start_date
        )

        # Check that GPU-specific numeric columns are in the column_types
        numeric_columns = processor._column_types["numeric_columns"]
        self.assertIn("gpu_memory_capacity_mib", numeric_columns)
        self.assertIn("gpu_pod_uptime", numeric_columns)

    def test_get_table_names_for_delete(self):
        """Test that both raw and daily table names are returned."""
        table_names = self.processor.get_table_names_for_delete()
        self.assertEqual(len(table_names), 2)
        self.assertIn(TRINO_LINE_ITEM_TABLE_MAP[self.report_type], table_names)
        self.assertIn(TRINO_LINE_ITEM_TABLE_DAILY_MAP[self.report_type], table_names)

    @patch("koku.reportdb_accessor.get_report_db_accessor")
    def test_delete_day_postgres(self, _):
        """Test delete_day_postgres."""
        self.processor.delete_day_postgres(self.start_date, reportnumhours=24)

    @patch("koku.reportdb_accessor.get_report_db_accessor")
    def test_delete_day_postgres_raises_when_data_exists(self, mock_get_accessor):
        """Test delete_day_postgres raises exception when data exists."""
        mock_conn = mock_get_accessor.return_value.connect.return_value.__enter__.return_value
        mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
        mock_cursor.rowcount = 0
        mock_cursor.fetchone.return_value = (1,)
        with self.assertRaises(Exception):
            self.processor.delete_day_postgres(self.start_date, reportnumhours=24)

    @patch("masu.processor.report_parquet_processor_base.ReportParquetProcessorBase.write_dataframe_to_sql")
    def test_write_dataframe_to_sql(self, _):
        """Test write_dataframe_to_sql adds reportnumhours column."""
        data_frame = pd.DataFrame({"col1": [1, 2]})
        metadata = {"ReportNumHours": "24"}
        self.processor.write_dataframe_to_sql(data_frame, metadata)
        self.assertIn("reportnumhours", data_frame.columns)

    @patch("masu.processor.report_parquet_processor_base.ReportParquetProcessorBase._generate_create_table_sql")
    def test_generate_create_table_sql(self, _):
        """Test _generate_create_table_sql appends reportnumhours column."""
        column_names = ["col1", "col2"]
        self.processor._generate_create_table_sql(column_names)
        self.assertIn("reportnumhours", column_names)
