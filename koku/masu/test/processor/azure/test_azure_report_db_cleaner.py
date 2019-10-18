#
# Copyright 2019 Red Hat, Inc.
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

"""Test the AzureReportDBCleaner object."""
import datetime
from dateutil import relativedelta

from tenant_schemas.utils import schema_context

from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.processor.azure.azure_report_db_cleaner import (
    AzureReportDBCleaner,
    AzureReportDBCleanerError
)
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator


class AzureReportDBCleanerTest(MasuTestCase):
    """Test Cases for the AzureReportChargeUpdater object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.common_accessor = ReportingCommonDBAccessor()
        cls.column_map = cls.common_accessor.column_map
        cls.accessor = AzureReportDBAccessor(
            schema=cls.schema, column_map=cls.column_map
        )
        cls.report_schema = cls.accessor.report_schema
        cls.creator = ReportObjectCreator(cls.schema, cls.column_map)
        cls.all_tables = list(AZURE_REPORT_TABLE_MAP.values())
        cls.foreign_key_tables = [
            AZURE_REPORT_TABLE_MAP['bill'],
            AZURE_REPORT_TABLE_MAP['product'],
            AZURE_REPORT_TABLE_MAP['meter'],
        ]

    def setUp(self):
        """"Set up a test with database objects."""
        super().setUp()
        bill_id = self.creator.create_azure_cost_entry_bill(provider_id=self.azure_provider_id)
        product_id = self.creator.create_azure_cost_entry_product()
        meter_id = self.creator.create_azure_meter()
        self.creator.create_azure_cost_entry_line_item(
            bill_id, product_id, meter_id
        )

    def test_initializer(self):
        """Test initializer."""
        self.assertIsNotNone(self.report_schema)

    def test_purge_expired_report_data_on_date(self):
        """Test to remove report data on a provided date."""
        bill_table_name = AZURE_REPORT_TABLE_MAP['bill']
        line_item_table_name = AZURE_REPORT_TABLE_MAP['line_item']

        cleaner = AzureReportDBCleaner(self.schema)
        with schema_context(self.schema):
            # Verify that data is cleared for a cutoff date == billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
            cutoff_date = first_bill.billing_period_start

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(
                self.accessor._get_db_obj_query(line_item_table_name).first()
            )

        removed_data = cleaner.purge_expired_report_data(cutoff_date)

        self.assertEqual(len(removed_data), 1)
        self.assertEqual(
            removed_data[0].get('provider_id'), first_bill.provider_id
        )
        self.assertEqual(
            removed_data[0].get('billing_period_start'),
            str(first_bill.billing_period_start),
        )

        with schema_context(self.schema):
            self.assertIsNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNone(self.accessor._get_db_obj_query(line_item_table_name).first())

