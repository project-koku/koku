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

    def test_update_daily_tables(self):
        """Test process method."""
        import pdb; pdb.set_trace()
        self.updater.update_daily_tables(None, None)

    def test_update_summary_tables(self):
        """Test verify temporary files are removed."""
        self.updater.update_summary_tables(None, None)
