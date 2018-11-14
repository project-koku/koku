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
import psycopg2
import uuid

from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_rate_db_accessor import OCPRateDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from tests import MasuTestCase
from tests.database.helpers import ReportObjectCreator


class OCPRateDBAccessorTest(MasuTestCase):
    """Test Cases for the OCPRateDBAccessor object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        cls.common_accessor = ReportingCommonDBAccessor()
        cls.column_map = cls.common_accessor.column_map
        cls.accessor = OCPRateDBAccessor(
            schema='acct10001org20002',
            provider_uuid='3c6e687e-1a09-4a05-970c-2ccf44b0952e',
            column_map=cls.column_map
        )
        cls.report_schema = cls.accessor.report_schema
        cls.creator = ReportObjectCreator(
            cls.accessor,
            cls.column_map,
            cls.report_schema.column_types
        )
        cls.all_tables = list(OCP_REPORT_TABLE_MAP.values())

    def setUp(self):
        """"Set up a test with database objects."""
        super().setUp()
        if self.accessor._conn.closed:
            self.accessor._conn = self.accessor._db.connect()
        if self.accessor._pg2_conn.closed:
            self.accessor._pg2_conn = self.accessor._get_psycopg2_connection()
        if self.accessor._cursor.closed:
            self.accessor._cursor = self.accessor._get_psycopg2_cursor()

        reporting_period = self.creator.create_ocp_report_period()
        report = self.creator.create_ocp_report(reporting_period)
        self.creator.create_ocp_usage_line_item(
            reporting_period,
            report
        )
        self.cpu_rate = {'metric': 'cpu_core_per_hour',
                         'provider_uuid': '3c6e687e-1a09-4a05-970c-2ccf44b0952e',
                         'rates': {'fixed_rate': {'value': 1.5, 'unit': 'USD'}}}
        self.mem_rate = {'metric': 'memory_gb_per_hour',
                         'provider_uuid': '3c6e687e-1a09-4a05-970c-2ccf44b0952e',
                         'rates': {'fixed_rate': {'value': 2.5, 'unit': 'USD'}}}
        self.creator.create_rate(**self.cpu_rate)
        self.creator.create_rate(**self.mem_rate)

    def tearDown(self):
        """Return the database to a pre-test state."""
        self.accessor._session.rollback()

        for table_name in self.all_tables:
            tables = self.accessor._get_db_obj_query(table_name).all()
            for table in tables:
                self.accessor._session.delete(table)
        self.accessor.commit()

    def test_initializer(self):
        """Test initializer."""
        self.assertIsNotNone(self.report_schema)
        self.assertIsNotNone(self.accessor._session)
        self.assertIsNotNone(self.accessor._conn)
        self.assertIsNotNone(self.accessor._cursor)

    def test_get_metric(self):
        """Test get metric."""
        cpu_metric = self.accessor.get_metric('cpu_core_per_hour')
        self.assertEquals(cpu_metric, 'cpu_core_per_hour')

        mem_metric = self.accessor.get_metric('memory_gb_per_hour')
        self.assertEquals(mem_metric, 'memory_gb_per_hour')

        missing_metric = self.accessor.get_metric('wrong_metric')
        self.assertIsNone(missing_metric)

    def test_get_rates(self):
        """Test get metric."""
        cpu_rate = self.accessor.get_rates('cpu_core_per_hour')
        self.assertEquals(type(cpu_rate), dict)

        mem_rate = self.accessor.get_rates('memory_gb_per_hour')
        self.assertEquals(type(mem_rate), dict)

        missing_rate = self.accessor.get_rates('wrong_metric')
        self.assertIsNone(missing_rate)

    def test_get_cpu_rates(self):
        """Test get cpu rates."""
        cpu_rates = self.accessor.get_cpu_rates()
        self.assertEquals(type(cpu_rates), dict)
        self.assertEqual(cpu_rates.get('fixed_rate').get('value'), 1.5)

    def test_get_memory_rates(self):
        """Test get memory rates."""
        mem_rates = self.accessor.get_memory_rates()
        self.assertEquals(type(mem_rates), dict)
        self.assertEqual(mem_rates.get('fixed_rate').get('value'), 2.5)
