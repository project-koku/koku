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
"""Test the AzureReportParquetProcessor."""
from tenant_schemas.utils import schema_context

from api.utils import DateHelper
from masu.processor.azure.azure_report_parquet_processor import AzureReportParquetProcessor
from masu.test import MasuTestCase
from reporting.provider.azure.models import AzureCostEntryBill
from reporting.provider.azure.models import PRESTO_LINE_ITEM_TABLE


class AzureReportParquetProcessorTest(MasuTestCase):
    """Test cases for the AzureReportParquetProcessor."""

    def setUp(self):
        """Setup up shared variables."""
        super().setUp()

        self.manifest_id = 1
        self.account = 10001
        self.s3_path = "/s3/path"
        self.provider_uuid = self.azure_provider_uuid
        self.local_parquet = "/local/path"
        self.processor = AzureReportParquetProcessor(
            self.manifest_id, self.account, self.s3_path, self.provider_uuid, self.local_parquet
        )

    def test_azure_table_name(self):
        """Test the Azure table name generation."""
        self.assertEqual(self.processor._table_name, PRESTO_LINE_ITEM_TABLE)

    def test_create_bill(self):
        """Test that a bill is created in the Postgres database."""
        bill_date = DateHelper().this_month_start
        start_date = bill_date
        end_date = DateHelper().this_month_end

        self.processor.create_bill(bill_date.date())

        with schema_context(self.schema):
            bill = AzureCostEntryBill.objects.filter(
                billing_period_start=start_date, billing_period_end=end_date, provider=self.azure_provider_uuid
            )
            self.assertIsNotNone(bill.first())
