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
from dateutil.relativedelta import relativedelta
from unittest.mock import patch
from decimal import Decimal
import uuid

import psycopg2

from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.processor.ocp.ocp_report_charge_updater import (
    OCPReportChargeUpdater,
    OCPReportChargeUpdaterError,
)
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator


class OCPReportChargeUpdaterTest(MasuTestCase):
    """Test Cases for the OCPReportChargeUpdater object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        cls.common_accessor = ReportingCommonDBAccessor()
        cls.column_map = cls.common_accessor.column_map
        cls.ocp_provider_uuid = '3c6e687e-1a09-4a05-970c-2ccf44b0952e'
        cls.accessor = OCPReportDBAccessor(
            schema='acct10001',
            column_map=cls.column_map
        )
        cls.provider_accessor = ProviderDBAccessor(
            provider_uuid=cls.ocp_provider_uuid
        )
        cls.report_schema = cls.accessor.report_schema
        cls.creator = ReportObjectCreator(
            cls.accessor,
            cls.column_map,
            cls.report_schema.column_types
        )
        cls.all_tables = list(OCP_REPORT_TABLE_MAP.values())

    @classmethod
    def tearDownClass(cls):
        """Close the DB session."""
        cls.accessor.close_session()

    def setUp(self):
        """"Set up a test with database objects."""
        super().setUp()
        if self.accessor._conn.closed:
            self.accessor._conn = self.accessor._db.connect()
        if self.accessor._pg2_conn.closed:
            self.accessor._pg2_conn = self.accessor._get_psycopg2_connection()
        if self.accessor._cursor.closed:
            self.accessor._cursor = self.accessor._get_psycopg2_cursor()
        provider_id = self.provider_accessor.get_provider().id
        self.cluster_id = self.ocp_provider_resource_name

        reporting_period = self.creator.create_ocp_report_period(provider_id=provider_id, cluster_id=self.cluster_id)

        report = self.creator.create_ocp_report(reporting_period, reporting_period.report_period_start)
        self.updater = OCPReportChargeUpdater(
            schema=self.test_schema,
            provider_uuid=self.ocp_provider_uuid,
            provider_id=provider_id
        )
        self.creator.create_ocp_usage_line_item(
            reporting_period,
            report
        )
        self.creator.create_ocp_storage_line_item(
            reporting_period,
            report
        )
        self.creator.create_ocp_usage_line_item(
            reporting_period,
            report,
            null_cpu_usage=True
        )

    def tearDown(self):
        """Return the database to a pre-test state."""
        self.accessor._session.rollback()

        for table_name in self.all_tables:
            tables = self.accessor._get_db_obj_query(table_name).all()
            for table in tables:
                self.accessor._session.delete(table)

    def test_normalize_tier(self):
        """Test the tier helper function to normalize rate tier."""
        rate_json = [{
            "usage": {
                "usage_start": '20',
                "usage_end": '30'
            },
            "value": '0.30',
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": None,
                "usage_end": "10"
            },
            "value": "0.10",
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": "10",
                "usage_end": "20"
            },
            "value": "0.20",
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": '30',
                "usage_end": None
            },
            "value": '0.40',
            "unit": "USD"
        }]
        normalized_tier = self.updater._normalize_tier(rate_json)
        self.assertEqual(len(normalized_tier), len(rate_json))
        self.assertIsNone(normalized_tier[0].get('usage').get('usage_start'))
        self.assertGreater(normalized_tier[1].get('usage').get('usage_end'), normalized_tier[0].get('usage').get('usage_end'))
        self.assertGreater(normalized_tier[2].get('usage').get('usage_end'), normalized_tier[1].get('usage').get('usage_end'))
        self.assertIsNone(normalized_tier[3].get('usage').get('usage_end'))

    def test_normalize_tier_no_start_end_provided(self):
        """Test the tier helper function to normalize rate tier when end points are not provided."""
        rate_json = [{
            "usage": {
                "usage_start": '20',
                "usage_end": '30'
            },
            "value": '0.30',
            "unit": "USD"
        },
        {
            "usage": {
                "usage_end": "10",
                "value": "0.10"
            },
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": "10",
                "usage_end": "20"
            },
            "value": "0.20",
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": '30'
            },
            "value": '0.40',
            "unit": "USD"
        }]
        normalized_tier = self.updater._normalize_tier(rate_json)
        self.assertEqual(len(normalized_tier), len(rate_json))
        self.assertIsNone(normalized_tier[0].get('usage').get('usage_start'))
        self.assertGreater(normalized_tier[1].get('usage').get('usage_end'), normalized_tier[0].get('usage').get('usage_end'))
        self.assertGreater(normalized_tier[2].get('usage').get('usage_end'), normalized_tier[1].get('usage').get('usage_end'))
        self.assertIsNone(normalized_tier[3].get('usage').get('usage_end'))

    def test_normalize_tier_missing_first(self):
        """Test the tier helper function when first tier is missing."""
        rate_json = [{
            "usage": {
                "usage_start": None,
                "usage_end": "10"
            },
            "value": "0.10",
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": '20',
                "usage_end": '30'
            },
            "value": '0.30',
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": "10",
                "usage_end": "20"
            },
            "value": "0.20",
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": '30',
                "usage_end": '40'
            },
            "value": '0.40',
            "unit": "USD"
        }]
        with self.assertRaises(OCPReportChargeUpdaterError) as error:
            self.updater._normalize_tier(rate_json)
            self.assertIn('Missing first tier', error)

    def test_normalize_tier_two_starts(self):
        """Test the tier helper function when two starting tiers are provided."""
        rate_json = [{
            "usage": {
                "usage_start": None,
                "usage_end": "10"
            },
            "value": "0.10",
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": None,
                "usage_end": '30'
            },
            "value": '0.30',
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": "10",
                "usage_end": "20"
            },
            "value": "0.20",
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": '30'
            },
            "value": '0.40',
            "unit": "USD"
        }]
        with self.assertRaises(OCPReportChargeUpdaterError) as error:
            self.updater._normalize_tier(rate_json)
            self.assertIn('Two starting tiers', error)

    def test_normalize_tier_two_final(self):
        """Test the tier helper function when two final tiers are provided."""
        rate_json = [{
            "usage": {
                "usage_start": None,
                "usage_end": "10"
            },
            "value": "0.10",
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": '20',
                "usage_end": '30'
            },
            "value": '0.30',
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": "10",
                "usage_end": None
            },
            "value": "0.20",
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": '30'
            },
            "value": '0.40',
            "unit": "USD"
        }]
        with self.assertRaises(OCPReportChargeUpdaterError) as error:
            self.updater._normalize_tier(rate_json)
            self.assertIn('Two final tiers', error)

    def test_normalize_tier_missing_last(self):
        """Test the tier helper function when last tier is missing."""
        rate_json = [{
            "usage": {
                "usage_start": '20',
                "usage_end": '30'
            },
            "value": '0.30',
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": "10",
                "usage_end": "20"
            },
            "value": "0.20",
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": '30',
                "usage_end": None
            },
            "value": '0.40',
            "unit": "USD"
        }]
        with self.assertRaises(OCPReportChargeUpdaterError) as error:
            self.updater._normalize_tier(rate_json)
            self.assertIn('Missing final tier', error)

    def test_bucket_applied(self):
        """Test the tier helper function."""
        lower_limit = 0
        upper_limit = 10
        test_matrix = [{'usage': -10, 'expected_usage_applied': 0},
                       {'usage': 5, 'expected_usage_applied': 5},
                       {'usage': 10, 'expected_usage_applied': 10},
                       {'usage': 15, 'expected_usage_applied': 10}]

        for test in test_matrix:
            usage_applied = self.updater._bucket_applied(test.get('usage'), lower_limit, upper_limit)
            self.assertEqual(usage_applied, test.get('expected_usage_applied'))

    def test_aggregate_charges(self):
        """Test the helper function to aggregate usage and request charges."""
        usage_charge = {3: {'usage': Decimal('0.000249'), 'charge': Decimal('0.049800')},
                        4: {'usage': Decimal('0.05'), 'charge': Decimal('0.10')}}
        request_charge = {3: {'usage': Decimal('0.000173'), 'charge': Decimal('0.043250')},
                          4: {'usage': Decimal('0.06'), 'charge': Decimal('0.20')}}

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
        usage_charge = {3: {'usage': Decimal('0.000249'), 'charge': Decimal('0.049800')},
                        4: {'usage': Decimal('0.05'), 'charge': Decimal('0.10')}}
        request_charge = {3: {'usage': Decimal('0.000173'), 'charge': Decimal('0.043250')}}

        with self.assertRaises(OCPReportChargeUpdaterError):
            self.updater._aggregate_charges(usage_charge, request_charge)

    def test_aggregate_charges_extra_request(self):
        """Test the helper function to aggregate usage and request charges where request_charge is larger."""
        usage_charge = {3: {'usage': Decimal('0.000249'), 'charge': Decimal('0.049800')}}
        request_charge = {3: {'usage': Decimal('0.000173'), 'charge': Decimal('0.043250')},
                          4: {'usage': Decimal('0.06'), 'charge': Decimal('0.20')}}

        with self.assertRaises(OCPReportChargeUpdaterError):
            self.updater._aggregate_charges(usage_charge, request_charge)

    def test_aggregate_charges_mismatched_keys(self):
        """Test the helper function to aggregate usage and request charges where dictionaries have different keys."""
        usage_charge = {3: {'usage': Decimal('0.000249'), 'charge': Decimal('0.049800')},
                        4: {'usage': Decimal('0.05'), 'charge': Decimal('0.10')}}
        request_charge = {3: {'usage': Decimal('0.000173'), 'charge': Decimal('0.043250')},
                          5: {'usage': Decimal('0.06'), 'charge': Decimal('0.20')}}

        with self.assertRaises(OCPReportChargeUpdaterError):
            self.updater._aggregate_charges(usage_charge, request_charge)

    def test_calculate_variable_charge(self):
        """Test the helper function to calculate charge."""
        rate_json = {"tiered_rates": [{
            "usage": {
                "usage_start": None,
                "usage_end": "10"
            },
            "value": "0.10",
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": "10",
                "usage_end": "20"
            },
            "value": "0.20",
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": '20',
                "usage_end": '30'
            },
            "value": '0.30',
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": '30',
                "usage_end": None
            },
            "value": '0.40',
            "unit": "USD"
        }]
        }
        usage_dictionary = {1: Decimal(5),
                            2: Decimal(15),
                            3: Decimal(25),
                            4: Decimal(50),
                            5: Decimal(0)}

        expected_results = {1: Decimal(0.5),  # usage: 5,  charge: 0.5 = 5 * 0.1
                            2: Decimal(2.0),  # usage: 15, charge: 2.0 = (10 * 0.1) + (5 * 0.2)
                            3: Decimal(4.5),  # usage: 25, charge: 4.5 = (10 * 0.1) + (10 * 0.2) + (5 * 0.3)
                            4: Decimal(14.0), # usage: 50, charge: 14.0 = (10 * 0.1) + (10 * 0.2) + (10 * 0.3) + (20 * 0.4)
                            5: Decimal(0.0)}  # usage: 0, charge: 0

        for key, usage in usage_dictionary.items():
            tier_charge = self.updater._calculate_variable_charge(usage, rate_json)
            self.assertEqual(tier_charge, expected_results.get(key))

    def test_calculate_variable_charge_floating_ends(self):
        """Test the helper function to calculate charge with floating endpoints."""
        rate_json = {"tiered_rates": [{
            "usage": {
                "usage_start": None,
                "usage_end": "10.3"
            },
            "value": "0.10",
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": "10.3",
                "usage_end": "19.8"
            },
            "value": "0.20",
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": '19.8',
                "usage_end": '22.6'
            },
            "value": '0.30',
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": '22.6',
                "usage_end": None
            },
            "value": '0.40',
            "unit": "USD"
        }]
        }

        usage_dictionary = {1: Decimal(5),
                            2: Decimal(15),
                            3: Decimal(25),
                            4: Decimal(50),
                            5: Decimal(0)}

        expected_results = {1: Decimal('0.5'),    # usage: 5,  charge: 0.5 = 5 * 0.1
                            2: Decimal('1.97'),   # usage: 15, charge: 1.97 = (10.3 * 0.1) + (4.7 * 0.2)
                            3: Decimal('4.730'),  # usage: 25, charge: 4.730 = (10.3 * 0.1) + (9.5 * 0.2) + (2.8 * 0.3) + (2.4 * 0.4)
                            4: Decimal('14.730'), # usage: 50, charge: 14.73 = (10.3 * 0.1) + (9.5 * 0.2) + (2.8 * 0.3) + (27.4 * 0.4)
                            5: Decimal('0.0')}    # usage: 0, charge: 0

        for key, usage in usage_dictionary.items():
            tier_charge = self.updater._calculate_variable_charge(usage, rate_json)
            self.assertEqual(tier_charge, expected_results.get(key))

    def test_calculate_variable_charge_ends_missing(self):
        """Test the helper function to calculate charge when end limits are missing."""
        rate_json = {"tiered_rates": [{
            "usage": {
                "usage_end": "10"
            },
            "value": "0.10",
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": "10",
                "usage_end": "20"
            },
            "value": "0.20",
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": '20',
                "usage_end": '30'
            },
            "value": '0.30',
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": '30'
            },
            "value": '0.40',
            "unit": "USD"
        }]
        }
        usage_dictionary = {1: Decimal(5),
                            2: Decimal(15),
                            3: Decimal(25),
                            4: Decimal(50),
                            5: Decimal(0),}

        expected_results = {1: Decimal(0.5),
                            2: Decimal(2.0),
                            3: Decimal(4.5),
                            4: Decimal(14.0),
                            5: Decimal(0.0)}

        for key, usage in usage_dictionary.items():
            tier_charge = self.updater._calculate_variable_charge(usage, rate_json)
            self.assertEqual(tier_charge, expected_results.get(key))

    def test_calculate_charge(self):
        """Test the helper function to calculate charge."""
        rate_json = {"tiered_rates": [{
            "usage": {
                "usage_start": None,
                "usage_end": "10"
            },
            "value": "0.10",
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": "10",
                "usage_end": "20"
            },
            "value": "0.20",
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": '20',
                "usage_end": '30'
            },
            "value": '0.30',
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": '30',
                "usage_end": None
            },
            "value": '0.40',
            "unit": "USD"
        }]
        }
        usage_dictionary = {1: Decimal(5),
                            2: Decimal(15),
                            3: Decimal(25),}

        expected_results = {1: {'expected_charge': Decimal(0.5)},
                            2: {'expected_charge': Decimal(2.0)},
                            3: {'expected_charge': Decimal(4.5)}}

        charge_dictionary = self.updater._calculate_charge(rate_json, usage_dictionary)
        for key, entry in expected_results.items():
            usage = charge_dictionary[key].get('usage')
            calculated_charge = charge_dictionary[key].get('charge')
            self.assertEqual(usage, usage_dictionary[key])
            self.assertEqual(round(float(calculated_charge), 1), entry.get('expected_charge'))

    @patch('masu.database.ocp_rate_db_accessor.OCPRateDBAccessor.get_cpu_core_request_per_hour_rates')
    @patch('masu.database.ocp_rate_db_accessor.OCPRateDBAccessor.get_cpu_core_usage_per_hour_rates')
    @patch('masu.database.ocp_rate_db_accessor.OCPRateDBAccessor.get_memory_gb_request_per_hour_rates')
    @patch('masu.database.ocp_rate_db_accessor.OCPRateDBAccessor.get_memory_gb_usage_per_hour_rates')
    def test_update_summary_charge_info_mem_cpu(self, mock_db_mem_usage_rate, mock_db_mem_request_rate, mock_db_cpu_usage_rate, mock_db_cpu_request_rate):
        """Test that OCP charge information is updated for cpu and memory."""
        mem_rate_usage = {'tiered_rates': [{'value': '100', 'unit': 'USD'}]}
        mem_rate_request = {'tiered_rates': [{'value': '150', 'unit': 'USD'}]}
        cpu_rate_usage = {'tiered_rates': [{'value': '200', 'unit': 'USD'}]}
        cpu_rate_request = {'tiered_rates': [{'value': '250', 'unit': 'USD'}]}

        mock_db_mem_usage_rate.return_value = mem_rate_usage
        mock_db_mem_request_rate.return_value = mem_rate_request
        mock_db_cpu_usage_rate.return_value = cpu_rate_usage
        mock_db_cpu_request_rate.return_value = cpu_rate_request

        cpu_usage_rate_value = float(cpu_rate_usage.get('tiered_rates')[0].get('value'))
        cpu_request_rate_value = float(cpu_rate_request.get('tiered_rates')[0].get('value'))
        mem_usage_rate_value = float(mem_rate_usage.get('tiered_rates')[0].get('value'))
        mem_request_rate_value = float(mem_rate_request.get('tiered_rates')[0].get('value'))

        usage_period = self.accessor.get_current_usage_period()
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)

        self.accessor.populate_line_item_daily_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_cost_summary_table(self.cluster_id, start_date, end_date)
        self.updater.update_summary_charge_info()

        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']

        items = self.accessor._get_db_obj_query(table_name).all()
        for item in items:
            mem_usage_value = float(item.pod_usage_memory_gigabyte_hours)
            mem_request_value = float(item.pod_request_memory_gigabyte_hours)
            mem_charge = (mem_usage_value * mem_usage_rate_value) + (mem_request_value * mem_request_rate_value)
            self.assertEqual(round(mem_charge, 6),
                             round(float(item.pod_charge_memory_gigabyte_hours), 6))

            cpu_usage_value = float(item.pod_usage_cpu_core_hours) if item.pod_usage_cpu_core_hours else float(0.0)
            cpu_request_value = float(item.pod_request_cpu_core_hours)
            cpu_charge = (cpu_usage_value * cpu_usage_rate_value) + (cpu_request_value * cpu_request_rate_value)
            self.assertEqual(round(cpu_charge, 6),
                             round(float(item.pod_charge_cpu_core_hours), 6))

    @patch('masu.database.ocp_rate_db_accessor.OCPRateDBAccessor.get_cpu_core_usage_per_hour_rates')
    @patch('masu.database.ocp_rate_db_accessor.OCPRateDBAccessor.get_memory_gb_usage_per_hour_rates')
    def test_update_summary_charge_info_cpu(self, mock_db_mem_usage_rate, mock_db_cpu_usage_rate):
        """Test that OCP charge information is updated for cpu."""
        mem_rate = None
        cpu_rate = {'tiered_rates': [{'value': '200', 'unit': 'USD'}]}

        mock_db_mem_usage_rate.return_value = mem_rate
        mock_db_cpu_usage_rate.return_value = cpu_rate

        cpu_rate_value = float(cpu_rate.get('tiered_rates')[0].get('value'))

        usage_period = self.accessor.get_current_usage_period()
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)

        self.accessor.populate_line_item_daily_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_cost_summary_table(self.cluster_id, start_date, end_date)
        self.updater.update_summary_charge_info()

        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']

        items = self.accessor._get_db_obj_query(table_name).all()
        for item in items:
            cpu_usage_value = float(item.pod_usage_cpu_core_hours) if item.pod_usage_cpu_core_hours else float(0.0)
            self.assertEqual(round(0.0, 6),
                             round(float(item.pod_charge_memory_gigabyte_hours), 6))
            self.assertEqual(round(cpu_usage_value*cpu_rate_value, 6),
                             round(float(item.pod_charge_cpu_core_hours), 6))

    @patch('masu.database.ocp_rate_db_accessor.OCPRateDBAccessor.get_cpu_core_usage_per_hour_rates')
    @patch('masu.database.ocp_rate_db_accessor.OCPRateDBAccessor.get_memory_gb_usage_per_hour_rates')
    def test_update_summary_charge_info_mem(self, mock_db_mem_usage_rate, mock_db_cpu_usage_rate):
        """Test that OCP charge information is updated for cpu and memory."""
        mem_rate = {'tiered_rates': [{'value': '100', 'unit': 'USD'}]}
        cpu_rate = None

        mock_db_mem_usage_rate.return_value = mem_rate
        mock_db_cpu_usage_rate.return_value = cpu_rate

        mem_rate_value = float(mem_rate.get('tiered_rates')[0].get('value'))

        usage_period = self.accessor.get_current_usage_period()
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)

        self.accessor.populate_line_item_daily_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_cost_summary_table(self.cluster_id, start_date, end_date)
        self.updater.update_summary_charge_info()

        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']

        items = self.accessor._get_db_obj_query(table_name).all()
        for item in items:
            mem_usage_value = float(item.pod_usage_memory_gigabyte_hours)
            self.assertEqual(round(mem_usage_value*mem_rate_value, 6),
                             round(float(item.pod_charge_memory_gigabyte_hours), 6))
            self.assertEqual(round(0.0, 6),
                             round(float(item.pod_charge_cpu_core_hours), 6))

    @patch('masu.database.ocp_rate_db_accessor.OCPRateDBAccessor.get_storage_gb_request_per_month_rates')
    @patch('masu.database.ocp_rate_db_accessor.OCPRateDBAccessor.get_storage_gb_usage_per_month_rates')
    def test_update_summary_storage_charge(self, mock_db_storage_usage_rate, mock_db_storage_request_rate):
        """Test that OCP charge information is updated for storage."""
        usage_rate = {'tiered_rates': [{'value': '100', 'unit': 'USD'}]}
        request_rate = {'tiered_rates': [{'value': '200', 'unit': 'USD'}]}

        mock_db_storage_usage_rate.return_value = usage_rate
        mock_db_storage_request_rate.return_value = request_rate

        usage_rate_value = float(usage_rate.get('tiered_rates')[0].get('value'))
        request_rate_value = float(request_rate.get('tiered_rates')[0].get('value'))

        usage_period = self.accessor.get_current_usage_period()
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)

        self.accessor.populate_line_item_daily_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_storage_line_item_daily_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_storage_line_item_daily_summary_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_cost_summary_table(self.cluster_id, start_date, end_date)
        self.updater.update_summary_charge_info()

        table_name = OCP_REPORT_TABLE_MAP['storage_line_item_daily_summary']

        items = self.accessor._get_db_obj_query(table_name).all()
        for item in items:
            storage_charge = float(item.persistentvolumeclaim_charge_gb_month)
            expected_usage_charge = usage_rate_value * float(item.persistentvolumeclaim_usage_gigabyte_months)
            expected_request_charge = request_rate_value * float(item.volume_request_storage_gigabyte_months)
            self.assertEqual(round(storage_charge, 6),
                             round(expected_usage_charge + expected_request_charge, 6))

    @patch('masu.database.ocp_rate_db_accessor.OCPRateDBAccessor.get_cpu_core_usage_per_hour_rates')
    @patch('masu.database.ocp_rate_db_accessor.OCPRateDBAccessor.get_memory_gb_usage_per_hour_rates')
    def test_update_summary_charge_info_mem_cpu_malformed_mem(self, mock_db_mem_usage_rate, mock_db_cpu_usage_rate):
        """Test that OCP charge information is updated for cpu and memory with malformed memory rates."""
        mem_rate = {"tiered_rates": [{
            "usage": {
                "usage_start": None,
                "usage_end": "10"
            },
            "value": "0.10",
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": "10",
                "usage_end": "20"
            },
            "value": "0.20",
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": '20',
                "usage_end": '30'
            },
            "value": '0.30',
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": '30',
                "usage_end": '40'
            },
            "value": '0.40',
            "unit": "USD"
        }]
        }
        cpu_rate = {'tiered_rates': [{'value': '200', 'unit': 'USD'}]}

        mock_db_mem_usage_rate.return_value = mem_rate
        mock_db_cpu_usage_rate.return_value = cpu_rate

        cpu_rate_value = float(cpu_rate.get('tiered_rates')[0].get('value'))

        usage_period = self.accessor.get_current_usage_period()
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)

        self.accessor.populate_line_item_daily_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_cost_summary_table(self.cluster_id, start_date, end_date)
        self.updater.update_summary_charge_info()

        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']

        items = self.accessor._get_db_obj_query(table_name).all()
        for item in items:
            self.assertIsNone(item.pod_charge_memory_gigabyte_hours)
            self.assertIsNone(item.pod_charge_cpu_core_hours)


    @patch('masu.database.ocp_rate_db_accessor.OCPRateDBAccessor.get_cpu_core_usage_per_hour_rates')
    @patch('masu.database.ocp_rate_db_accessor.OCPRateDBAccessor.get_memory_gb_usage_per_hour_rates')
    def test_update_summary_charge_info_mem_cpu_malformed_cpu(self, mock_db_mem_usage_rate, mock_db_cpu_usage_rate):
        """Test that OCP charge information is updated for cpu and memory with malformed cpu rates."""
        mem_rate = {'tiered_rates': [{'value': '100', 'unit': 'USD'}]}
        cpu_rate = {"tiered_rates": [{
            "usage": {
                "usage_start": "5",
                "usage_end": "10"
            },
            "value": "0.10",
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": "10",
                "usage_end": "20"
            },
            "value": "0.20",
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": '20',
                "usage_end": '30'
            },
            "value": '0.30',
            "unit": "USD"
        },
        {
            "usage": {
                "usage_start": '30',
                "usage_end": None
            },
            "value": '0.40',
            "unit": "USD"
        }]
        }

        mock_db_mem_usage_rate.return_value = mem_rate
        mock_db_cpu_usage_rate.return_value = cpu_rate

        usage_period = self.accessor.get_current_usage_period()
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)

        self.accessor.populate_line_item_daily_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_cost_summary_table(self.cluster_id, start_date, end_date)
        self.updater.update_summary_charge_info()

        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']

        items = self.accessor._get_db_obj_query(table_name).all()
        for item in items:
            self.assertIsNone(item.pod_charge_cpu_core_hours)
            self.assertIsNone(item.pod_charge_memory_gigabyte_hours)

    def test_update_summary_charge_info_cpu_real_rates(self):
        """Test that OCP charge information is updated for cpu from the right provider uuid."""
        cpu_usage_rate = [{'metric': {'name': 'cpu_core_usage_per_hour'},
                          'tiered_rates': [{'value': 1.5, 'unit': 'USD'}]}]
        self.creator.create_cost_model(self.ocp_provider_uuid, 'OCP', cpu_usage_rate)

        other_provider_uuid = '6e212746-484a-40cd-bba0-09a19d132d64'
        other_cpu_usage_rate = [{'metric': {'name': 'cpu_core_usage_per_hour'},
                                'tiered_rates': [{'value': 2.5, 'unit': 'USD'}]}]
        self.creator.create_cost_model(other_provider_uuid, 'OCP', other_cpu_usage_rate)

        cpu_rate_value = float(cpu_usage_rate[0].get('tiered_rates')[0].get('value'))

        usage_period = self.accessor.get_current_usage_period()
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)

        self.accessor.populate_line_item_daily_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_cost_summary_table(self.cluster_id, start_date, end_date)
        self.updater.update_summary_charge_info()

        with OCPReportDBAccessor(schema='acct10001', column_map=self.column_map) as accessor:
            self.assertIsNotNone(accessor.get_current_usage_period().derived_cost_datetime)
        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']

        items = self.accessor._get_db_obj_query(table_name).all()
        for item in items:
            cpu_usage_value = float(item.pod_usage_cpu_core_hours) if item.pod_usage_cpu_core_hours else float(0.0)
            self.assertEqual(round(0.0, 5),
                             round(float(item.pod_charge_memory_gigabyte_hours), 5))
            self.assertEqual(round(cpu_usage_value*cpu_rate_value, 5),
                             round(float(item.pod_charge_cpu_core_hours), 5))
