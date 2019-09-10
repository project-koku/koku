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

"""Test the CostModelDBAccessor utility object."""
from tenant_schemas.utils import schema_context

from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator


class CostModelDBAccessorTest(MasuTestCase):
    """Test Cases for the CostModelDBAccessor object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.provider_uuid = '3c6e687e-1a09-4a05-970c-2ccf44b0952e'
        cls.common_accessor = ReportingCommonDBAccessor()
        cls.column_map = cls.common_accessor.column_map
        cls.accessor = CostModelDBAccessor(
            schema='acct10001',
            provider_uuid=cls.provider_uuid,
            column_map=cls.column_map
        )
        cls.report_schema = cls.accessor.report_schema
        cls.creator = ReportObjectCreator(cls.schema, cls.column_map)
        cls.all_tables = list(OCP_REPORT_TABLE_MAP.values())

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()

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

        markup = {'value': 10, 'unit': 'percent'}

        self.creator.create_cost_model(self.provider_uuid, 'OCP', rates, markup)
        # Reset the rate map and markups in the accessor
        self.accessor.rates = self.accessor._make_rate_by_metric_map()
        self.accessor.markup = self.accessor._get_markup()

    def test_initializer(self):
        """Test initializer."""
        self.assertIsNotNone(self.report_schema)

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
        rates = self.accessor._get_base_entry('rates')
        expected_map = {}
        for rate in rates:
            expected_map[rate.get('metric', {}).get('name')] = rate

        result_rate_map = self.accessor._make_rate_by_metric_map()
        for metric, rate in result_rate_map.items():
            self.assertIn(rate, rates)
            self.assertIn(rate, expected_map.values())
            self.assertIn(metric, expected_map)

    def test_get_not_emtpy_markup(self):
        markup = self.accessor._get_base_entry('markup')
        self.assertEqual(self.accessor._get_markup(), markup)

    def test_get_emtpy_markup(self):
        self.creator.create_cost_model(self.provider_uuid, 'OCP', [], {})
        self.assertEqual(self.accessor._get_markup(), {})
