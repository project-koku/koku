#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the GCPReportDBCleaner utility object."""
import datetime

from dateutil import relativedelta
from tenant_schemas.utils import schema_context

from masu.database import GCP_REPORT_TABLE_MAP
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.processor.gcp.gcp_report_db_cleaner import GCPReportDBCleaner
from masu.processor.gcp.gcp_report_db_cleaner import GCPReportDBCleanerError
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator


class GCPReportDBCleanerTest(MasuTestCase):
    """Test Cases for the GCPReportDBCleaner object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.accessor = GCPReportDBAccessor(schema=cls.schema)
        cls.report_schema = cls.accessor.report_schema
        cls.creator = ReportObjectCreator(cls.schema)
        cls.all_tables = list(GCP_REPORT_TABLE_MAP.values())
        cls.foreign_key_tables = [GCP_REPORT_TABLE_MAP["bill"], GCP_REPORT_TABLE_MAP["product"]]

    def test_initializer(self):
        """Test initializer."""
        self.assertIsNotNone(self.report_schema)

    def test_purge_expired_report_data_on_date(self):
        """Test to remove report data on a provided date."""
        bill_table_name = GCP_REPORT_TABLE_MAP["bill"]
        line_item_table_name = GCP_REPORT_TABLE_MAP["line_item"]

        cleaner = GCPReportDBCleaner(self.schema)
        with schema_context(self.schema):
            # Verify that data is cleared for a cutoff date == billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).order_by("-billing_period_start").first()
            cutoff_date = first_bill.billing_period_start
            expected_count = (
                self.accessor._get_db_obj_query(bill_table_name).filter(billing_period_start__lte=cutoff_date).count()
            )

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

        removed_data = cleaner.purge_expired_report_data(cutoff_date)

        self.assertEqual(len(removed_data), expected_count)
        self.assertIn(first_bill.provider_id, [entry.get("removed_provider_uuid") for entry in removed_data])
        self.assertIn(
            str(first_bill.billing_period_start), [entry.get("billing_period_start") for entry in removed_data]
        )

    def test_purge_expired_report_data_before_date(self):
        """Test to remove report data before a provided date."""
        bill_table_name = GCP_REPORT_TABLE_MAP["bill"]
        line_item_table_name = GCP_REPORT_TABLE_MAP["line_item"]

        cleaner = GCPReportDBCleaner(self.schema)

        with schema_context(self.schema):
            # Verify that data is not cleared for a cutoff date < billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
            cutoff_date = first_bill.billing_period_start
            earlier_cutoff = cutoff_date.replace(day=15) + relativedelta.relativedelta(months=-1)

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

        removed_data = cleaner.purge_expired_report_data(earlier_cutoff)

        self.assertEqual(len(removed_data), 0)

        with schema_context(self.schema):
            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

    def test_purge_expired_report_data_after_date(self):
        """Test to remove report data after a provided date."""
        bill_table_name = GCP_REPORT_TABLE_MAP["bill"]
        line_item_table_name = GCP_REPORT_TABLE_MAP["line_item"]

        cleaner = GCPReportDBCleaner(self.schema)

        with schema_context(self.schema):
            # Verify that data is cleared for a cutoff date > billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).order_by("-billing_period_start").first()
            cutoff_date = first_bill.billing_period_start
            later_date = cutoff_date + relativedelta.relativedelta(months=+1)
            later_cutoff = later_date.replace(month=later_date.month, day=15)
            expected_count = (
                self.accessor._get_db_obj_query(bill_table_name).filter(billing_period_start__lte=later_cutoff).count()
            )

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

        removed_data = cleaner.purge_expired_report_data(later_cutoff)

        self.assertEqual(len(removed_data), expected_count)
        self.assertIn(first_bill.provider_id, [entry.get("removed_provider_uuid") for entry in removed_data])
        self.assertIn(
            str(first_bill.billing_period_start), [entry.get("billing_period_start") for entry in removed_data]
        )

    def test_purge_expired_report_data_on_date_simulate(self):
        """Test to simulate removing report data on a provided date."""
        bill_table_name = GCP_REPORT_TABLE_MAP["bill"]
        line_item_table_name = GCP_REPORT_TABLE_MAP["line_item"]

        cleaner = GCPReportDBCleaner(self.schema)

        # Verify that data is cleared for a cutoff date == billing_period_start
        with schema_context(self.schema):
            first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
            cutoff_date = first_bill.billing_period_start

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

        removed_data = cleaner.purge_expired_report_data(cutoff_date, simulate=True)

        self.assertEqual(len(removed_data), 1)
        self.assertEqual(removed_data[0].get("removed_provider_uuid"), first_bill.provider_id)
        self.assertEqual(removed_data[0].get("billing_period_start"), str(first_bill.billing_period_start))

        with schema_context(self.schema):
            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

    def test_purge_expired_report_data_for_provider(self):
        """Test that the provider_uuid deletes all data for the provider."""
        bill_table_name = GCP_REPORT_TABLE_MAP["bill"]
        line_item_table_name = GCP_REPORT_TABLE_MAP["line_item"]

        cleaner = GCPReportDBCleaner(self.schema)

        with schema_context(self.schema):
            # Verify that data is cleared for a cutoff date == billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).order_by("-billing_period_start").first()

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

            expected_count = (
                self.accessor._get_db_obj_query(bill_table_name).filter(provider_id=self.gcp_provider_uuid).count()
            )

        removed_data = cleaner.purge_expired_report_data(provider_uuid=self.gcp_provider_uuid)

        self.assertEqual(len(removed_data), expected_count)
        self.assertIn(first_bill.provider_id, [entry.get("removed_provider_uuid") for entry in removed_data])
        self.assertIn(
            str(first_bill.billing_period_start), [entry.get("billing_period_start") for entry in removed_data]
        )

        with schema_context(self.schema):
            self.assertIsNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNone(self.accessor._get_db_obj_query(line_item_table_name).first())

    def test_purge_expired_report_data_no_args(self):
        """Test that the provider_uuid deletes all data for the provider."""
        cleaner = GCPReportDBCleaner(self.schema)
        with self.assertRaises(GCPReportDBCleanerError):
            cleaner.purge_expired_report_data()

    def test_purge_expired_report_data_both_args(self):
        """Test that the provider_uuid deletes all data for the provider."""
        now = datetime.datetime.utcnow()
        cleaner = GCPReportDBCleaner(self.schema)
        with self.assertRaises(GCPReportDBCleanerError):
            cleaner.purge_expired_report_data(expired_date=now, provider_uuid=self.gcp_provider_uuid)

    def test_purge_expired_line_items_on_date(self):
        """Test to remove line items on a provided date."""
        bill_table_name = GCP_REPORT_TABLE_MAP["bill"]
        line_item_table_name = GCP_REPORT_TABLE_MAP["line_item"]

        cleaner = GCPReportDBCleaner(self.schema)
        with schema_context(self.schema):
            # Verify that data is cleared for a cutoff date == billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).order_by("-billing_period_start").first()
            cutoff_date = first_bill.billing_period_start
            expected_count = (
                self.accessor._get_db_obj_query(bill_table_name).filter(billing_period_start__lte=cutoff_date).count()
            )

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

        removed_data = cleaner.purge_expired_line_item(cutoff_date)

        self.assertEqual(len(removed_data), expected_count)
        self.assertIn(first_bill.provider_id, [entry.get("removed_provider_uuid") for entry in removed_data])
        self.assertIn(
            str(first_bill.billing_period_start), [entry.get("billing_period_start") for entry in removed_data]
        )

    def test_purge_expired_line_items_before_date(self):
        """Test to remove line items before a provided date."""
        bill_table_name = GCP_REPORT_TABLE_MAP["bill"]
        line_item_table_name = GCP_REPORT_TABLE_MAP["line_item"]

        cleaner = GCPReportDBCleaner(self.schema)

        with schema_context(self.schema):
            # Verify that data is not cleared for a cutoff date < billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
            cutoff_date = first_bill.billing_period_start
            earlier_cutoff = cutoff_date.replace(day=15) + relativedelta.relativedelta(months=-1)

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

        removed_data = cleaner.purge_expired_line_item(earlier_cutoff)

        self.assertEqual(len(removed_data), 0)

        with schema_context(self.schema):
            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

    def test_purge_expired_line_items_after_date(self):
        """Test to remove report data after a provided date."""
        bill_table_name = GCP_REPORT_TABLE_MAP["bill"]
        line_item_table_name = GCP_REPORT_TABLE_MAP["line_item"]

        cleaner = GCPReportDBCleaner(self.schema)

        with schema_context(self.schema):
            # Verify that data is cleared for a cutoff date > billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).order_by("-billing_period_start").first()
            cutoff_date = first_bill.billing_period_start
            later_date = cutoff_date + relativedelta.relativedelta(months=+1)
            later_cutoff = later_date.replace(month=later_date.month, day=15)
            expected_count = (
                self.accessor._get_db_obj_query(bill_table_name).filter(billing_period_start__lte=later_cutoff).count()
            )

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

        removed_data = cleaner.purge_expired_line_item(later_cutoff)

        self.assertEqual(len(removed_data), expected_count)
        self.assertIn(first_bill.provider_id, [entry.get("removed_provider_uuid") for entry in removed_data])
        self.assertIn(
            str(first_bill.billing_period_start), [entry.get("billing_period_start") for entry in removed_data]
        )
        with schema_context(self.schema):
            self.assertIsNone(
                self.accessor._get_db_obj_query(line_item_table_name).filter(cost_entry_bill=first_bill).first()
            )
            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())

    def test_purge_expired_line_items_on_date_simulate(self):
        """Test to simulate removing report data on a provided date."""
        bill_table_name = GCP_REPORT_TABLE_MAP["bill"]
        line_item_table_name = GCP_REPORT_TABLE_MAP["line_item"]

        cleaner = GCPReportDBCleaner(self.schema)

        # Verify that data is cleared for a cutoff date == billing_period_start
        with schema_context(self.schema):
            first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
            cutoff_date = first_bill.billing_period_start

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

        removed_data = cleaner.purge_expired_line_item(cutoff_date, simulate=True)

        self.assertEqual(len(removed_data), 1)
        self.assertEqual(removed_data[0].get("removed_provider_uuid"), first_bill.provider_id)
        self.assertEqual(removed_data[0].get("billing_period_start"), str(first_bill.billing_period_start))

        with schema_context(self.schema):
            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

    def test_purge_expired_line_items_for_provider(self):
        """Test that the provider_uuid deletes all data for the provider."""
        bill_table_name = GCP_REPORT_TABLE_MAP["bill"]
        line_item_table_name = GCP_REPORT_TABLE_MAP["line_item"]

        cleaner = GCPReportDBCleaner(self.schema)

        with schema_context(self.schema):
            # Verify that data is cleared for a cutoff date == billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).order_by("-billing_period_start").first()
            cutoff_date = first_bill.billing_period_start
            expected_count = (
                self.accessor._get_db_obj_query(bill_table_name)
                .filter(provider_id=self.gcp_provider_uuid, billing_period_start__lte=cutoff_date)
                .count()
            )
            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

        removed_data = cleaner.purge_expired_line_item(cutoff_date, provider_uuid=self.gcp_provider_uuid)

        self.assertEqual(len(removed_data), expected_count)
        self.assertIn(first_bill.provider_id, [entry.get("removed_provider_uuid") for entry in removed_data])
        self.assertIn(
            str(first_bill.billing_period_start), [entry.get("billing_period_start") for entry in removed_data]
        )

        with schema_context(self.schema):
            self.assertIsNone(
                self.accessor._get_db_obj_query(line_item_table_name).filter(cost_entry_bill=first_bill).first()
            )
            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())

    def test_purge_expired_line_items_not_datetime_obj(self):
        """Test error raised if expired_date is not datetime.datetime."""
        cleaner = GCPReportDBCleaner(self.schema)
        with self.assertRaises(GCPReportDBCleanerError):
            cleaner.purge_expired_line_item(False)
