#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AzureReportDBCleaner object."""
import datetime
from unittest.mock import patch

from dateutil import relativedelta
from tenant_schemas.utils import schema_context

from api.provider.models import Provider
from api.provider.models import ProviderAuthentication
from api.provider.models import ProviderBillingSource
from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.processor.azure.azure_report_db_cleaner import AzureReportDBCleaner
from masu.processor.azure.azure_report_db_cleaner import AzureReportDBCleanerError
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator


class AzureReportDBCleanerTest(MasuTestCase):
    """Test Cases for the AzureCostModelCostUpdater object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.accessor = AzureReportDBAccessor(schema=cls.schema)
        cls.report_schema = cls.accessor.report_schema
        cls.creator = ReportObjectCreator(cls.schema)
        cls.all_tables = list(AZURE_REPORT_TABLE_MAP.values())
        cls.foreign_key_tables = [
            AZURE_REPORT_TABLE_MAP["bill"],
            AZURE_REPORT_TABLE_MAP["product"],
            AZURE_REPORT_TABLE_MAP["meter"],
        ]

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()
        bill_id = self.creator.create_azure_cost_entry_bill(provider_uuid=self.azure_provider_uuid)
        product_id = self.creator.create_azure_cost_entry_product(provider_uuid=self.azure_provider_uuid)
        meter_id = self.creator.create_azure_meter(provider_uuid=self.azure_provider_uuid)
        self.creator.create_azure_cost_entry_line_item(bill_id, product_id, meter_id)

    def test_initializer(self):
        """Test initializer."""
        self.assertIsNotNone(self.report_schema)

    def test_purge_expired_report_data_no_args(self):
        """Test that the provider_uuid deletes all data for the provider."""
        cleaner = AzureReportDBCleaner(self.schema)
        with self.assertRaises(AzureReportDBCleanerError):
            cleaner.purge_expired_report_data()

    def test_purge_expired_report_data_both_args(self):
        """Test that the provider_uuid deletes all data for the provider."""
        now = datetime.datetime.utcnow()
        cleaner = AzureReportDBCleaner(self.schema)
        with self.assertRaises(AzureReportDBCleanerError):
            cleaner.purge_expired_report_data(expired_date=now, provider_uuid=self.azure_provider_uuid)

    def test_purge_expired_report_data_on_date(self):
        """Test to remove report data on a provided date."""
        bill_table_name = AZURE_REPORT_TABLE_MAP["bill"]
        line_item_table_name = AZURE_REPORT_TABLE_MAP["line_item"]

        cleaner = AzureReportDBCleaner(self.schema)
        with schema_context(self.schema):
            # Verify that data is cleared for a cutoff date == billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
            cutoff_date = first_bill.billing_period_start

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

        removed_data = cleaner.purge_expired_report_data(cutoff_date)

        self.assertEqual(len(removed_data), 1)
        self.assertEqual(removed_data[0].get("provider_uuid"), first_bill.provider_id)
        self.assertEqual(removed_data[0].get("billing_period_start"), str(first_bill.billing_period_start))

    def test_purge_expired_report_data_before_date(self):
        """Test to remove report data before a provided date."""
        bill_table_name = AZURE_REPORT_TABLE_MAP["bill"]
        line_item_table_name = AZURE_REPORT_TABLE_MAP["line_item"]

        cleaner = AzureReportDBCleaner(self.schema)

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
        bill_table_name = AZURE_REPORT_TABLE_MAP["bill"]
        line_item_table_name = AZURE_REPORT_TABLE_MAP["line_item"]

        cleaner = AzureReportDBCleaner(self.schema)

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
        self.assertEqual(removed_data[0].get("provider_uuid"), first_bill.provider_id)
        self.assertIn(
            str(first_bill.billing_period_start), [entry.get("billing_period_start") for entry in removed_data]
        )
        with schema_context(self.schema):
            self.assertIsNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNone(self.accessor._get_db_obj_query(line_item_table_name).first())

    def test_purge_expired_report_data_on_date_simulate(self):
        """Test to simulate removing report data on a provided date."""
        bill_table_name = AZURE_REPORT_TABLE_MAP["bill"]
        line_item_table_name = AZURE_REPORT_TABLE_MAP["line_item"]

        cleaner = AzureReportDBCleaner(self.schema)

        # Verify that data is cleared for a cutoff date == billing_period_start
        with schema_context(self.schema):
            first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
            cutoff_date = first_bill.billing_period_start

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

        removed_data = cleaner.purge_expired_report_data(cutoff_date, simulate=True)

        self.assertEqual(len(removed_data), 1)
        self.assertEqual(removed_data[0].get("provider_uuid"), first_bill.provider_id)
        self.assertEqual(removed_data[0].get("billing_period_start"), str(first_bill.billing_period_start))

        with schema_context(self.schema):
            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

    def test_purge_expired_report_data_for_provider(self):
        """Test that the provider_uuid deletes all data for the provider."""
        bill_table_name = AZURE_REPORT_TABLE_MAP["bill"]
        line_item_table_name = AZURE_REPORT_TABLE_MAP["line_item"]

        cleaner = AzureReportDBCleaner(self.schema)

        with schema_context(self.schema):
            first_bill = (
                self.accessor._get_db_obj_query(bill_table_name)
                .filter(provider_id=self.azure_provider_uuid)
                .order_by("-billing_period_start")
                .first()
            )
            expected_count = (
                self.accessor._get_db_obj_query(bill_table_name).filter(provider_id=self.azure_provider_uuid).count()
            )

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

        removed_data = cleaner.purge_expired_report_data(provider_uuid=self.azure_provider_uuid)

        self.assertEqual(len(removed_data), expected_count)
        self.assertEqual(removed_data[0].get("provider_uuid"), first_bill.provider_id)
        self.assertIn(
            str(first_bill.billing_period_start), [entry.get("billing_period_start") for entry in removed_data]
        )

        with schema_context(self.schema):
            self.assertIsNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNone(self.accessor._get_db_obj_query(line_item_table_name).first())

    def test_purge_correct_expired_report_data_for_provider(self):
        """Test that the provider_uuid deletes all data for the provider when another provider exists."""
        # add another line item with different provider_uuid
        azure_credentials = {
            "subscription_id": "11111111-f248-4ad7-bfb1-9a4cff600e1d",
            "tenant_id": "11111111-228a-4aee-a215-3a768cdd0105",
            "client_id": "11111111-0f78-42bb-b8e5-90144a025191",
            "client_secret": "notsosecretcode",
        }
        azure_data_source = {"resource_group": "resourcegroup2", "storage_account": "storageaccount2"}
        test_provider_uuid = "11111111-d05f-488c-a6d9-c2a6f3ee02bb"
        azure_auth = ProviderAuthentication.objects.create(credentials=azure_credentials)
        azure_auth.save()
        azure_billing_source = ProviderBillingSource.objects.create(data_source=azure_data_source)
        azure_billing_source.save()
        with patch("masu.celery.tasks.check_report_updates"):
            azure_provider = Provider.objects.create(
                uuid=test_provider_uuid,
                name="Test Provider",
                type=Provider.PROVIDER_AZURE_LOCAL,
                authentication=azure_auth,
                billing_source=azure_billing_source,
                customer=self.customer,
                setup_complete=False,
            )
        azure_provider.save()
        bill_id = self.creator.create_azure_cost_entry_bill(provider_uuid=azure_provider.uuid)
        product_id = self.creator.create_azure_cost_entry_product(provider_uuid=azure_provider.uuid)
        meter_id = self.creator.create_azure_meter(provider_uuid=azure_provider.uuid)
        self.creator.create_azure_cost_entry_line_item(bill_id, product_id, meter_id)

        bill_table_name = AZURE_REPORT_TABLE_MAP["bill"]
        line_item_table_name = AZURE_REPORT_TABLE_MAP["line_item"]

        cleaner = AzureReportDBCleaner(self.schema)

        with schema_context(self.schema):
            # Verify that data is cleared for a cutoff date == billing_period_start
            first_bill = (
                self.accessor._get_db_obj_query(bill_table_name)
                .filter(provider_id=self.azure_provider_uuid)
                .order_by("-billing_period_start")
                .first()
            )
            expected_count = (
                self.accessor._get_db_obj_query(bill_table_name).filter(provider_id=self.azure_provider_uuid).count()
            )
            expected_line_item_count = (
                self.accessor._get_db_obj_query(line_item_table_name)
                .filter(cost_entry_bill__provider_id=self.azure_provider_uuid)
                .count()
            )

            self.assertEqual(self.accessor._get_db_obj_query(bill_table_name).count(), expected_count + 1)
            self.assertEqual(
                self.accessor._get_db_obj_query(line_item_table_name).count(), expected_line_item_count + 1
            )

        removed_data = cleaner.purge_expired_report_data(provider_uuid=self.azure_provider_uuid)

        self.assertEqual(len(removed_data), expected_count)
        self.assertEqual(removed_data[0].get("provider_uuid"), first_bill.provider_id)
        self.assertIn(
            str(first_bill.billing_period_start), [entry.get("billing_period_start") for entry in removed_data]
        )

        with schema_context(self.schema):
            self.assertEqual(self.accessor._get_db_obj_query(bill_table_name).all().count(), 1)
            self.assertEqual(self.accessor._get_db_obj_query(line_item_table_name).count(), 1)
