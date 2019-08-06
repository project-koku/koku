#
# Copyright 2018 Red Hat, Inc.
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

"""Test the OCPRateDBAccessor utility object."""
from tenant_schemas.utils import schema_context

from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_rate_db_accessor import OCPRateDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator


class OCPRateDBAccessorTest(MasuTestCase):
    """Test Cases for the OCPRateDBAccessor object."""

    def run(self, result=None):
        """Run the tests with the correct schema context."""
        with schema_context(self.schema):
            super().run(result)

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.provider_uuid = '3c6e687e-1a09-4a05-970c-2ccf44b0952e'
        cls.common_accessor = ReportingCommonDBAccessor()
        cls.column_map = cls.common_accessor.column_map
        cls.accessor = OCPRateDBAccessor(
            schema='acct10001',
            provider_uuid=cls.provider_uuid,
            column_map=cls.column_map
        )
        cls.report_schema = cls.accessor.report_schema
        cls.creator = ReportObjectCreator(
            cls.accessor, cls.column_map, cls.report_schema.column_types
        )
        cls.all_tables = list(OCP_REPORT_TABLE_MAP.values())

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()
        if self.accessor._cursor.closed:
            self.accessor._cursor = self.accessor._get_psycopg2_cursor()

        reporting_period = self.creator.create_ocp_report_period()
        report = self.creator.create_ocp_report(reporting_period)
        self.creator.create_ocp_usage_line_item(
            reporting_period,
            report
        )
        rates = [
            {'metric': {'name': 'cpu_core_usage_per_hour'},
             'tiered_rates': [{'value': 1.5, 'unit': 'USD'}]},
            {'metric': {'name': 'memory_gb_usage_per_hour'},
             'tiered_rates': [{'value': 2.5, 'unit': 'USD'}]},
            {'metric': {'name': 'cpu_core_request_per_hour'},
             'tiered_rates': [{'value': 3.5, 'unit': 'USD'}]},
            {'metric': {'name': 'memory_gb_request_per_hour'},
             'tiered_rates': [{'value': 4.5, 'unit': 'USD'}]},
            {'metric': {'name': 'storage_gb_usage_per_month'},
             'tiered_rates': [{'value': 5.5, 'unit': 'USD'}]},
            {'metric': {'name': 'storage_gb_request_per_month'},
             'tiered_rates': [{'value': 6.5, 'unit': 'USD'}]}
        ]

        self.creator.create_cost_model(self.provider_uuid, 'OCP', rates)
        # Reset the rate map in the accessor
        self.accessor.rates = self.accessor._make_rate_by_metric_map()

    def tearDown(self):
        """Return the database to a pre-test state."""
        #TODO figure out what's needed here now that we don't have a session
        pass
        # self.accessor._session.rollback()

        # for table_name in self.all_tables:
        #     tables = self.accessor._get_db_obj_query(table_name).all()
        #     for table in tables:
        #         self.accessor._session.delete(table)
        # self.accessor.commit()

    def test_initializer(self):
        """Test initializer."""
        self.assertIsNotNone(self.report_schema)
        self.assertIsNotNone(self.accessor._cursor)

    def test_get_rates(self):
        """Test get rates."""
        cpu_usage_rate = self.accessor.get_rates('cpu_core_usage_per_hour')
        self.assertEqual(type(cpu_usage_rate), dict)

        mem_usage_rate = self.accessor.get_rates('memory_gb_usage_per_hour')
        self.assertEqual(type(mem_usage_rate), dict)

        cpu_request_rate = self.accessor.get_rates('cpu_core_request_per_hour')
        self.assertEqual(type(cpu_request_rate), dict)

        mem_request_rate = self.accessor.get_rates('memory_gb_request_per_hour')
        self.assertEqual(type(mem_request_rate), dict)

        storage_usage_rate = self.accessor.get_rates('storage_gb_usage_per_month')
        self.assertEqual(type(storage_usage_rate), dict)

        storage_request_rate = self.accessor.get_rates('storage_gb_request_per_month')
        self.assertEqual(type(storage_request_rate), dict)

        missing_rate = self.accessor.get_rates('wrong_metric')
        self.assertIsNone(missing_rate)

    def test_get_cpu_core_usage_per_hour_rates(self):
        """Test get cpu usage rates."""
        cpu_rates = self.accessor.get_cpu_core_usage_per_hour_rates()
        self.assertEqual(type(cpu_rates), dict)
        self.assertEqual(cpu_rates.get('tiered_rates')[0].get('value'), 1.5)

    def test_get_memory_gb_usage_per_hour_rates(self):
        """Test get memory usage rates."""
        mem_rates = self.accessor.get_memory_gb_usage_per_hour_rates()
        self.assertEqual(type(mem_rates), dict)
        self.assertEqual(mem_rates.get('tiered_rates')[0].get('value'), 2.5)

    def test_get_cpu_core_request_per_hour_rates(self):
        """Test get cpu request rates."""
        cpu_rates = self.accessor.get_cpu_core_request_per_hour_rates()
        self.assertEqual(type(cpu_rates), dict)
        self.assertEqual(cpu_rates.get('tiered_rates')[0].get('value'), 3.5)

    def test_get_memory_gb_request_per_hour_rates(self):
        """Test get memory request rates."""
        mem_rates = self.accessor.get_memory_gb_request_per_hour_rates()
        self.assertEqual(type(mem_rates), dict)
        self.assertEqual(mem_rates.get('tiered_rates')[0].get('value'), 4.5)

    def test_get_storage_gb_usage_per_month_rates(self):
        """Test get memory request rates."""
        storage_rates = self.accessor.get_storage_gb_usage_per_month_rates()
        self.assertEqual(type(storage_rates), dict)
        self.assertEqual(storage_rates.get('tiered_rates')[0].get('value'), 5.5)

    def test_get_storage_gb_request_per_month_rates(self):
        """Test get memory request rates."""
        storage_rates = self.accessor.get_storage_gb_request_per_month_rates()
        self.assertEqual(type(storage_rates), dict)
        self.assertEqual(storage_rates.get('tiered_rates')[0].get('value'), 6.5)

    def test_make_rate_by_metric_map(self):
        """Test to make sure a dictionary of metric to rates is returned."""
        rates = self.accessor._get_base_entry()
        expected_map = {}
        for rate in rates:
            expected_map[rate.get('metric', {}).get('name')] = rate

        result_rate_map = self.accessor._make_rate_by_metric_map()
        for metric, rate in result_rate_map.items():
            self.assertIn(rate, rates)
            self.assertIn(rate, expected_map.values())
            self.assertIn(metric, expected_map)
