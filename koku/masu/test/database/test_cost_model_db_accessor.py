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

from api.models import Provider
from cost_models.models import CostModel
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator


class CostModelDBAccessorTest(MasuTestCase):
    """Test Cases for the CostModelDBAccessor object."""

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()
        self.provider_uuid = '3c6e687e-1a09-4a05-970c-2ccf44b0952e'
        self.schema = 'acct10001'
        self.column_map = ReportingCommonDBAccessor().column_map
        self.creator = ReportObjectCreator(self.schema, self.column_map)

        reporting_period = self.creator.create_ocp_report_period(provider_uuid=self.provider_uuid)
        report = self.creator.create_ocp_report(reporting_period)
        self.creator.create_ocp_usage_line_item(reporting_period, report)
        self.rates = [
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
             'tiered_rates': [{'value': 6.5, 'unit': 'USD'}]},
            {'metric': {'name': 'node_cost_per_month'},
             'tiered_rates': [{'value': 7.5, 'unit': 'USD'}]}
        ]

        self.markup = {'value': 10, 'unit': 'percent'}

        self.cost_model = self.creator.create_cost_model(
            self.provider_uuid, Provider.PROVIDER_OCP, self.rates, self.markup
        )

    def test_initializer(self):
        """Test initializer."""
        with CostModelDBAccessor(
            self.schema, self.provider_uuid, self.column_map
        ) as cost_model_accessor:
            self.assertIsNotNone(cost_model_accessor.report_schema)

    def test_get_rates(self):
        """Test get rates."""
        with CostModelDBAccessor(
            self.schema, self.provider_uuid, self.column_map
        ) as cost_model_accessor:
            cpu_usage_rate = cost_model_accessor.get_rates('cpu_core_usage_per_hour')
            self.assertEqual(type(cpu_usage_rate), dict)

            mem_usage_rate = cost_model_accessor.get_rates('memory_gb_usage_per_hour')
            self.assertEqual(type(mem_usage_rate), dict)

            cpu_request_rate = cost_model_accessor.get_rates('cpu_core_request_per_hour')
            self.assertEqual(type(cpu_request_rate), dict)

            mem_request_rate = cost_model_accessor.get_rates('memory_gb_request_per_hour')
            self.assertEqual(type(mem_request_rate), dict)

            storage_usage_rate = cost_model_accessor.get_rates('storage_gb_usage_per_month')
            self.assertEqual(type(storage_usage_rate), dict)

            storage_request_rate = cost_model_accessor.get_rates('storage_gb_request_per_month')
            self.assertEqual(type(storage_request_rate), dict)

            storage_request_rate = cost_model_accessor.get_rates('node_cost_per_month')
            self.assertEqual(type(storage_request_rate), dict)

            missing_rate = cost_model_accessor.get_rates('wrong_metric')
            self.assertIsNone(missing_rate)

    def test_get_cpu_core_usage_per_hour_rates(self):
        """Test get cpu usage rates."""
        with CostModelDBAccessor(
            self.schema, self.provider_uuid, self.column_map
        ) as cost_model_accessor:
            cpu_rates = cost_model_accessor.get_cpu_core_usage_per_hour_rates()
            self.assertEqual(type(cpu_rates), dict)
            self.assertEqual(cpu_rates.get('tiered_rates')[0].get('value'), 1.5)

    def test_get_memory_gb_usage_per_hour_rates(self):
        """Test get memory usage rates."""
        with CostModelDBAccessor(
            self.schema, self.provider_uuid, self.column_map
        ) as cost_model_accessor:
            mem_rates = cost_model_accessor.get_memory_gb_usage_per_hour_rates()
            self.assertEqual(type(mem_rates), dict)
            self.assertEqual(mem_rates.get('tiered_rates')[0].get('value'), 2.5)

    def test_get_cpu_core_request_per_hour_rates(self):
        """Test get cpu request rates."""
        with CostModelDBAccessor(
            self.schema, self.provider_uuid, self.column_map
        ) as cost_model_accessor:
            cpu_rates = cost_model_accessor.get_cpu_core_request_per_hour_rates()
            self.assertEqual(type(cpu_rates), dict)
            self.assertEqual(cpu_rates.get('tiered_rates')[0].get('value'), 3.5)

    def test_get_memory_gb_request_per_hour_rates(self):
        """Test get memory request rates."""
        with CostModelDBAccessor(
            self.schema, self.provider_uuid, self.column_map
        ) as cost_model_accessor:
            mem_rates = cost_model_accessor.get_memory_gb_request_per_hour_rates()
            self.assertEqual(type(mem_rates), dict)
            self.assertEqual(mem_rates.get('tiered_rates')[0].get('value'), 4.5)

    def test_get_storage_gb_usage_per_month_rates(self):
        """Test get memory request rates."""
        with CostModelDBAccessor(
            self.schema, self.provider_uuid, self.column_map
        ) as cost_model_accessor:
            storage_rates = cost_model_accessor.get_storage_gb_usage_per_month_rates()
            self.assertEqual(type(storage_rates), dict)
            self.assertEqual(storage_rates.get('tiered_rates')[0].get('value'), 5.5)

    def test_get_storage_gb_request_per_month_rates(self):
        """Test get memory request rates."""
        with CostModelDBAccessor(
            self.schema, self.provider_uuid, self.column_map
        ) as cost_model_accessor:
            storage_rates = cost_model_accessor.get_storage_gb_request_per_month_rates()
            self.assertEqual(type(storage_rates), dict)
            self.assertEqual(storage_rates.get('tiered_rates')[0].get('value'), 6.5)

    def test_make_rate_by_metric_map(self):
        """Test to make sure a dictionary of metric to rates is returned."""
        expected_map = {}
        for rate in self.rates:
            expected_map[rate.get('metric', {}).get('name')] = rate

        with CostModelDBAccessor(
            self.schema, self.provider_uuid, self.column_map
        ) as cost_model_accessor:
            result_rate_map = cost_model_accessor._make_rate_by_metric_map()
            for metric, rate in result_rate_map.items():
                self.assertIn(rate, self.rates)
                self.assertIn(rate, expected_map.values())
                self.assertIn(metric, expected_map)

    def test_get_markup(self):
        """Test to make sure markup dictionary is returned."""
        with CostModelDBAccessor(
            self.schema, self.provider_uuid, self.column_map
        ) as cost_model_accessor:
            markup = cost_model_accessor.get_markup()
            self.assertEqual(markup, self.markup)
            markup = cost_model_accessor.get_markup()
            self.assertEqual(markup, self.markup)

    def test_get_cost_model(self):
        """Test to make sure cost_model is gotten."""
        with schema_context(self.schema):
            model = CostModel.objects.filter(costmodelmap__provider_uuid=self.provider_uuid).first()
        with CostModelDBAccessor(
            self.schema, self.provider_uuid, self.column_map
        ) as cost_model_accessor:
            self.assertEqual(cost_model_accessor._get_cost_model(), model)
            uuid = cost_model_accessor._get_cost_model().uuid
            self.assertEqual(cost_model_accessor._get_cost_model().uuid, uuid)

    def test_get_node_cost_per_month(self):
        """Test get memory request rates."""
        with CostModelDBAccessor(self.schema, self.provider_uuid,
                                 self.column_map) as cost_model_accessor:
            node_cost = cost_model_accessor.get_node_per_month_rates()
            self.assertEqual(type(node_cost), dict)
            self.assertEqual(node_cost.get('tiered_rates')[0].get('value'), 7.5)


