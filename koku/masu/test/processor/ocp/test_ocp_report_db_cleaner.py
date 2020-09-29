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
import logging

from dateutil import relativedelta
from django_tenants.utils import schema_context

from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.processor.ocp.ocp_report_db_cleaner import OCPReportDBCleaner
from masu.processor.ocp.ocp_report_db_cleaner import OCPReportDBCleanerError
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator

LOG = logging.getLogger(__name__)


class OCPReportDBCleanerTest(MasuTestCase):
    """Test Cases for the OCPReportDBCleaner object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.accessor = OCPReportDBAccessor(schema=cls.schema)
        cls.report_schema = cls.accessor.report_schema
        cls.creator = ReportObjectCreator(cls.schema)
        cls.all_tables = list(OCP_REPORT_TABLE_MAP.values())

    def test_initializer(self):
        """Test initializer."""
        self.assertIsNotNone(self.report_schema)

    def test_purge_expired_report_data_on_date(self):
        """Test to remove report data on a provided date."""
        report_period_table_name = OCP_REPORT_TABLE_MAP["report_period"]
        report_table_name = OCP_REPORT_TABLE_MAP["report"]
        line_item_table_name = OCP_REPORT_TABLE_MAP["line_item"]
        storage_line_item_table_name = OCP_REPORT_TABLE_MAP["storage_line_item"]

        cleaner = OCPReportDBCleaner(self.schema)

        with schema_context(self.schema):
            # Verify that data is cleared for a cutoff date == billing_period_start
            first_period = (
                self.accessor._get_db_obj_query(report_period_table_name).order_by("-report_period_start").first()
            )
            cutoff_date = first_period.report_period_start
            expected_count = (
                self.accessor._get_db_obj_query(report_period_table_name)
                .filter(report_period_start__lte=cutoff_date)
                .count()
            )

            self.assertIsNotNone(self.accessor._get_db_obj_query(report_period_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(report_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(storage_line_item_table_name).first())

        removed_data = cleaner.purge_expired_report_data(cutoff_date)

        self.assertEqual(len(removed_data), expected_count)
        self.assertIn(first_period.id, [item.get("usage_period_id") for item in removed_data])
        self.assertIn(str(first_period.report_period_start), [item.get("interval_start") for item in removed_data])

        with schema_context(self.schema):
            self.assertIsNone(self.accessor._get_db_obj_query(report_period_table_name).first())
            self.assertIsNone(self.accessor._get_db_obj_query(report_table_name).first())
            self.assertIsNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNone(self.accessor._get_db_obj_query(storage_line_item_table_name).first())

    def test_purge_expired_report_data_before_date(self):
        """Test to remove report data before a provided date."""
        report_period_table_name = OCP_REPORT_TABLE_MAP["report_period"]
        report_table_name = OCP_REPORT_TABLE_MAP["report"]
        line_item_table_name = OCP_REPORT_TABLE_MAP["line_item"]
        storage_line_item_table_name = OCP_REPORT_TABLE_MAP["storage_line_item"]

        cleaner = OCPReportDBCleaner(self.schema)

        with schema_context(self.schema):
            # Verify that data is not cleared for a cutoff date < billing_period_start
            first_period = (
                self.accessor._get_db_obj_query(report_period_table_name).order_by("-report_period_start").first()
            )
            cutoff_date = first_period.report_period_start
            earlier_date = cutoff_date + relativedelta.relativedelta(months=-1)
            earlier_cutoff = earlier_date.replace(month=earlier_date.month, day=15)
            expected_count = (
                self.accessor._get_db_obj_query(report_period_table_name)
                .filter(report_period_start__lte=earlier_cutoff)
                .count()
            )

            self.assertIsNotNone(self.accessor._get_db_obj_query(report_period_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(report_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(storage_line_item_table_name).first())

        removed_data = cleaner.purge_expired_report_data(earlier_cutoff)

        self.assertEqual(len(removed_data), expected_count)

        with schema_context(self.schema):
            self.assertIsNotNone(self.accessor._get_db_obj_query(report_period_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(report_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(storage_line_item_table_name).first())

    def test_purge_expired_report_data_after_date(self):
        """Test to remove report data after a provided date."""
        report_period_table_name = OCP_REPORT_TABLE_MAP["report_period"]
        report_table_name = OCP_REPORT_TABLE_MAP["report"]
        line_item_table_name = OCP_REPORT_TABLE_MAP["line_item"]
        storage_line_item_table_name = OCP_REPORT_TABLE_MAP["storage_line_item"]

        cleaner = OCPReportDBCleaner(self.schema)

        with schema_context(self.schema):
            # Verify that data is cleared for a cutoff date > billing_period_start
            first_period = (
                self.accessor._get_db_obj_query(report_period_table_name).order_by("-report_period_start").first()
            )
            cutoff_date = first_period.report_period_start
            later_date = cutoff_date + relativedelta.relativedelta(months=+1)
            later_cutoff = later_date.replace(day=15)
            expected_count = (
                self.accessor._get_db_obj_query(report_period_table_name)
                .filter(report_period_start__lte=later_cutoff)
                .count()
            )

            self.assertIsNotNone(self.accessor._get_db_obj_query(report_period_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(report_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(storage_line_item_table_name).first())

        removed_data = cleaner.purge_expired_report_data(later_cutoff)
        self.assertEqual(len(removed_data), expected_count)
        self.assertIn(first_period.id, [item.get("usage_period_id") for item in removed_data])
        self.assertIn(str(first_period.report_period_start), [item.get("interval_start") for item in removed_data])

        with schema_context(self.schema):
            self.assertIsNone(self.accessor._get_db_obj_query(report_period_table_name).first())
            self.assertIsNone(self.accessor._get_db_obj_query(report_table_name).first())
            self.assertIsNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNone(self.accessor._get_db_obj_query(storage_line_item_table_name).first())

    def test_purge_expired_report_data_on_date_simulate(self):
        """Test to simulate removing report data on a provided date."""
        report_period_table_name = OCP_REPORT_TABLE_MAP["report_period"]
        report_table_name = OCP_REPORT_TABLE_MAP["report"]
        line_item_table_name = OCP_REPORT_TABLE_MAP["line_item"]
        storage_line_item_table_name = OCP_REPORT_TABLE_MAP["storage_line_item"]

        cleaner = OCPReportDBCleaner(self.schema)

        # Verify that data is cleared for a cutoff date == billing_period_start
        with schema_context(self.schema):
            first_period = (
                self.accessor._get_db_obj_query(report_period_table_name).order_by("-report_period_start").first()
            )
            cutoff_date = first_period.report_period_start
            expected_count = (
                self.accessor._get_db_obj_query(report_period_table_name)
                .filter(report_period_start__lte=cutoff_date)
                .count()
            )

            self.assertIsNotNone(self.accessor._get_db_obj_query(report_period_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(report_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(storage_line_item_table_name).first())

        removed_data = cleaner.purge_expired_report_data(cutoff_date, simulate=True)

        self.assertEqual(len(removed_data), expected_count)
        self.assertIn(first_period.id, [item.get("usage_period_id") for item in removed_data])
        self.assertIn(str(first_period.report_period_start), [item.get("interval_start") for item in removed_data])

        with schema_context(self.schema):
            self.assertIsNotNone(self.accessor._get_db_obj_query(report_period_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(report_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(storage_line_item_table_name).first())

    def test_purge_expired_report_data_for_provider(self):
        """Test that the provider_uuid deletes all data for the provider."""
        report_period_table_name = OCP_REPORT_TABLE_MAP["report_period"]
        report_table_name = OCP_REPORT_TABLE_MAP["report"]
        line_item_table_name = OCP_REPORT_TABLE_MAP["line_item"]
        storage_line_item_table_name = OCP_REPORT_TABLE_MAP["storage_line_item"]

        cleaner = OCPReportDBCleaner(self.schema)

        with schema_context(self.schema):
            # Verify that data is cleared for a cutoff date == billing_period_start
            first_period = (
                self.accessor._get_db_obj_query(report_period_table_name)
                .filter(provider_id=self.ocp_provider_uuid)
                .order_by("-report_period_start")
                .first()
            )

            self.assertIsNotNone(self.accessor._get_db_obj_query(report_period_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(report_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(storage_line_item_table_name).first())

            expected_count = (
                self.accessor._get_db_obj_query(report_period_table_name)
                .filter(provider_id=self.ocp_provider_uuid)
                .count()
            )

        removed_data = cleaner.purge_expired_report_data(provider_uuid=self.ocp_provider_uuid)

        self.assertEqual(len(removed_data), expected_count)
        self.assertIn(first_period.id, [item.get("usage_period_id") for item in removed_data])
        self.assertIn(str(first_period.report_period_start), [item.get("interval_start") for item in removed_data])

    def test_purge_expired_report_data_no_args(self):
        """Test that the provider_uuid deletes all data for the provider."""
        cleaner = OCPReportDBCleaner(self.schema)
        with self.assertRaises(OCPReportDBCleanerError):
            cleaner.purge_expired_report_data()

    def test_purge_expired_report_data_both_args(self):
        """Test that the provider_uuid deletes all data for the provider."""
        now = datetime.datetime.utcnow()
        cleaner = OCPReportDBCleaner(self.schema)
        with self.assertRaises(OCPReportDBCleanerError):
            cleaner.purge_expired_report_data(expired_date=now, provider_uuid=self.ocp_provider_uuid)

    def test_purge_expired_line_item_on_date(self):
        """Test to remove report data on a provided date."""
        report_period_table_name = OCP_REPORT_TABLE_MAP["report_period"]
        report_table_name = OCP_REPORT_TABLE_MAP["report"]
        line_item_table_name = OCP_REPORT_TABLE_MAP["line_item"]
        storage_line_item_table_name = OCP_REPORT_TABLE_MAP["storage_line_item"]

        cleaner = OCPReportDBCleaner(self.schema)

        with schema_context(self.schema):
            # Verify that data is cleared for a cutoff date == billing_period_start
            first_period = (
                self.accessor._get_db_obj_query(report_period_table_name).order_by("-report_period_start").first()
            )
            cutoff_date = first_period.report_period_start
            expected_count = (
                self.accessor._get_db_obj_query(report_period_table_name)
                .filter(report_period_start__lte=cutoff_date)
                .count()
            )

            self.assertIsNotNone(self.accessor._get_db_obj_query(report_period_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(report_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(storage_line_item_table_name).first())

        removed_data = cleaner.purge_expired_line_item(cutoff_date)

        self.assertEqual(len(removed_data), expected_count)
        self.assertIn(first_period.id, [item.get("usage_period_id") for item in removed_data])
        self.assertIn(str(first_period.report_period_start), [item.get("interval_start") for item in removed_data])

        with schema_context(self.schema):
            self.assertIsNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(report_period_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(report_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(storage_line_item_table_name).first())

    def test_purge_expired_line_item_before_date(self):
        """Test to remove report data before a provided date."""
        report_period_table_name = OCP_REPORT_TABLE_MAP["report_period"]
        report_table_name = OCP_REPORT_TABLE_MAP["report"]
        line_item_table_name = OCP_REPORT_TABLE_MAP["line_item"]
        storage_line_item_table_name = OCP_REPORT_TABLE_MAP["storage_line_item"]

        cleaner = OCPReportDBCleaner(self.schema)

        with schema_context(self.schema):
            # Verify that data is not cleared for a cutoff date < billing_period_start
            first_period = (
                self.accessor._get_db_obj_query(report_period_table_name).order_by("-report_period_start").first()
            )
            cutoff_date = first_period.report_period_start
            earlier_date = cutoff_date + relativedelta.relativedelta(months=-1)
            earlier_cutoff = earlier_date.replace(month=earlier_date.month, day=15)
            expected_count = (
                self.accessor._get_db_obj_query(report_period_table_name)
                .filter(report_period_start__lte=earlier_cutoff)
                .count()
            )

            self.assertIsNotNone(self.accessor._get_db_obj_query(report_period_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(report_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(storage_line_item_table_name).first())

        removed_data = cleaner.purge_expired_line_item(earlier_cutoff)

        self.assertEqual(len(removed_data), expected_count)

        with schema_context(self.schema):
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(report_period_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(report_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(storage_line_item_table_name).first())

    def test_purge_expired_line_item_after_date(self):
        """Test to remove report data after a provided date."""
        report_period_table_name = OCP_REPORT_TABLE_MAP["report_period"]
        report_table_name = OCP_REPORT_TABLE_MAP["report"]
        line_item_table_name = OCP_REPORT_TABLE_MAP["line_item"]
        storage_line_item_table_name = OCP_REPORT_TABLE_MAP["storage_line_item"]

        cleaner = OCPReportDBCleaner(self.schema)

        with schema_context(self.schema):
            # Verify that data is cleared for a cutoff date > billing_period_start
            first_period = (
                self.accessor._get_db_obj_query(report_period_table_name).order_by("-report_period_start").first()
            )
            cutoff_date = first_period.report_period_start
            later_date = cutoff_date + relativedelta.relativedelta(months=+1)
            later_cutoff = later_date.replace(day=15)
            expected_count = (
                self.accessor._get_db_obj_query(report_period_table_name)
                .filter(report_period_start__lte=later_cutoff)
                .count()
            )

            self.assertIsNotNone(self.accessor._get_db_obj_query(report_period_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(report_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(storage_line_item_table_name).first())

        removed_data = cleaner.purge_expired_line_item(later_cutoff)
        self.assertEqual(len(removed_data), expected_count)
        self.assertIn(first_period.id, [item.get("usage_period_id") for item in removed_data])
        self.assertIn(str(first_period.report_period_start), [item.get("interval_start") for item in removed_data])

        with schema_context(self.schema):
            self.assertIsNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(report_period_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(report_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(storage_line_item_table_name).first())

    def test_purge_expired_line_item_on_date_simulate(self):
        """Test to simulate removing report data on a provided date."""
        report_period_table_name = OCP_REPORT_TABLE_MAP["report_period"]
        report_table_name = OCP_REPORT_TABLE_MAP["report"]
        line_item_table_name = OCP_REPORT_TABLE_MAP["line_item"]
        storage_line_item_table_name = OCP_REPORT_TABLE_MAP["storage_line_item"]

        cleaner = OCPReportDBCleaner(self.schema)

        # Verify that data is cleared for a cutoff date == billing_period_start
        with schema_context(self.schema):
            first_period = (
                self.accessor._get_db_obj_query(report_period_table_name).order_by("-report_period_start").first()
            )
            cutoff_date = first_period.report_period_start
            expected_count = (
                self.accessor._get_db_obj_query(report_period_table_name)
                .filter(report_period_start__lte=cutoff_date)
                .count()
            )

            self.assertIsNotNone(self.accessor._get_db_obj_query(report_period_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(report_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(storage_line_item_table_name).first())

        removed_data = cleaner.purge_expired_line_item(cutoff_date, simulate=True)

        self.assertEqual(len(removed_data), expected_count)
        self.assertIn(first_period.id, [item.get("usage_period_id") for item in removed_data])
        self.assertIn(str(first_period.report_period_start), [item.get("interval_start") for item in removed_data])

        with schema_context(self.schema):
            self.assertIsNotNone(self.accessor._get_db_obj_query(report_period_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(report_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(storage_line_item_table_name).first())

    def test_purge_expired_line_item_for_provider(self):
        """Test that the provider_uuid deletes all data for the provider."""
        report_period_table_name = OCP_REPORT_TABLE_MAP["report_period"]
        report_table_name = OCP_REPORT_TABLE_MAP["report"]
        line_item_table_name = OCP_REPORT_TABLE_MAP["line_item"]
        storage_line_item_table_name = OCP_REPORT_TABLE_MAP["storage_line_item"]

        cleaner = OCPReportDBCleaner(self.schema)

        with schema_context(self.schema):
            # Verify that data is cleared for a cutoff date == billing_period_start
            first_period = (
                self.accessor._get_db_obj_query(report_period_table_name)
                .filter(provider_id=self.ocp_provider_uuid)
                .order_by("-report_period_start")
                .first()
            )
            cutoff_date = first_period.report_period_start
            self.assertIsNotNone(self.accessor._get_db_obj_query(report_period_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(report_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(storage_line_item_table_name).first())

            expected_count = (
                self.accessor._get_db_obj_query(report_period_table_name)
                .filter(provider_id=self.ocp_provider_uuid)
                .count()
            )

        removed_data = cleaner.purge_expired_line_item(cutoff_date, provider_uuid=self.ocp_provider_uuid)

        self.assertEqual(len(removed_data), expected_count)
        self.assertIn(first_period.id, [item.get("usage_period_id") for item in removed_data])
        self.assertIn(str(first_period.report_period_start), [item.get("interval_start") for item in removed_data])

    def test_purge_expired_line_items_not_datetime_obj(self):
        """Test error raised if expired_date is not datetime.datetime."""
        cleaner = OCPReportDBCleaner(self.schema)
        with self.assertRaises(OCPReportDBCleanerError):
            cleaner.purge_expired_line_item(False)
