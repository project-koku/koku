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

"""Test the AzureReportSummaryUpdater object."""
import calendar
import datetime
from unittest.mock import patch

from tenant_schemas.utils import schema_context

from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.processor.azure.azure_report_summary_updater import AzureReportSummaryUpdater
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator


class AzureReportSummaryUpdaterTest(MasuTestCase):
    """Test Cases for the AzureReportSummaryUpdater object."""
    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        with ReportingCommonDBAccessor() as report_common_db:
            cls.column_map = report_common_db.column_map

        cls.accessor = AzureReportDBAccessor('acct10001', cls.column_map)
        cls.report_schema = cls.accessor.report_schema
        cls.all_tables = list(AZURE_REPORT_TABLE_MAP.values())
        cls.creator = ReportObjectCreator(cls.schema, cls.column_map)
        cls.date_accessor = DateAccessor()
        cls.manifest_accessor = ReportManifestDBAccessor()

    def setUp(self):
        """Set up each test."""
        super().setUp()

        billing_start = self.date_accessor.today_with_timezone('UTC').replace(day=1)
        self.manifest_dict = {
            'assembly_id': '1234',
            'billing_period_start_datetime': billing_start,
            'num_total_files': 2,
            'provider_id': self.azure_provider.id,
        }

        today = DateAccessor().today_with_timezone('UTC')
        bill = self.creator.create_azure_cost_entry_bill(provider_id=self.azure_provider_id, bill_date=today)
        product = self.creator.create_azure_cost_entry_product()
        meter = self.creator.create_azure_meter()
        service = self.creator.create_azure_service()
        self.creator.create_azure_cost_entry_line_item(bill, product, meter, service)

        self.manifest = self.manifest_accessor.add(**self.manifest_dict)
        self.manifest_accessor.commit()

        with ProviderDBAccessor(self.azure_test_provider_uuid) as provider_accessor:
            self.provider = provider_accessor.get_provider()

        self.updater = AzureReportSummaryUpdater(
           self.schema, self.azure_provider, self.manifest
        )


    @patch('masu.processor.azure.azure_report_summary_updater.AzureReportDBAccessor.populate_line_item_daily_summary_table')
    def test_azure_update_summary_tables_with_manifest(self, mock_summary):
        """Test that summary tables are properly run."""
        self.manifest.num_processed_files = self.manifest.num_total_files
        self.manifest_accessor.commit()

        start_date = self.date_accessor.today_with_timezone('UTC')
        end_date = start_date + datetime.timedelta(days=1)
        bill_date = start_date.replace(day=1).date()

        with AzureReportDBAccessor(self.schema, self.column_map) as accessor:
            bill = accessor.get_cost_entry_bills_by_date(bill_date)[0]
            bill.summary_data_creation_datetime = start_date
            bill.save()

        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')

        expected_start_date = start_date.strftime('%Y-%m-%d')
        expected_end_date = end_date.strftime('%Y-%m-%d')

        self.assertIsNone(bill.summary_data_updated_datetime)

        self.updater.update_daily_tables(start_date_str, end_date_str)
        mock_summary.assert_not_called()

        self.updater.update_summary_tables(start_date_str, end_date_str)
        mock_summary.assert_called_with(
            expected_start_date, expected_end_date, [str(bill.id)]
        )

        with AzureReportDBAccessor(self.schema, self.column_map) as accessor:
            bill = accessor.get_cost_entry_bills_by_date(bill_date)[0]
            self.assertIsNotNone(bill.summary_data_creation_datetime)
            self.assertIsNotNone(bill.summary_data_updated_datetime)

    @patch('masu.processor.azure.azure_report_summary_updater.AzureReportDBAccessor.populate_line_item_daily_summary_table')
    def test_azure_update_summary_tables_new_bill(self, mock_summary):
        """Test that summary tables are run for a full month."""

        self.manifest.num_processed_files = self.manifest.num_total_files
        manifest_id = self.manifest.id
        self.manifest_accessor.commit()

        start_date = self.date_accessor.today_with_timezone('UTC')
        end_date = start_date
        bill_date = start_date.replace(day=1).date()
        with schema_context(self.schema):
            bill = self.accessor.get_cost_entry_bills_by_date(bill_date)[0]

        last_day_of_month = calendar.monthrange(bill_date.year, bill_date.month)[1]

        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')

        expected_start_date = start_date.replace(day=1).strftime('%Y-%m-%d')
        expected_end_date = end_date.replace(day=last_day_of_month).strftime('%Y-%m-%d')

        self.assertIsNone(bill.summary_data_creation_datetime)
        self.assertIsNone(bill.summary_data_updated_datetime)

        self.updater.update_daily_tables(start_date_str, end_date_str)
        mock_summary.assert_not_called()

        self.updater.update_summary_tables(start_date_str, end_date_str)
        mock_summary.assert_called_with(
            expected_start_date, expected_end_date, [str(bill.id)]
        )

        with AzureReportDBAccessor(self.schema, self.column_map) as accessor:
            bill = accessor.get_cost_entry_bills_by_date(bill_date)[0]
            self.assertIsNotNone(bill.summary_data_creation_datetime)
            self.assertIsNotNone(bill.summary_data_updated_datetime)