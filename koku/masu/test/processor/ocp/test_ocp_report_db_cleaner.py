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

"""Test the OCPReportDBCleaner utility object."""
import datetime

from dateutil import relativedelta

from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.processor.ocp.ocp_report_db_cleaner import (
    OCPReportDBCleaner,
    OCPReportDBCleanerError,
)
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from tests import MasuTestCase
from tests.database.helpers import ReportObjectCreator


class OCPReportDBCleanerTest(MasuTestCase):
    """Test Cases for the OCPReportDBCleaner object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        cls.common_accessor = ReportingCommonDBAccessor()
        cls.column_map = cls.common_accessor.column_map
        cls.accessor = OCPReportDBAccessor(
            schema='acct10001', column_map=cls.column_map
        )
        cls.report_schema = cls.accessor.report_schema
        cls.creator = ReportObjectCreator(
            cls.accessor, cls.column_map, cls.report_schema.column_types
        )
        cls.all_tables = list(OCP_REPORT_TABLE_MAP.values())

    @classmethod
    def tearDownClass(cls):
        """Close the DB session."""
        cls.common_accessor.close_session()
        cls.accessor.close_session()

    def setUp(self):
        """"Set up a test with database objects."""
        reporting_period = self.creator.create_ocp_report_period()
        report = self.creator.create_ocp_report(reporting_period)
        self.creator.create_ocp_usage_line_item(reporting_period, report)
        self.creator.create_ocp_storage_line_item(reporting_period, report)

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

    def test_purge_expired_report_data_on_date(self):
        """Test to remove report data on a provided date."""
        report_period_table_name = OCP_REPORT_TABLE_MAP['report_period']
        report_table_name = OCP_REPORT_TABLE_MAP['report']
        line_item_table_name = OCP_REPORT_TABLE_MAP['line_item']
        storage_line_item_table_name = OCP_REPORT_TABLE_MAP['storage_line_item']

        cleaner = OCPReportDBCleaner('acct10001')

        # Verify that data is cleared for a cutoff date == billing_period_start
        first_period = self.accessor._get_db_obj_query(report_period_table_name).first()
        cutoff_date = first_period.report_period_start

        self.assertIsNotNone(
            self.accessor._get_db_obj_query(report_period_table_name).first()
        )
        self.assertIsNotNone(self.accessor._get_db_obj_query(report_table_name).first())
        self.assertIsNotNone(
            self.accessor._get_db_obj_query(line_item_table_name).first()
        )
        self.assertIsNotNone(
            self.accessor._get_db_obj_query(storage_line_item_table_name).first()
        )

        removed_data = cleaner.purge_expired_report_data(cutoff_date)

        self.assertEqual(len(removed_data), 1)
        self.assertEqual(removed_data[0].get('usage_period_id'), first_period.id)
        self.assertEqual(
            removed_data[0].get('interval_start'), str(first_period.report_period_start)
        )

        self.assertIsNone(
            self.accessor._get_db_obj_query(report_period_table_name).first()
        )
        self.assertIsNone(self.accessor._get_db_obj_query(report_table_name).first())
        self.assertIsNone(self.accessor._get_db_obj_query(line_item_table_name).first())
        self.assertIsNone(
            self.accessor._get_db_obj_query(storage_line_item_table_name).first()
        )

    def test_purge_expired_report_data_before_date(self):
        """Test to remove report data before a provided date."""
        report_period_table_name = OCP_REPORT_TABLE_MAP['report_period']
        report_table_name = OCP_REPORT_TABLE_MAP['report']
        line_item_table_name = OCP_REPORT_TABLE_MAP['line_item']
        storage_line_item_table_name = OCP_REPORT_TABLE_MAP['storage_line_item']

        cleaner = OCPReportDBCleaner('acct10001')

        # Verify that data is not cleared for a cutoff date < billing_period_start
        first_period = self.accessor._get_db_obj_query(report_period_table_name).first()
        cutoff_date = first_period.report_period_start
        earlier_date = cutoff_date + relativedelta.relativedelta(months=-1)
        earlier_cutoff = earlier_date.replace(month=earlier_date.month, day=15)

        self.assertIsNotNone(
            self.accessor._get_db_obj_query(report_period_table_name).first()
        )
        self.assertIsNotNone(self.accessor._get_db_obj_query(report_table_name).first())
        self.assertIsNotNone(
            self.accessor._get_db_obj_query(line_item_table_name).first()
        )
        self.assertIsNotNone(
            self.accessor._get_db_obj_query(storage_line_item_table_name).first()
        )

        removed_data = cleaner.purge_expired_report_data(earlier_cutoff)

        self.assertEqual(len(removed_data), 0)

        self.assertIsNotNone(
            self.accessor._get_db_obj_query(report_period_table_name).first()
        )
        self.assertIsNotNone(self.accessor._get_db_obj_query(report_table_name).first())
        self.assertIsNotNone(
            self.accessor._get_db_obj_query(line_item_table_name).first()
        )
        self.assertIsNotNone(
            self.accessor._get_db_obj_query(storage_line_item_table_name).first()
        )

    def test_purge_expired_report_data_after_date(self):
        """Test to remove report data after a provided date."""
        report_period_table_name = OCP_REPORT_TABLE_MAP['report_period']
        report_table_name = OCP_REPORT_TABLE_MAP['report']
        line_item_table_name = OCP_REPORT_TABLE_MAP['line_item']
        storage_line_item_table_name = OCP_REPORT_TABLE_MAP['storage_line_item']

        cleaner = OCPReportDBCleaner('acct10001')

        # Verify that data is cleared for a cutoff date > billing_period_start
        first_period = self.accessor._get_db_obj_query(report_period_table_name).first()
        cutoff_date = first_period.report_period_start
        later_date = cutoff_date + relativedelta.relativedelta(months=+1)
        later_cutoff = later_date.replace(day=15)

        self.assertIsNotNone(
            self.accessor._get_db_obj_query(report_period_table_name).first()
        )
        self.assertIsNotNone(self.accessor._get_db_obj_query(report_table_name).first())
        self.assertIsNotNone(
            self.accessor._get_db_obj_query(line_item_table_name).first()
        )
        self.assertIsNotNone(
            self.accessor._get_db_obj_query(storage_line_item_table_name).first()
        )

        removed_data = cleaner.purge_expired_report_data(later_cutoff)
        self.assertEqual(len(removed_data), 1)
        self.assertEqual(removed_data[0].get('usage_period_id'), first_period.id)
        self.assertEqual(
            removed_data[0].get('interval_start'), str(first_period.report_period_start)
        )

        self.assertIsNone(
            self.accessor._get_db_obj_query(report_period_table_name).first()
        )
        self.assertIsNone(self.accessor._get_db_obj_query(report_table_name).first())
        self.assertIsNone(self.accessor._get_db_obj_query(line_item_table_name).first())
        self.assertIsNone(
            self.accessor._get_db_obj_query(storage_line_item_table_name).first()
        )

    def test_purge_expired_report_data_on_date_simulate(self):
        """Test to simulate removing report data on a provided date."""
        report_period_table_name = OCP_REPORT_TABLE_MAP['report_period']
        report_table_name = OCP_REPORT_TABLE_MAP['report']
        line_item_table_name = OCP_REPORT_TABLE_MAP['line_item']
        storage_line_item_table_name = OCP_REPORT_TABLE_MAP['storage_line_item']

        cleaner = OCPReportDBCleaner('acct10001')

        # Verify that data is cleared for a cutoff date == billing_period_start
        first_period = self.accessor._get_db_obj_query(report_period_table_name).first()
        cutoff_date = first_period.report_period_start

        self.assertIsNotNone(
            self.accessor._get_db_obj_query(report_period_table_name).first()
        )
        self.assertIsNotNone(self.accessor._get_db_obj_query(report_table_name).first())
        self.assertIsNotNone(
            self.accessor._get_db_obj_query(line_item_table_name).first()
        )
        self.assertIsNotNone(
            self.accessor._get_db_obj_query(storage_line_item_table_name).first()
        )

        removed_data = cleaner.purge_expired_report_data(cutoff_date, simulate=True)

        self.assertEqual(len(removed_data), 1)
        self.assertEqual(removed_data[0].get('usage_period_id'), first_period.id)
        self.assertEqual(
            removed_data[0].get('interval_start'), str(first_period.report_period_start)
        )

        self.assertIsNotNone(
            self.accessor._get_db_obj_query(report_period_table_name).first()
        )
        self.assertIsNotNone(self.accessor._get_db_obj_query(report_table_name).first())
        self.assertIsNotNone(
            self.accessor._get_db_obj_query(line_item_table_name).first()
        )
        self.assertIsNotNone(
            self.accessor._get_db_obj_query(storage_line_item_table_name).first()
        )

    def test_purge_expired_report_data_for_provider(self):
        """Test that the provider_id deletes all data for the provider."""
        report_period_table_name = OCP_REPORT_TABLE_MAP['report_period']
        report_table_name = OCP_REPORT_TABLE_MAP['report']
        line_item_table_name = OCP_REPORT_TABLE_MAP['line_item']
        storage_line_item_table_name = OCP_REPORT_TABLE_MAP['storage_line_item']

        cleaner = OCPReportDBCleaner('acct10001')

        # Verify that data is cleared for a cutoff date == billing_period_start
        first_period = self.accessor._get_db_obj_query(report_period_table_name).first()

        self.assertIsNotNone(
            self.accessor._get_db_obj_query(report_period_table_name).first()
        )
        self.assertIsNotNone(self.accessor._get_db_obj_query(report_table_name).first())
        self.assertIsNotNone(
            self.accessor._get_db_obj_query(line_item_table_name).first()
        )
        self.assertIsNotNone(
            self.accessor._get_db_obj_query(storage_line_item_table_name).first()
        )

        removed_data = cleaner.purge_expired_report_data(provider_id=1)

        self.assertEqual(len(removed_data), 1)
        self.assertEqual(removed_data[0].get('usage_period_id'), first_period.id)
        self.assertEqual(
            removed_data[0].get('interval_start'), str(first_period.report_period_start)
        )

        self.assertIsNone(
            self.accessor._get_db_obj_query(report_period_table_name).first()
        )
        self.assertIsNone(self.accessor._get_db_obj_query(report_table_name).first())
        self.assertIsNone(self.accessor._get_db_obj_query(line_item_table_name).first())
        self.assertIsNone(
            self.accessor._get_db_obj_query(storage_line_item_table_name).first()
        )

    def test_purge_expired_report_data_no_args(self):
        """Test that the provider_id deletes all data for the provider."""

        cleaner = OCPReportDBCleaner('acct10001')
        with self.assertRaises(OCPReportDBCleanerError):
            cleaner.purge_expired_report_data()

    def test_purge_expired_report_data_both_args(self):
        """Test that the provider_id deletes all data for the provider."""
        now = datetime.datetime.utcnow()
        cleaner = OCPReportDBCleaner('acct10001')
        with self.assertRaises(OCPReportDBCleanerError):
            cleaner.purge_expired_report_data(expired_date=now, provider_id=1)
