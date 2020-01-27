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

"""Test the OCPReportDBAccessor utility object."""
import random
import string
from decimal import Decimal
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from tenant_schemas.utils import schema_context

from api.models import Provider
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.processor.ocp.ocp_report_charge_updater import (
    OCPReportChargeUpdater,
    OCPReportChargeUpdaterError,
)
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary


class OCPReportChargeUpdaterTest(MasuTestCase):
    """Test Cases for the OCPReportChargeUpdater object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.common_accessor = ReportingCommonDBAccessor()
        cls.column_map = cls.common_accessor.column_map
        cls.ocp_provider_uuid = '3c6e687e-1a09-4a05-970c-2ccf44b0952e'
        cls.accessor = OCPReportDBAccessor(schema='acct10001', column_map=cls.column_map)
        cls.report_schema = cls.accessor.report_schema
        cls.creator = ReportObjectCreator(cls.schema, cls.column_map)
        cls.all_tables = list(OCP_REPORT_TABLE_MAP.values())

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()
        with ProviderDBAccessor(self.ocp_provider_uuid) as provider_accessor:
            self.provider = provider_accessor.get_provider()

        self.cluster_id = self.ocp_provider_resource_name

        reporting_period = self.creator.create_ocp_report_period(
            provider_uuid=self.provider.uuid, cluster_id=self.cluster_id
        )

        report = self.creator.create_ocp_report(
            reporting_period, reporting_period.report_period_start
        )
        self.updater = OCPReportChargeUpdater(schema=self.schema, provider=self.provider)
        pod = ''.join(random.choice(string.ascii_lowercase) for _ in range(10))
        namespace = ''.join(random.choice(string.ascii_lowercase) for _ in range(10))
        self.creator.create_ocp_usage_line_item(
            reporting_period, report, pod=pod, namespace=namespace
        )
        self.creator.create_ocp_storage_line_item(
            reporting_period, report, pod=pod, namespace=namespace
        )
        self.creator.create_ocp_usage_line_item(reporting_period, report, null_cpu_usage=True)

    def test_normalize_tier(self):
        """Test the tier helper function to normalize rate tier."""
        rate_json = [
            {'usage': {'usage_start': '20', 'usage_end': '30'}, 'value': '0.30', 'unit': 'USD'},
            {'usage': {'usage_start': None, 'usage_end': '10'}, 'value': '0.10', 'unit': 'USD'},
            {'usage': {'usage_start': '10', 'usage_end': '20'}, 'value': '0.20', 'unit': 'USD'},
            {'usage': {'usage_start': '30', 'usage_end': None}, 'value': '0.40', 'unit': 'USD'},
        ]
        normalized_tier = self.updater._normalize_tier(rate_json)
        self.assertEqual(len(normalized_tier), len(rate_json))
        self.assertIsNone(normalized_tier[0].get('usage').get('usage_start'))
        self.assertGreater(
            normalized_tier[1].get('usage').get('usage_end'),
            normalized_tier[0].get('usage').get('usage_end'),
        )
        self.assertGreater(
            normalized_tier[2].get('usage').get('usage_end'),
            normalized_tier[1].get('usage').get('usage_end'),
        )
        self.assertIsNone(normalized_tier[3].get('usage').get('usage_end'))

    def test_normalize_tier_no_start_end_provided(self):
        """Test the tier helper function to normalize rate tier when end points are not provided."""
        rate_json = [
            {'usage': {'usage_start': '20', 'usage_end': '30'}, 'value': '0.30', 'unit': 'USD'},
            {'usage': {'usage_end': '10', 'value': '0.10'}, 'unit': 'USD'},
            {'usage': {'usage_start': '10', 'usage_end': '20'}, 'value': '0.20', 'unit': 'USD'},
            {'usage': {'usage_start': '30'}, 'value': '0.40', 'unit': 'USD'},
        ]
        normalized_tier = self.updater._normalize_tier(rate_json)
        self.assertEqual(len(normalized_tier), len(rate_json))
        self.assertIsNone(normalized_tier[0].get('usage').get('usage_start'))
        self.assertGreater(
            normalized_tier[1].get('usage').get('usage_end'),
            normalized_tier[0].get('usage').get('usage_end'),
        )
        self.assertGreater(
            normalized_tier[2].get('usage').get('usage_end'),
            normalized_tier[1].get('usage').get('usage_end'),
        )
        self.assertIsNone(normalized_tier[3].get('usage').get('usage_end'))

    def test_normalize_tier_missing_first(self):
        """Test the tier helper function when first tier is missing."""
        rate_json = [
            {'usage': {'usage_start': None, 'usage_end': '10'}, 'value': '0.10', 'unit': 'USD'},
            {'usage': {'usage_start': '20', 'usage_end': '30'}, 'value': '0.30', 'unit': 'USD'},
            {'usage': {'usage_start': '10', 'usage_end': '20'}, 'value': '0.20', 'unit': 'USD'},
            {'usage': {'usage_start': '30', 'usage_end': '40'}, 'value': '0.40', 'unit': 'USD'},
        ]
        with self.assertRaises(OCPReportChargeUpdaterError) as error:
            self.updater._normalize_tier(rate_json)
            self.assertIn('Missing first tier', error)

    def test_normalize_tier_two_starts(self):
        """Test the tier helper function when two starting tiers are provided."""
        rate_json = [
            {'usage': {'usage_start': None, 'usage_end': '10'}, 'value': '0.10', 'unit': 'USD'},
            {'usage': {'usage_start': None, 'usage_end': '30'}, 'value': '0.30', 'unit': 'USD'},
            {'usage': {'usage_start': '10', 'usage_end': '20'}, 'value': '0.20', 'unit': 'USD'},
            {'usage': {'usage_start': '30'}, 'value': '0.40', 'unit': 'USD'},
        ]
        with self.assertRaises(OCPReportChargeUpdaterError) as error:
            self.updater._normalize_tier(rate_json)
            self.assertIn('Two starting tiers', error)

    def test_normalize_tier_two_final(self):
        """Test the tier helper function when two final tiers are provided."""
        rate_json = [
            {'usage': {'usage_start': None, 'usage_end': '10'}, 'value': '0.10', 'unit': 'USD'},
            {'usage': {'usage_start': '20', 'usage_end': '30'}, 'value': '0.30', 'unit': 'USD'},
            {'usage': {'usage_start': '10', 'usage_end': None}, 'value': '0.20', 'unit': 'USD'},
            {'usage': {'usage_start': '30'}, 'value': '0.40', 'unit': 'USD'},
        ]
        with self.assertRaises(OCPReportChargeUpdaterError) as error:
            self.updater._normalize_tier(rate_json)
            self.assertIn('Two final tiers', error)

    def test_normalize_tier_missing_last(self):
        """Test the tier helper function when last tier is missing."""
        rate_json = [
            {'usage': {'usage_start': '20', 'usage_end': '30'}, 'value': '0.30', 'unit': 'USD'},
            {'usage': {'usage_start': '10', 'usage_end': '20'}, 'value': '0.20', 'unit': 'USD'},
            {'usage': {'usage_start': '30', 'usage_end': None}, 'value': '0.40', 'unit': 'USD'},
        ]
        with self.assertRaises(OCPReportChargeUpdaterError) as error:
            self.updater._normalize_tier(rate_json)
            self.assertIn('Missing final tier', error)

    def test_bucket_applied(self):
        """Test the tier helper function."""
        lower_limit = 0
        upper_limit = 10
        test_matrix = [
            {'usage': -10, 'expected_usage_applied': 0},
            {'usage': 5, 'expected_usage_applied': 5},
            {'usage': 10, 'expected_usage_applied': 10},
            {'usage': 15, 'expected_usage_applied': 10},
        ]

        for test in test_matrix:
            usage_applied = self.updater._bucket_applied(
                test.get('usage'), lower_limit, upper_limit
            )
            self.assertEqual(usage_applied, test.get('expected_usage_applied'))

    def test_aggregate_charges(self):
        """Test the helper function to aggregate usage and request charges."""
        usage_charge = {
            3: {'usage': Decimal('0.000249'), 'charge': Decimal('0.049800')},
            4: {'usage': Decimal('0.05'), 'charge': Decimal('0.10')},
        }
        request_charge = {
            3: {'usage': Decimal('0.000173'), 'charge': Decimal('0.043250')},
            4: {'usage': Decimal('0.06'), 'charge': Decimal('0.20')},
        }

        total_charge = self.updater._aggregate_charges(usage_charge, request_charge)
        for key, charge in total_charge.items():
            usage_charge_value = usage_charge.get(key).get('charge')
            request_charge_value = request_charge.get(key).get('charge')
            total_charge = usage_charge_value + request_charge_value

            self.assertEqual(charge.get('usage_charge'), usage_charge_value)
            self.assertEqual(charge.get('request_charge'), request_charge_value)
            self.assertEqual(charge.get('charge'), total_charge)

    def test_aggregate_charges_extra_usage(self):
        """Test the helper function to aggregate usage and request charges where usage_charge is larger."""
        usage_charge = {
            3: {'usage': Decimal('0.000249'), 'charge': Decimal('0.049800')},
            4: {'usage': Decimal('0.05'), 'charge': Decimal('0.10')},
        }
        request_charge = {3: {'usage': Decimal('0.000173'), 'charge': Decimal('0.043250')}}

        with self.assertRaises(OCPReportChargeUpdaterError):
            self.updater._aggregate_charges(usage_charge, request_charge)

    def test_aggregate_charges_extra_request(self):
        """Test the helper function to aggregate usage and request charges where request_charge is larger."""
        usage_charge = {3: {'usage': Decimal('0.000249'), 'charge': Decimal('0.049800')}}
        request_charge = {
            3: {'usage': Decimal('0.000173'), 'charge': Decimal('0.043250')},
            4: {'usage': Decimal('0.06'), 'charge': Decimal('0.20')},
        }

        with self.assertRaises(OCPReportChargeUpdaterError):
            self.updater._aggregate_charges(usage_charge, request_charge)

    def test_aggregate_charges_mismatched_keys(self):
        """Test the helper function to aggregate usage and request charges where dictionaries have different keys."""
        usage_charge = {
            3: {'usage': Decimal('0.000249'), 'charge': Decimal('0.049800')},
            4: {'usage': Decimal('0.05'), 'charge': Decimal('0.10')},
        }
        request_charge = {
            3: {'usage': Decimal('0.000173'), 'charge': Decimal('0.043250')},
            5: {'usage': Decimal('0.06'), 'charge': Decimal('0.20')},
        }

        with self.assertRaises(OCPReportChargeUpdaterError):
            self.updater._aggregate_charges(usage_charge, request_charge)

    def test_calculate_variable_charge(self):
        """Test the helper function to calculate charge."""
        rate_json = {
            'tiered_rates': [
                {'usage': {'usage_start': None, 'usage_end': '10'}, 'value': '0.10', 'unit': 'USD'},
                {'usage': {'usage_start': '10', 'usage_end': '20'}, 'value': '0.20', 'unit': 'USD'},
                {'usage': {'usage_start': '20', 'usage_end': '30'}, 'value': '0.30', 'unit': 'USD'},
                {'usage': {'usage_start': '30', 'usage_end': None}, 'value': '0.40', 'unit': 'USD'},
            ]
        }
        usage_dictionary = {
            1: Decimal(5),
            2: Decimal(15),
            3: Decimal(25),
            4: Decimal(50),
            5: Decimal(0),
        }

        expected_results = {
            1: Decimal(0.5),  # usage: 5,  charge: 0.5 = 5 * 0.1
            2: Decimal(2.0),  # usage: 15, charge: 2.0 = (10 * 0.1) + (5 * 0.2)
            3: Decimal(4.5),  # usage: 25, charge: 4.5 = (10 * 0.1) + (10 * 0.2) + (5 * 0.3)
            4: Decimal(
                14.0
            ),  # usage: 50, charge: 14.0 = (10 * 0.1) + (10 * 0.2) + (10 * 0.3) + (20 * 0.4)
            5: Decimal(0.0),
        }  # usage: 0, charge: 0

        for key, usage in usage_dictionary.items():
            tier_charge = self.updater._calculate_variable_charge(usage, rate_json)
            self.assertEqual(tier_charge, expected_results.get(key))

    def test_calculate_variable_charge_floating_ends(self):
        """Test the helper function to calculate charge with floating endpoints."""
        rate_json = {
            'tiered_rates': [
                {
                    'usage': {'usage_start': None, 'usage_end': '10.3'},
                    'value': '0.10',
                    'unit': 'USD',
                },
                {
                    'usage': {'usage_start': '10.3', 'usage_end': '19.8'},
                    'value': '0.20',
                    'unit': 'USD',
                },
                {
                    'usage': {'usage_start': '19.8', 'usage_end': '22.6'},
                    'value': '0.30',
                    'unit': 'USD',
                },
                {
                    'usage': {'usage_start': '22.6', 'usage_end': None},
                    'value': '0.40',
                    'unit': 'USD',
                },
            ]
        }

        usage_dictionary = {
            1: Decimal(5),
            2: Decimal(15),
            3: Decimal(25),
            4: Decimal(50),
            5: Decimal(0),
        }

        expected_results = {
            1: Decimal('0.5'),  # usage: 5,  charge: 0.5 = 5 * 0.1
            2: Decimal('1.97'),  # usage: 15, charge: 1.97 = (10.3 * 0.1) + (4.7 * 0.2)
            3: Decimal(
                '4.730'
            ),  # usage: 25, charge: 4.730 = (10.3 * 0.1) + (9.5 * 0.2) + (2.8 * 0.3) + (2.4 * 0.4)
            4: Decimal(
                '14.730'
            ),  # usage: 50, charge: 14.73 = (10.3 * 0.1) + (9.5 * 0.2) + (2.8 * 0.3) + (27.4 * 0.4)
            5: Decimal('0.0'),
        }  # usage: 0, charge: 0

        for key, usage in usage_dictionary.items():
            tier_charge = self.updater._calculate_variable_charge(usage, rate_json)
            self.assertEqual(tier_charge, expected_results.get(key))

    def test_calculate_variable_charge_ends_missing(self):
        """Test the helper function to calculate charge when end limits are missing."""
        rate_json = {
            'tiered_rates': [
                {'usage': {'usage_end': '10'}, 'value': '0.10', 'unit': 'USD'},
                {'usage': {'usage_start': '10', 'usage_end': '20'}, 'value': '0.20', 'unit': 'USD'},
                {'usage': {'usage_start': '20', 'usage_end': '30'}, 'value': '0.30', 'unit': 'USD'},
                {'usage': {'usage_start': '30'}, 'value': '0.40', 'unit': 'USD'},
            ]
        }
        usage_dictionary = {
            1: Decimal(5),
            2: Decimal(15),
            3: Decimal(25),
            4: Decimal(50),
            5: Decimal(0),
        }

        expected_results = {
            1: Decimal(0.5),
            2: Decimal(2.0),
            3: Decimal(4.5),
            4: Decimal(14.0),
            5: Decimal(0.0),
        }

        for key, usage in usage_dictionary.items():
            tier_charge = self.updater._calculate_variable_charge(usage, rate_json)
            self.assertEqual(tier_charge, expected_results.get(key))

    def test_calculate_charge(self):
        """Test the helper function to calculate charge."""
        rate_json = {
            'tiered_rates': [
                {'usage': {'usage_start': None, 'usage_end': '10'}, 'value': '0.10', 'unit': 'USD'},
                {'usage': {'usage_start': '10', 'usage_end': '20'}, 'value': '0.20', 'unit': 'USD'},
                {'usage': {'usage_start': '20', 'usage_end': '30'}, 'value': '0.30', 'unit': 'USD'},
                {'usage': {'usage_start': '30', 'usage_end': None}, 'value': '0.40', 'unit': 'USD'},
            ]
        }
        usage_dictionary = {
            1: Decimal(5),
            2: Decimal(15),
            3: Decimal(25),
        }

        expected_results = {
            1: {'expected_charge': Decimal(0.5)},
            2: {'expected_charge': Decimal(2.0)},
            3: {'expected_charge': Decimal(4.5)},
        }

        charge_dictionary = self.updater._calculate_charge(rate_json, usage_dictionary)
        for key, entry in expected_results.items():
            usage = charge_dictionary[key].get('usage')
            calculated_charge = charge_dictionary[key].get('charge')
            self.assertEqual(usage, usage_dictionary[key])
            self.assertEqual(round(float(calculated_charge), 1), entry.get('expected_charge'))

    @patch('masu.database.cost_model_db_accessor.CostModelDBAccessor._make_rate_by_metric_map')
    @patch('masu.database.cost_model_db_accessor.CostModelDBAccessor.get_markup')
    def test_update_summary_charge_info_mem_cpu(self, mock_markup, mock_rate_map):
        """Test that OCP charge information is updated for cpu and memory."""
        markup = {}
        mem_rate_usage = {'tiered_rates': [{'value': '100', 'unit': 'USD'}]}
        mem_rate_request = {'tiered_rates': [{'value': '150', 'unit': 'USD'}]}
        cpu_rate_usage = {'tiered_rates': [{'value': '200', 'unit': 'USD'}]}
        cpu_rate_request = {'tiered_rates': [{'value': '250', 'unit': 'USD'}]}
        rate_metric_map = {
            'cpu_core_usage_per_hour': cpu_rate_usage,
            'cpu_core_request_per_hour': cpu_rate_request,
            'memory_gb_usage_per_hour': mem_rate_usage,
            'memory_gb_request_per_hour': mem_rate_request,
        }

        mock_markup.return_value = markup
        mock_rate_map.return_value = rate_metric_map

        cpu_usage_rate_value = Decimal(cpu_rate_usage.get('tiered_rates')[0].get('value'))
        cpu_request_rate_value = Decimal(cpu_rate_request.get('tiered_rates')[0].get('value'))
        mem_usage_rate_value = Decimal(mem_rate_usage.get('tiered_rates')[0].get('value'))
        mem_request_rate_value = Decimal(mem_rate_request.get('tiered_rates')[0].get('value'))

        usage_period = self.accessor.get_current_usage_period()
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)

        self.accessor.populate_line_item_daily_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, self.cluster_id)
        self.updater.update_summary_charge_info(
            str(usage_period.report_period_start),
            str(usage_period.report_period_end)
        )

        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']

        with schema_context(self.schema):
            items = self.accessor._get_db_obj_query(table_name).all()
            for item in items:
                mem_usage_value = item.pod_usage_memory_gigabyte_hours
                mem_request_value = item.pod_request_memory_gigabyte_hours
                mem_charge = (mem_usage_value * mem_usage_rate_value) + (
                    mem_request_value * mem_request_rate_value
                )
                self.assertAlmostEqual(mem_charge, item.pod_charge_memory_gigabyte_hours, places=6)

                cpu_usage_value = (
                    item.pod_usage_cpu_core_hours
                    if item.pod_usage_cpu_core_hours
                    else Decimal('0.0')
                )
                cpu_request_value = item.pod_request_cpu_core_hours
                cpu_charge = (cpu_usage_value * cpu_usage_rate_value) + (
                    cpu_request_value * cpu_request_rate_value
                )
                self.assertAlmostEqual(cpu_charge, item.pod_charge_cpu_core_hours, places=6)

    @patch('masu.database.cost_model_db_accessor.CostModelDBAccessor._make_rate_by_metric_map')
    @patch('masu.database.cost_model_db_accessor.CostModelDBAccessor.get_markup')
    def test_update_summary_charge_info_cpu(self, mock_markup, mock_rate_map):
        """Test that OCP charge information is updated for cpu."""
        markup = {}
        mem_rate = None
        cpu_rate = {'tiered_rates': [{'value': '200', 'unit': 'USD'}]}

        rate_metric_map = {
            'cpu_core_usage_per_hour': cpu_rate,
            'memory_gb_usage_per_hour': mem_rate,
        }

        mock_markup.return_value = markup
        mock_rate_map.return_value = rate_metric_map

        cpu_rate_value = Decimal(cpu_rate.get('tiered_rates')[0].get('value'))

        usage_period = self.accessor.get_current_usage_period()
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)

        self.accessor.populate_line_item_daily_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, self.cluster_id)
        self.updater.update_summary_charge_info(
            str(usage_period.report_period_start),
            str(usage_period.report_period_end)
        )

        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']

        with schema_context(self.schema):
            items = self.accessor._get_db_obj_query(table_name).all()
            for item in items:
                cpu_usage_value = (
                    item.pod_usage_cpu_core_hours if item.pod_usage_cpu_core_hours else Decimal(0.0)
                )
                self.assertAlmostEqual(0.0, item.pod_charge_memory_gigabyte_hours)
                self.assertAlmostEqual(
                    cpu_usage_value * cpu_rate_value, item.pod_charge_cpu_core_hours, places=6
                )

    @patch('masu.database.cost_model_db_accessor.CostModelDBAccessor._make_rate_by_metric_map')
    @patch('masu.database.cost_model_db_accessor.CostModelDBAccessor.get_markup')
    def test_update_summary_charge_info_mem(self, mock_markup, mock_rate_map):
        """Test that OCP charge information is updated for cpu and memory."""
        markup = {}
        mem_rate = {'tiered_rates': [{'value': '100', 'unit': 'USD'}]}
        cpu_rate = None
        rate_metric_map = {
            'memory_gb_usage_per_hour': mem_rate,
            'cpu_core_usage_per_hour': cpu_rate,
        }

        mock_markup.return_value = markup
        mock_rate_map.return_value = rate_metric_map

        mem_rate_value = Decimal(mem_rate.get('tiered_rates')[0].get('value'))

        usage_period = self.accessor.get_current_usage_period()
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)

        self.accessor.populate_line_item_daily_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, self.cluster_id)
        self.updater.update_summary_charge_info(
            str(usage_period.report_period_start),
            str(usage_period.report_period_end)
        )

        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']

        with schema_context(self.schema):
            items = self.accessor._get_db_obj_query(table_name).all()
            for item in items:
                mem_usage_value = Decimal(item.pod_usage_memory_gigabyte_hours)
                self.assertAlmostEqual(
                    mem_usage_value * mem_rate_value,
                    Decimal(item.pod_charge_memory_gigabyte_hours),
                    places=6,
                )
                self.assertAlmostEqual(0.0, Decimal(item.pod_charge_cpu_core_hours), places=6)

    @patch('masu.database.cost_model_db_accessor.CostModelDBAccessor._make_rate_by_metric_map')
    @patch('masu.database.cost_model_db_accessor.CostModelDBAccessor.get_markup')
    def test_update_summary_storage_charge(self, mock_markup, mock_rate_map):
        """Test that OCP charge information is updated for storage."""
        markup = {}
        usage_rate = {'tiered_rates': [{'value': '100', 'unit': 'USD'}]}
        request_rate = {'tiered_rates': [{'value': '200', 'unit': 'USD'}]}
        rate_metric_map = {
            'storage_gb_usage_per_month': usage_rate,
            'storage_gb_request_per_month': request_rate,
        }

        mock_markup.return_value = markup
        mock_rate_map.return_value = rate_metric_map

        usage_rate_value = Decimal(usage_rate.get('tiered_rates')[0].get('value'))
        request_rate_value = Decimal(request_rate.get('tiered_rates')[0].get('value'))

        usage_period = self.accessor.get_current_usage_period()
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)

        self.accessor.populate_line_item_daily_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_storage_line_item_daily_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_storage_line_item_daily_summary_table(
            start_date, end_date, self.cluster_id
        )
        self.updater.update_summary_charge_info(
            str(usage_period.report_period_start),
            str(usage_period.report_period_end)
        )

        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']

        with schema_context(self.schema):
            items = self.accessor._get_db_obj_query(table_name).filter(data_source='Storage').all()
            for item in items:
                storage_charge = Decimal(item.persistentvolumeclaim_charge_gb_month)
                expected_usage_charge = usage_rate_value * Decimal(
                    item.persistentvolumeclaim_usage_gigabyte_months
                )
                expected_request_charge = request_rate_value * Decimal(
                    item.volume_request_storage_gigabyte_months
                )
                self.assertAlmostEqual(
                    storage_charge, expected_usage_charge + expected_request_charge, places=6
                )

    def test_update_summary_markup_charge(self):
        """Test markup charge update for summary table is successful."""
        markup = {'value': 10, 'unit': 'percent'}
        markup_percentage = Decimal(markup.get('value')) / 100
        rate = [
            {
                'metric': {'name': 'memory_gb_usage_per_hour'},
                'tiered_rates': [{'value': 1, 'unit': 'USD'}],
            }
        ]
        self.creator.create_cost_model(self.ocp_provider_uuid,
                                       Provider.PROVIDER_OCP, rates=rate, markup=markup)

        usage_period = self.accessor.get_current_usage_period()
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)

        self.accessor.populate_line_item_daily_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, self.cluster_id)
        self.updater.update_summary_charge_info(
            str(usage_period.report_period_start),
            str(usage_period.report_period_end)
        )
        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']
        with OCPReportDBAccessor(schema=self.schema, column_map=self.column_map) as accessor:
            with schema_context(self.schema):
                items = accessor._get_db_obj_query(table_name).all()
                for item in items:
                    markup_value = item.markup_cost
                    self.assertEqual(
                        markup_value, item.pod_charge_memory_gigabyte_hours * markup_percentage
                    )

    def test_update_summary_markup_charge_with_infrastructure_markup(self):
        """Test that markup for infrastructure is included."""
        rate = [
            {
                'metric': {'name': 'cpu_core_usage_per_hour'},
                'tiered_rates': [{'value': 1.5, 'unit': 'USD'}],
            }
        ]
        openshift_markup = {'value': 10, 'unit': 'percent'}
        self.creator.create_cost_model(
            self.ocp_provider_uuid, Provider.PROVIDER_OCP, rates=rate, markup=openshift_markup
        )

        aws_markup = {'value': 5, 'unit': 'percent'}
        self.creator.create_cost_model(self.aws_provider_uuid, Provider.PROVIDER_AWS, markup=aws_markup)

        # Set infrastructure relationship for OCP on AWS
        # This is required to pick up the AWS markup
        with ProviderDBAccessor(self.ocp_provider_uuid) as accessor:
            accessor.set_infrastructure(self.aws_provider_uuid, Provider.PROVIDER_AWS)

        usage_period = self.accessor.get_current_usage_period()
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)

        self.accessor.populate_line_item_daily_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, self.cluster_id)
        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']
        with OCPReportDBAccessor(schema=self.schema, column_map=self.column_map) as accessor:
            # Add some infrastructure cost
            summary_items = accessor._get_db_obj_query(table_name)
            for item in summary_items:
                item.infra_cost = Decimal(1.0)
                item.project_infra_cost = Decimal(0.5)
                item.save()
        self.updater.update_summary_charge_info(
            str(usage_period.report_period_start),
            str(usage_period.report_period_end)
        )
        with OCPReportDBAccessor(schema=self.schema, column_map=self.column_map) as accessor:
            self.assertIsNotNone(accessor.get_current_usage_period().derived_cost_datetime)

            items = accessor._get_db_obj_query(table_name).all()
            with schema_context(self.schema):
                for item in items:
                    derived_cost = Decimal(0)
                    derived_cost += (
                        item.pod_charge_cpu_core_hours
                        if item.pod_charge_cpu_core_hours
                        else Decimal(0)
                    )
                    derived_cost += (
                        item.pod_charge_memory_gigabyte_hours
                        if item.pod_charge_memory_gigabyte_hours
                        else Decimal(0)
                    )
                    derived_cost += (
                        item.persistentvolumeclaim_charge_gb_month
                        if item.persistentvolumeclaim_charge_gb_month
                        else Decimal(0)
                    )
                    infra_cost = item.infra_cost if item.infra_cost else Decimal(0)
                    project_infra_cost = (
                        item.project_infra_cost if item.project_infra_cost else Decimal(0)
                    )
                    expected_markup_cost = (
                        derived_cost * openshift_markup['value'] / 100
                        + infra_cost * aws_markup['value'] / 100
                    )
                    expected_project_markup_cost = (
                        derived_cost * openshift_markup['value'] / 100
                        + project_infra_cost * aws_markup['value'] / 100
                    )
                    self.assertEqual(expected_markup_cost, item.markup_cost)
                    self.assertEqual(expected_project_markup_cost, item.project_markup_cost)

    def test_update_summary_markup_charge_no_clusterid(self):
        """Test that markup is calculated without a cluster id."""
        markup = {'value': 10, 'unit': 'percent'}
        markup_percentage = Decimal(markup.get('value')) / 100
        rate = [
            {
                'metric': {'name': 'memory_gb_usage_per_hour'},
                'tiered_rates': [{'value': 1, 'unit': 'USD'}],
            }
        ]
        self.creator.create_cost_model(self.ocp_provider_uuid, Provider.PROVIDER_OCP, rates=rate, markup=markup)

        usage_period = self.accessor.get_current_usage_period()
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)

        self.accessor.populate_line_item_daily_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, self.cluster_id)
        self.updater._update_pod_charge(start_date, end_date)
        self.updater._update_storage_charge(start_date, end_date)

        self.updater._cluster_id = None
        self.updater._update_markup_cost(start_date, end_date)

        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']
        with OCPReportDBAccessor(schema=self.schema, column_map=self.column_map) as accessor:
            with schema_context(self.schema):
                items = accessor._get_db_obj_query(table_name).all()
                for item in items:
                    markup_value = Decimal(item.markup_cost)
                    self.assertEqual(
                        markup_value, item.pod_charge_memory_gigabyte_hours * markup_percentage
                    )

    @patch('masu.database.cost_model_db_accessor.CostModelDBAccessor._make_rate_by_metric_map')
    @patch('masu.database.cost_model_db_accessor.CostModelDBAccessor.get_markup')
    def test_update_summary_charge_info_mem_cpu_malformed_mem(self, mock_markup, mock_rate_map):
        """Test that OCP charge information is updated for cpu and memory with malformed memory rates."""
        markup = {}
        mem_rate = {
            'tiered_rates': [
                {'usage': {'usage_start': None, 'usage_end': '10'}, 'value': '0.10', 'unit': 'USD'},
                {'usage': {'usage_start': '10', 'usage_end': '20'}, 'value': '0.20', 'unit': 'USD'},
                {'usage': {'usage_start': '20', 'usage_end': '30'}, 'value': '0.30', 'unit': 'USD'},
                {'usage': {'usage_start': '30', 'usage_end': '40'}, 'value': '0.40', 'unit': 'USD'},
            ]
        }
        cpu_rate = {'tiered_rates': [{'value': '200', 'unit': 'USD'}]}

        rate_metric_map = {
            'memory_gb_usage_per_hour': mem_rate,
            'cpu_core_usage_per_hour': cpu_rate,
        }
        mock_markup.return_value = markup
        mock_rate_map.return_value = rate_metric_map

        usage_period = self.accessor.get_current_usage_period()
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)

        self.accessor.populate_line_item_daily_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, self.cluster_id)
        self.updater.update_summary_charge_info(
            str(usage_period.report_period_start),
            str(usage_period.report_period_end)
        )

        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']

        with schema_context(self.schema):
            items = self.accessor._get_db_obj_query(table_name).all()
            for item in items:
                self.assertIsNone(item.pod_charge_memory_gigabyte_hours)
                self.assertIsNone(item.pod_charge_cpu_core_hours)

    @patch('masu.database.cost_model_db_accessor.CostModelDBAccessor._make_rate_by_metric_map')
    @patch('masu.database.cost_model_db_accessor.CostModelDBAccessor.get_markup')
    def test_update_summary_charge_info_mem_cpu_malformed_cpu(self, mock_markup, mock_rate_map):
        """Test that OCP charge information is updated for cpu and memory with malformed cpu rates."""
        markup = {}
        mem_rate = {'tiered_rates': [{'value': '100', 'unit': 'USD'}]}
        cpu_rate = {
            'tiered_rates': [
                {'usage': {'usage_start': '5', 'usage_end': '10'}, 'value': '0.10', 'unit': 'USD'},
                {'usage': {'usage_start': '10', 'usage_end': '20'}, 'value': '0.20', 'unit': 'USD'},
                {'usage': {'usage_start': '20', 'usage_end': '30'}, 'value': '0.30', 'unit': 'USD'},
                {'usage': {'usage_start': '30', 'usage_end': None}, 'value': '0.40', 'unit': 'USD'},
            ]
        }

        rate_metric_map = {
            'memory_gb_usage_per_hour': mem_rate,
            'cpu_core_usage_per_hour': cpu_rate,
        }
        mock_markup.return_value = markup
        mock_rate_map.return_value = rate_metric_map

        usage_period = self.accessor.get_current_usage_period()
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)

        self.accessor.populate_line_item_daily_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, self.cluster_id)
        self.updater.update_summary_charge_info(
            str(usage_period.report_period_start),
            str(usage_period.report_period_end)
        )

        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']
        with schema_context(self.schema):
            items = self.accessor._get_db_obj_query(table_name).all()
            for item in items:
                self.assertIsNone(item.pod_charge_cpu_core_hours)
                self.assertIsNone(item.pod_charge_memory_gigabyte_hours)

    def test_update_summary_charge_info_cpu_real_rates(self):
        """Test that OCP charge information is updated for cpu from the right provider uuid."""
        cpu_usage_rate = [
            {
                'metric': {'name': 'cpu_core_usage_per_hour'},
                'tiered_rates': [{'value': 1.5, 'unit': 'USD'}],
            }
        ]
        self.creator.create_cost_model(self.ocp_provider_uuid, Provider.PROVIDER_OCP, cpu_usage_rate)

        other_provider_uuid = self.aws_provider_uuid
        other_cpu_usage_rate = [
            {
                'metric': {'name': 'cpu_core_usage_per_hour'},
                'tiered_rates': [{'value': 2.5, 'unit': 'USD'}],
            }
        ]
        self.creator.create_cost_model(other_provider_uuid, Provider.PROVIDER_AWS, other_cpu_usage_rate)

        cpu_rate_value = Decimal(cpu_usage_rate[0].get('tiered_rates')[0].get('value'))

        usage_period = self.accessor.get_current_usage_period()
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)

        self.accessor.populate_line_item_daily_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, self.cluster_id)
        self.updater.update_summary_charge_info(
            str(usage_period.report_period_start),
            str(usage_period.report_period_end)
        )

        with OCPReportDBAccessor(schema='acct10001', column_map=self.column_map) as accessor:
            self.assertIsNotNone(accessor.get_current_usage_period().derived_cost_datetime)
        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']
        items = self.accessor._get_db_obj_query(table_name).all()
        with schema_context(self.schema):
            for item in items:
                cpu_usage_value = Decimal(item.pod_usage_cpu_core_hours) if \
                    item.pod_usage_cpu_core_hours else Decimal(0.0)
                self.assertAlmostEqual(0.0, Decimal(item.pod_charge_memory_gigabyte_hours), places=5)
                self.assertAlmostEqual(cpu_usage_value * cpu_rate_value,
                                       Decimal(item.pod_charge_cpu_core_hours),
                                       places=6)

    def test_update_monthly_cost(self):
        """Test OCP charge for monthly costs is updated."""
        node_cost = random.randrange(1, 200)
        monthly_cost_metric = [{'metric': {'name': 'node_cost_per_month'},
                                'tiered_rates': [{'value': node_cost, 'unit': 'USD'}]}]
        self.creator.create_cost_model(self.ocp_provider_uuid, Provider.PROVIDER_OCP, monthly_cost_metric)

        usage_period = self.accessor.get_current_usage_period()
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)

        self.accessor.populate_line_item_daily_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, self.cluster_id)
        self.updater.update_summary_charge_info(
            str(usage_period.report_period_start),
            str(usage_period.report_period_end)
        )

        with schema_context(self.schema):
            unique_nodes = OCPUsageLineItemDailySummary.objects.filter(
                usage_start__gte=usage_period.report_period_start,
                usage_start__lt=usage_period.report_period_end,
                node__isnull=False
            ).values_list('node').distinct().count()

            monthly_cost_row = OCPUsageLineItemDailySummary.objects.filter(
                monthly_cost__isnull=False
            ).first()
            self.assertGreater(monthly_cost_row.monthly_cost, 0)
            self.assertEquals(monthly_cost_row.monthly_cost, unique_nodes * node_cost)
