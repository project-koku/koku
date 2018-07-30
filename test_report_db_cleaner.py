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

"""Test the ReportDBAccessor utility object."""
import datetime

from masu.database import AWS_CUR_TABLE_MAP
from masu.database.report_db_accessor import ReportDBAccessor
from masu.database.report_db_cleaner import ReportDBCleaner
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from tests import MasuTestCase
from tests.database.helpers import ReportObjectCreator


class ReportDBCleanerTest(MasuTestCase):
    """Test Cases for the ReportDBCleaner object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        cls.common_accessor = ReportingCommonDBAccessor()
        cls.column_map = cls.common_accessor.column_map
        cls.accessor = ReportDBAccessor(
            schema='testcustomer',
            column_map=cls.column_map
        )
        cls.report_schema = cls.accessor.report_schema
        cls.creator = ReportObjectCreator(
            cls.accessor,
            cls.column_map,
            cls.report_schema.column_types
        )
        cls.all_tables = list(AWS_CUR_TABLE_MAP.values())
        cls.foreign_key_tables = [
            AWS_CUR_TABLE_MAP['bill'],
            AWS_CUR_TABLE_MAP['product'],
            AWS_CUR_TABLE_MAP['pricing'],
            AWS_CUR_TABLE_MAP['reservation']
        ]

    def setUp(self):
        """"Set up a test with database objects."""
        bill_id = self.creator.create_cost_entry_bill()
        cost_entry_id = self.creator.create_cost_entry(bill_id)
        product_id = self.creator.create_cost_entry_product()
        pricing_id = self.creator.create_cost_entry_pricing()
        reservation_id = self.creator.create_cost_entry_reservation()
        self.creator.create_cost_entry_line_item(
            bill_id,
            cost_entry_id,
            product_id,
            pricing_id,
            reservation_id
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

    def test_purge_expired_report_data_on_date(self):
        """Test to remove report data on a provided date."""
        bill_table_name = AWS_CUR_TABLE_MAP['bill']
        line_item_table_name = AWS_CUR_TABLE_MAP['line_item']
        cost_entry_table_name = AWS_CUR_TABLE_MAP['cost_entry']

        cleaner = ReportDBCleaner('testcustomer')

        # Verify that data is cleared for a cutoff date == billing_period_start
        first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
        cutoff_date = first_bill.billing_period_start

        self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
        self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
        self.assertIsNotNone(self.accessor._get_db_obj_query(cost_entry_table_name).first())

        cleaner.purge_expired_report_data(cutoff_date)

        self.assertIsNone(self.accessor._get_db_obj_query(bill_table_name).first())
        self.assertIsNone(self.accessor._get_db_obj_query(line_item_table_name).first())
        self.assertIsNone(self.accessor._get_db_obj_query(cost_entry_table_name).first())

    def test_purge_expired_report_data_before_date(self):
        """Test to remove report data before a provided date."""
        bill_table_name = AWS_CUR_TABLE_MAP['bill']
        line_item_table_name = AWS_CUR_TABLE_MAP['line_item']
        cost_entry_table_name = AWS_CUR_TABLE_MAP['cost_entry']

        cleaner = ReportDBCleaner('testcustomer')

        # Verify that data is cleared for a cutoff date < billing_period_start
        first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
        cutoff_date = first_bill.billing_period_start
        earlier_cutoff = cutoff_date.replace(month=cutoff_date.month-1)

        self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
        self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
        self.assertIsNotNone(self.accessor._get_db_obj_query(cost_entry_table_name).first())

        cleaner.purge_expired_report_data(earlier_cutoff)

        self.assertIsNone(self.accessor._get_db_obj_query(bill_table_name).first())
        self.assertIsNone(self.accessor._get_db_obj_query(line_item_table_name).first())
        self.assertIsNone(self.accessor._get_db_obj_query(cost_entry_table_name).first())

    def test_purge_expired_report_data_after_date(self):
        """Test to remove report data after a provided date."""
        bill_table_name = AWS_CUR_TABLE_MAP['bill']
        line_item_table_name = AWS_CUR_TABLE_MAP['line_item']
        cost_entry_table_name = AWS_CUR_TABLE_MAP['cost_entry']

        cleaner = ReportDBCleaner('testcustomer')

        # Verify that data is not cleared for a cutoff date > billing_period_start
        first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
        cutoff_date = first_bill.billing_period_start
        later_cutoff = cutoff_date.replace(month=cutoff_date.month+1)

        self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
        self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
        self.assertIsNotNone(self.accessor._get_db_obj_query(cost_entry_table_name).first())

        cleaner.purge_expired_report_data(later_cutoff)

        self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
        self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
        self.assertIsNotNone(self.accessor._get_db_obj_query(cost_entry_table_name).first())
