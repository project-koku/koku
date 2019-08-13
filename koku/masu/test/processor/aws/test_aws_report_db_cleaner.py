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

"""Test the AWSReportDBCleaner utility object."""
import datetime
from dateutil import relativedelta

from tenant_schemas.utils import schema_context

from masu.database import AWS_CUR_TABLE_MAP
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.processor.aws.aws_report_db_cleaner import (
    AWSReportDBCleaner,
    AWSReportDBCleanerError,
)
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator


class AWSReportDBCleanerTest(MasuTestCase):
    """Test Cases for the AWSReportDBCleaner object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.common_accessor = ReportingCommonDBAccessor()
        cls.column_map = cls.common_accessor.column_map
        cls.accessor = AWSReportDBAccessor(
            schema=cls.schema, column_map=cls.column_map
        )
        cls.report_schema = cls.accessor.report_schema
        cls.creator = ReportObjectCreator(cls.schema, cls.column_map)
        cls.all_tables = list(AWS_CUR_TABLE_MAP.values())
        cls.foreign_key_tables = [
            AWS_CUR_TABLE_MAP['bill'],
            AWS_CUR_TABLE_MAP['product'],
            AWS_CUR_TABLE_MAP['pricing'],
            AWS_CUR_TABLE_MAP['reservation'],
        ]

    def setUp(self):
        """"Set up a test with database objects."""
        super().setUp()
        bill_id = self.creator.create_cost_entry_bill(provider_id=self.aws_provider.id)
        cost_entry_id = self.creator.create_cost_entry(bill_id)
        product_id = self.creator.create_cost_entry_product()
        pricing_id = self.creator.create_cost_entry_pricing()
        reservation_id = self.creator.create_cost_entry_reservation()
        self.creator.create_cost_entry_line_item(
            bill_id, cost_entry_id, product_id, pricing_id, reservation_id
        )

    def test_initializer(self):
        """Test initializer."""
        self.assertIsNotNone(self.report_schema)

    def test_purge_expired_report_data_on_date(self):
        """Test to remove report data on a provided date."""
        bill_table_name = AWS_CUR_TABLE_MAP['bill']
        line_item_table_name = AWS_CUR_TABLE_MAP['line_item']
        cost_entry_table_name = AWS_CUR_TABLE_MAP['cost_entry']

        cleaner = AWSReportDBCleaner(self.schema)
        with schema_context(self.schema):
            # Verify that data is cleared for a cutoff date == billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
            cutoff_date = first_bill.billing_period_start

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(
                self.accessor._get_db_obj_query(line_item_table_name).first()
            )
            self.assertIsNotNone(
                self.accessor._get_db_obj_query(cost_entry_table_name).first()
            )

        removed_data = cleaner.purge_expired_report_data(cutoff_date)

        self.assertEqual(len(removed_data), 1)
        self.assertEqual(
            removed_data[0].get('account_payer_id'), first_bill.payer_account_id
        )
        self.assertEqual(
            removed_data[0].get('billing_period_start'),
            str(first_bill.billing_period_start),
        )

        with schema_context(self.schema):
            self.assertIsNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNone(
                self.accessor._get_db_obj_query(cost_entry_table_name).first()
            )

    def test_purge_expired_report_data_before_date(self):
        """Test to remove report data before a provided date."""
        bill_table_name = AWS_CUR_TABLE_MAP['bill']
        line_item_table_name = AWS_CUR_TABLE_MAP['line_item']
        cost_entry_table_name = AWS_CUR_TABLE_MAP['cost_entry']

        cleaner = AWSReportDBCleaner(self.schema)

        with schema_context(self.schema):
            # Verify that data is not cleared for a cutoff date < billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
            cutoff_date = first_bill.billing_period_start
            earlier_cutoff = cutoff_date.replace(day=15) + relativedelta.relativedelta(
                months=-1
            )

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(
                self.accessor._get_db_obj_query(line_item_table_name).first()
            )
            self.assertIsNotNone(
                self.accessor._get_db_obj_query(cost_entry_table_name).first()
            )

        removed_data = cleaner.purge_expired_report_data(earlier_cutoff)

        self.assertEqual(len(removed_data), 0)

        with schema_context(self.schema):
            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(
                self.accessor._get_db_obj_query(line_item_table_name).first()
            )
            self.assertIsNotNone(
                self.accessor._get_db_obj_query(cost_entry_table_name).first()
            )

    def test_purge_expired_report_data_after_date(self):
        """Test to remove report data after a provided date."""
        bill_table_name = AWS_CUR_TABLE_MAP['bill']
        line_item_table_name = AWS_CUR_TABLE_MAP['line_item']
        cost_entry_table_name = AWS_CUR_TABLE_MAP['cost_entry']

        cleaner = AWSReportDBCleaner(self.schema)

        with schema_context(self.schema):
            # Verify that data is cleared for a cutoff date > billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
            cutoff_date = first_bill.billing_period_start
            later_date = cutoff_date + relativedelta.relativedelta(months=+1)
            later_cutoff = later_date.replace(month=later_date.month, day=15)

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(
                self.accessor._get_db_obj_query(line_item_table_name).first()
            )
            self.assertIsNotNone(
                self.accessor._get_db_obj_query(cost_entry_table_name).first()
            )

        removed_data = cleaner.purge_expired_report_data(later_cutoff)

        self.assertEqual(len(removed_data), 1)
        self.assertEqual(
            removed_data[0].get('account_payer_id'), first_bill.payer_account_id
        )
        self.assertEqual(
            removed_data[0].get('billing_period_start'),
            str(first_bill.billing_period_start),
        )
        with schema_context(self.schema):
            self.assertIsNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNone(
                self.accessor._get_db_obj_query(cost_entry_table_name).first()
            )

    def test_purge_expired_report_data_on_date_simulate(self):
        """Test to simulate removing report data on a provided date."""
        bill_table_name = AWS_CUR_TABLE_MAP['bill']
        line_item_table_name = AWS_CUR_TABLE_MAP['line_item']
        cost_entry_table_name = AWS_CUR_TABLE_MAP['cost_entry']

        cleaner = AWSReportDBCleaner(self.schema)

        # Verify that data is cleared for a cutoff date == billing_period_start
        with schema_context(self.schema):
            first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
            cutoff_date = first_bill.billing_period_start

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(
                self.accessor._get_db_obj_query(line_item_table_name).first()
            )
            self.assertIsNotNone(
                self.accessor._get_db_obj_query(cost_entry_table_name).first()
            )

        removed_data = cleaner.purge_expired_report_data(cutoff_date, simulate=True)

        self.assertEqual(len(removed_data), 1)
        self.assertEqual(
            removed_data[0].get('account_payer_id'), first_bill.payer_account_id
        )
        self.assertEqual(
            removed_data[0].get('billing_period_start'),
            str(first_bill.billing_period_start),
        )

        with schema_context(self.schema):
            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(
                self.accessor._get_db_obj_query(line_item_table_name).first()
            )
            self.assertIsNotNone(
                self.accessor._get_db_obj_query(cost_entry_table_name).first()
            )

    def test_purge_expired_report_data_for_provider(self):
        """Test that the provider_id deletes all data for the provider."""
        bill_table_name = AWS_CUR_TABLE_MAP['bill']
        line_item_table_name = AWS_CUR_TABLE_MAP['line_item']
        cost_entry_table_name = AWS_CUR_TABLE_MAP['cost_entry']

        cleaner = AWSReportDBCleaner(self.schema)

        with schema_context(self.schema):
            # Verify that data is cleared for a cutoff date == billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
            cutoff_date = first_bill.billing_period_start

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(
                self.accessor._get_db_obj_query(line_item_table_name).first()
            )
            self.assertIsNotNone(
                self.accessor._get_db_obj_query(cost_entry_table_name).first()
            )

        removed_data = cleaner.purge_expired_report_data(provider_id=self.aws_provider.id)

        self.assertEqual(len(removed_data), 1)
        self.assertEqual(
            removed_data[0].get('account_payer_id'), first_bill.payer_account_id
        )
        self.assertEqual(
            removed_data[0].get('billing_period_start'),
            str(first_bill.billing_period_start),
        )

        with schema_context(self.schema):
            self.assertIsNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNone(
                self.accessor._get_db_obj_query(cost_entry_table_name).first()
            )

    def test_purge_expired_report_data_no_args(self):
        """Test that the provider_id deletes all data for the provider."""

        cleaner = AWSReportDBCleaner(self.schema)
        with self.assertRaises(AWSReportDBCleanerError):
            removed_data = cleaner.purge_expired_report_data()

    def test_purge_expired_report_data_both_args(self):
        """Test that the provider_id deletes all data for the provider."""
        now = datetime.datetime.utcnow()
        cleaner = AWSReportDBCleaner(self.schema)
        with self.assertRaises(AWSReportDBCleanerError):
            removed_data = cleaner.purge_expired_report_data(
                expired_date=now, provider_id=self.aws_provider.id
            )
