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
from dateutil import relativedelta
import datetime
from decimal import Decimal, InvalidOperation
import types
import random
import string
import uuid

import psycopg2
from sqlalchemy.orm.query import Query
from sqlalchemy.sql import func


from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.report_db_accessor_base import ReportSchema
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from tests import MasuTestCase
from tests.database.helpers import ReportObjectCreator


class OCPReportDBAccessorTest(MasuTestCase):
    """Test Cases for the OCPReportDBAccessor object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        cls.common_accessor = ReportingCommonDBAccessor()
        cls.column_map = cls.common_accessor.column_map
        cls.accessor = OCPReportDBAccessor(
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

    def test_get_db_obj_query_default(self):
        """Test that a query is returned."""
        table_name = random.choice(self.all_tables)

        query = self.accessor._get_db_obj_query(table_name)

        self.assertIsInstance(query, Query)

    def test_get_db_obj_query_with_columns(self):
        """Test that a query is returned with limited columns."""
        table_name = OCP_REPORT_TABLE_MAP['line_item']
        columns = list(self.column_map[table_name].values())

        selected_columns = [random.choice(columns) for _ in range(2)]
        missing_columns = set(columns).difference(selected_columns)

        query = self.accessor._get_db_obj_query(
            table_name,
            columns=selected_columns
        )

        self.assertIsInstance(query, Query)

        result = query.first()

        for column in selected_columns:
            self.assertTrue(hasattr(result, column))

        for column in missing_columns:
            self.assertFalse(hasattr(result, column))

    def test_get_current_usage_report(self):
        """Test that the most recent usage report is returned."""
        current_report = self.accessor.get_current_usage_report()
        self.assertIsNotNone(current_report.interval_start)
        self.assertIsNotNone(current_report.interval_end)
        self.assertIsNotNone(current_report.report_period_id)

    def test_get_usage_report_before_date(self):
        """Test that the recent usage report is returned before given date."""
        current_report = self.accessor.get_current_usage_report()
        self.assertIsNotNone(current_report.interval_start)
        start_date = current_report.interval_start

        before_target = start_date + relativedelta.relativedelta(months=+1)
        query = self.accessor.get_usage_report_before_date(before_target)
        report = query.first()
        self.assertTrue(report.interval_start < before_target)

        after_date = start_date + relativedelta.relativedelta(months=-1)
        query = self.accessor.get_usage_report_before_date(after_date)
        report = query.first()
        self.assertIsNone(report)

    def test_get_lineitem_query_for_reportid(self):
        """Test that the line item data is returned given a report_id."""
        current_report = self.accessor.get_current_usage_report()
        self.assertIsNotNone(current_report.report_period_id)

        report_id = current_report.id
        line_item_query = self.accessor.get_lineitem_query_for_reportid(report_id)
        self.assertEqual(line_item_query.count(), 1)
        self.assertEqual(line_item_query.first().report_id, report_id)
        
        query_report = line_item_query.first()
        self.assertIsNotNone(query_report.namespace)
        self.assertIsNotNone(query_report.pod)
        self.assertIsNotNone(query_report.node)
        self.assertIsNotNone(query_report.usage_start)
        self.assertIsNotNone(query_report.usage_end)
        self.assertIsNotNone(query_report.pod_usage_cpu_core_seconds)
        self.assertIsNotNone(query_report.pod_request_cpu_core_seconds)
        self.assertIsNotNone(query_report.pod_limit_cpu_cores)
        self.assertIsNotNone(query_report.pod_usage_memory_byte_seconds)
        self.assertIsNotNone(query_report.pod_request_memory_byte_seconds)
        self.assertIsNotNone(query_report.pod_limit_memory_bytes)
