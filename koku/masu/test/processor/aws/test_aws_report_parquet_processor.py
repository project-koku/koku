#
# Copyright 2020 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Test the AWSReportParquetProcessor."""
from unittest.mock import patch

from tenant_schemas.utils import schema_context

from api.utils import DateHelper
from masu.processor.aws.aws_report_parquet_processor import AWSReportParquetProcessor
from masu.test import MasuTestCase
from reporting.models import PartitionedTable
from reporting.provider.aws.models import AWSCostEntryBill
from reporting.provider.aws.models import AWSCostEntryLineItemDailySummary
from reporting.provider.aws.models import PRESTO_LINE_ITEM_TABLE


class AWSReportProcessorParquetTest(MasuTestCase):
    """Test cases for the AWSReportParquetProcessor."""

    def setUp(self):
        """Setup up shared variables."""
        super().setUp()

        self.manifest_id = 1
        self.account = 10001
        self.s3_path = "/s3/path"
        self.local_parquet = "/local/path"
        self.processor = AWSReportParquetProcessor(
            self.manifest_id, self.account, self.s3_path, self.aws_provider_uuid, self.local_parquet
        )

    def test_aws_table_name(self):
        """Test the AWS table name generation."""
        self.assertEqual(self.processor._table_name, PRESTO_LINE_ITEM_TABLE)

    def test_postgres_summary_table(self):
        """Test that the correct table is returned."""
        self.assertEqual(self.processor.postgres_summary_table, AWSCostEntryLineItemDailySummary)

    @patch("masu.processor.aws.aws_report_parquet_processor.AWSReportParquetProcessor._execute_sql")
    def test_create_bill(self, mock_execute_sql):
        """Test that a bill is created in the Postgres database."""
        bill_date = DateHelper().this_month_start
        start_date = bill_date
        end_date = DateHelper().this_month_end
        account_id = "9999999999"
        mock_execute_sql.return_value = [[account_id]]

        self.processor.create_bill(bill_date.date())
        with schema_context(self.schema):
            bill = AWSCostEntryBill.objects.filter(
                billing_period_start=start_date,
                billing_period_end=end_date,
                payer_account_id=account_id,
                provider=self.aws_provider,
            )
            self.assertIsNotNone(bill.first())

    @patch("masu.processor.aws.aws_report_parquet_processor.AWSReportParquetProcessor._execute_sql")
    def test_create_bill_with_string_arg(self, mock_execute_sql):
        """Test that a bill is created in the Postgres database."""
        bill_date = DateHelper().this_month_start
        start_date = bill_date
        end_date = DateHelper().this_month_end
        account_id = "9999999999"
        mock_execute_sql.return_value = [[account_id]]

        self.processor.create_bill(str(bill_date.date()))
        with schema_context(self.schema):
            bill = AWSCostEntryBill.objects.filter(
                billing_period_start=start_date,
                billing_period_end=end_date,
                payer_account_id=account_id,
                provider=self.aws_provider,
            )
            self.assertIsNotNone(bill.first())

    def test_get_or_create_postgres_partition(self):
        """Test that a Postgres daily summary partition is created."""
        bill_date = DateHelper().next_month_start
        pg_table = self.processor.postgres_summary_table._meta.db_table
        table_name = f"{pg_table}_{bill_date.strftime('%Y_%m')}"
        expected_log = (
            f"INFO:masu.processor.report_parquet_processor_base:"
            f"Created a new parttiion for {pg_table} : {table_name}"
        )

        with self.assertLogs("masu.processor.report_parquet_processor_base", level="INFO") as logger:
            self.processor.get_or_create_postgres_partition(bill_date)
            self.assertIn(expected_log, logger.output)

        with schema_context(self.schema):
            self.assertNotEqual(PartitionedTable.objects.filter(table_name=table_name).count(), 0)
