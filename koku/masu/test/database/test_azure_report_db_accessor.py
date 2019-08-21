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

"""Test the AzureReportDBAccessor utility object."""
from tenant_schemas.utils import schema_context

from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.test import MasuTestCase
from masu.test.database.helpers import (
    ReportObjectCreator,
    map_django_field_type_to_python_type,
)


class AzureReportDBAccessorTest(MasuTestCase):
    """Test Cases for the AzureReportDBAccessor object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()

        cls.common_accessor = ReportingCommonDBAccessor()
        cls.column_map = cls.common_accessor.column_map
        cls.accessor = AzureReportDBAccessor(schema=cls.schema, column_map=cls.column_map)
        cls.report_schema = cls.accessor.report_schema
        cls.creator = ReportObjectCreator(cls.schema, cls.column_map)

        cls.all_tables = list(AZURE_REPORT_TABLE_MAP.values())
        cls.foreign_key_tables = [
            AZURE_REPORT_TABLE_MAP['bill'],
            AZURE_REPORT_TABLE_MAP['product'],
            AZURE_REPORT_TABLE_MAP['meter'],
            AZURE_REPORT_TABLE_MAP['service'],
        ]
        cls.manifest_accessor = ReportManifestDBAccessor()

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()
        today = DateAccessor().today_with_timezone('UTC')
        billing_start = today.replace(day=1)

        self.manifest_dict = {
            'assembly_id': '1234',
            'billing_period_start_datetime': billing_start,
            'num_total_files': 2,
            'provider_id': self.azure_provider_id,
        }

        bill = self.creator.create_azure_cost_entry_bill(
            provider_id=self.azure_provider.id,
            bill_date=today,
        )
        product = self.creator.create_azure_cost_entry_product()
        meter = self.creator.create_azure_meter()
        service = self.creator.create_azure_service()
        self.creator.create_azure_cost_entry_line_item(bill, product, meter, service)
        self.manifest = self.manifest_accessor.add(**self.manifest_dict)

    def tearDown(self):
        """Close the DB session."""
        super().tearDown()
        self.accessor.close_connections()

    def test_get_cost_entry_bills(self):
        """Test that Azure bills are returned in a dict."""
        table_name = AZURE_REPORT_TABLE_MAP['bill']
        with schema_context(self.schema):
            bill = self.accessor._get_db_obj_query(table_name).first()
            expected_key = (
                bill.subscription_guid,
                bill.billing_period_start,
                bill.provider_id,
            )
            bill_map = self.accessor.get_cost_entry_bills()
            self.assertIn(expected_key, bill_map)
            self.assertEqual(bill_map[expected_key], bill.id)

    def test_get_products(self):
        """Test that a dict of Azure products are returned."""
        table_name = AZURE_REPORT_TABLE_MAP['product']
        query = self.accessor._get_db_obj_query(table_name)
        with schema_context(self.schema):
            count = query.count()
            first_entry = query.first()
            products = self.accessor.get_products()

            self.assertIsInstance(products, dict)
            self.assertEqual(len(products.keys()), count)
            expected_key = first_entry.instance_id
            self.assertIn(expected_key, products)

    def test_get_meters(self):
        """Test that a dict of Azure meters are returned."""
        table_name = AZURE_REPORT_TABLE_MAP['meter']
        query = self.accessor._get_db_obj_query(table_name)
        with schema_context(self.schema):
            count = query.count()
            first_entry = query.first()
            meters = self.accessor.get_meters()

            self.assertIsInstance(meters, dict)
            self.assertEqual(len(meters.keys()), count)
            expected_key = first_entry.meter_id
            self.assertIn(expected_key, meters)

    def test_get_services(self):
        """Test that a dict of Azure services are returned."""
        table_name = AZURE_REPORT_TABLE_MAP['service']
        query = self.accessor._get_db_obj_query(table_name)
        with schema_context(self.schema):
            count = query.count()
            first_entry = query.first()
            services = self.accessor.get_services()

            self.assertIsInstance(services, dict)
            self.assertEqual(len(services.keys()), count)
            expected_key = (first_entry.service_tier, first_entry.service_name)
            self.assertIn(expected_key, services)
