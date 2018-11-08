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
        self.cpu_rate = 1.5
        self.cpu_timeunit = 'nil'
        self.mem_rate = 2.5
        self.mem_timeunit = 'nil'
        self.creator.create_rate('cpu', self.cpu_rate, self.cpu_timeunit)
        self.creator.create_rate('memory', self.mem_rate, self.mem_timeunit)

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

    def test_get_price(self):
        """Test get metric."""
        cpu_price = self.accessor.get_price('cpu')
        self.assertEqual(round(cpu_price, 1), self.cpu_rate)
        mem_price = self.accessor.get_price('memory')
        self.assertEqual(round(mem_price, 1), self.mem_rate)

    def test_get_timeunit(self):
        """Test get timeunit."""
        cpu_timeunit = self.accessor.get_timeunit('cpu')
        self.assertEqual(cpu_timeunit, self.cpu_timeunit)

        mem_timeunit = self.accessor.get_timeunit('memory')
        self.assertEqual(mem_timeunit, self.mem_timeunit)

    def test_get_cpu_usage_rate(self):
        """Test to get cpu usage rate."""
        cpu_rate = self.accessor.get_cpu_usage_rate()
        self.assertEqual(cpu_rate, self.cpu_rate)

    def test_get_memory_usage_rate(self):
        """Test to get memory usage rate."""
        mem_rate = self.accessor.get_memory_usage_rate()
        self.assertEqual(mem_rate, self.mem_rate)