class CostModelDBAccessorTestNoRateOrMarkup(MasuTestCase):
    """Test Cases for the CostModelDBAccessor object."""

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()
        self.provider_uuid = '3c6e687e-1a09-4a05-970c-2ccf44b0952e'
        self.schema = 'acct10001'
        self.column_map = ReportingCommonDBAccessor().column_map
        self.creator = ReportObjectCreator(self.schema, self.column_map)

        reporting_period = self.creator.create_ocp_report_period(self.ocp_provider_uuid)
        report = self.creator.create_ocp_report(reporting_period)
        self.creator.create_ocp_usage_line_item(reporting_period, report)

        self.cost_model = self.creator.create_cost_model(
            self.provider_uuid, Provider.PROVIDER_OCP)

    def test_initializer_no_rate_no_markup(self):
        """Test initializer."""
        with CostModelDBAccessor(
            self.schema, self.provider_uuid, self.column_map
        ) as cost_model_accessor:
            self.assertIsNotNone(cost_model_accessor.report_schema)

    def test_get_rates(self):
        """Test get rates."""
        with CostModelDBAccessor(
            self.schema, self.provider_uuid, self.column_map
        ) as cost_model_accessor:
            cpu_usage_rate = cost_model_accessor.get_rates('cpu_core_usage_per_hour')
            self.assertIsNone(cpu_usage_rate)


class CostModelDBAccessorNoCostModel(MasuTestCase):
    """Test Cases for the CostModelDBAccessor object."""

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()
        self.provider_uuid = '3c6e687e-1a09-4a05-970c-2ccf44b0952e'
        self.schema = 'acct10001'
        self.column_map = ReportingCommonDBAccessor().column_map

    def test_get_rates_no_cost_model(self):
        """Test that get_rates returns empty dict when cost model does not exist."""
        with CostModelDBAccessor(
            self.schema, self.provider_uuid, self.column_map
        ) as cost_model_accessor:
            cpu_usage_rate = cost_model_accessor.get_rates('cpu_core_usage_per_hour')
            self.assertFalse(cpu_usage_rate)

    def test_get_markup_no_cost_model(self):
        """Test that get_markup returns empty dict when cost model does not exist."""
        with CostModelDBAccessor(
            self.schema, self.provider_uuid, self.column_map
        ) as cost_model_accessor:
            markup = cost_model_accessor.get_markup()
            self.assertFalse(markup)
