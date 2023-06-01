#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AzureReportDBCleaner object."""
import datetime
import uuid
from unittest.mock import patch

import django
from dateutil import relativedelta
from django.conf import settings
from django.db import transaction
from django_tenants.utils import schema_context

from api.provider.models import Provider
from api.provider.models import ProviderAuthentication
from api.provider.models import ProviderBillingSource
from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.processor.azure.azure_report_db_cleaner import AzureReportDBCleaner
from masu.processor.azure.azure_report_db_cleaner import AzureReportDBCleanerError
from masu.test import MasuTestCase
from reporting.models import PartitionedTable


def table_exists(schema_name, table_name):
    sql = """
select oid
  from pg_class
 where relnamespace = %s::regnamespace
   and relname = %s ;
"""
    conn = transaction.get_connection()
    res = None
    with conn.cursor() as cur:
        cur.execute(sql, (schema_name, table_name))
        res = cur.fetchone()

    return True if res and res[0] else False


class AzureReportDBCleanerTest(MasuTestCase):
    """Test Cases for the AzureCostModelCostUpdater object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.accessor = AzureReportDBAccessor(schema_name=cls.schema_name)
        cls.report_schema = cls.accessor.report_schema
        cls.all_tables = list(AZURE_REPORT_TABLE_MAP.values())
        cls.foreign_key_tables = [
            AZURE_REPORT_TABLE_MAP["bill"],
        ]

    def test_initializer(self):
        """Test initializer."""
        self.assertIsNotNone(self.report_schema)

    def test_purge_expired_report_data_no_args(self):
        """Test that the provider_uuid deletes all data for the provider."""
        cleaner = AzureReportDBCleaner(self.schema_name)
        with self.assertRaises(AzureReportDBCleanerError):
            cleaner.purge_expired_report_data()

    def test_purge_expired_report_data_both_args(self):
        """Test that the provider_uuid deletes all data for the provider."""
        now = datetime.datetime.utcnow()
        cleaner = AzureReportDBCleaner(self.schema_name)
        with self.assertRaises(AzureReportDBCleanerError):
            cleaner.purge_expired_report_data(expired_date=now, provider_uuid=self.azure_provider_uuid)

    def test_purge_expired_report_data_on_date(self):
        """Test to remove report data on a provided date."""
        bill_table_name = AZURE_REPORT_TABLE_MAP["bill"]

        cleaner = AzureReportDBCleaner(self.schema_name)
        with schema_context(self.schema_name):
            # Verify that data is cleared for a cutoff date == billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
            cutoff_date = first_bill.billing_period_start

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())

        removed_data = cleaner.purge_expired_report_data(cutoff_date)

        self.assertEqual(len(removed_data), 1)
        self.assertEqual(removed_data[0].get("provider_uuid"), first_bill.provider_id)
        self.assertEqual(removed_data[0].get("billing_period_start"), str(first_bill.billing_period_start))

    def test_purge_expired_report_data_before_date(self):
        """Test to remove report data before a provided date."""
        bill_table_name = AZURE_REPORT_TABLE_MAP["bill"]

        cleaner = AzureReportDBCleaner(self.schema_name)

        with schema_context(self.schema_name):
            # Verify that data is not cleared for a cutoff date < billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
            cutoff_date = first_bill.billing_period_start
            earlier_cutoff = cutoff_date.replace(day=15) + relativedelta.relativedelta(months=-1)

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())

        removed_data = cleaner.purge_expired_report_data(earlier_cutoff)

        self.assertEqual(len(removed_data), 0)

        with schema_context(self.schema_name):
            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())

    def test_purge_expired_report_data_after_date(self):
        """Test to remove report data after a provided date."""
        bill_table_name = AZURE_REPORT_TABLE_MAP["bill"]

        with schema_context(self.schema_name):
            # Verify that data is cleared for a cutoff date > billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).order_by("-billing_period_start").first()
            cutoff_date = first_bill.billing_period_start
            later_date = cutoff_date + relativedelta.relativedelta(months=+1)
            later_cutoff = later_date.replace(month=later_date.month, day=15)

            self.assertNotEqual(
                self.accessor._get_db_obj_query(bill_table_name)
                .filter(billing_period_start__lte=later_cutoff)
                .count(),
                0,
            )
            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())

    def test_purge_expired_report_data_on_date_simulate(self):
        """Test to simulate removing report data on a provided date."""
        bill_table_name = AZURE_REPORT_TABLE_MAP["bill"]

        cleaner = AzureReportDBCleaner(self.schema_name)

        # Verify that data is cleared for a cutoff date == billing_period_start
        with schema_context(self.schema_name):
            first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
            cutoff_date = first_bill.billing_period_start

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())

        removed_data = cleaner.purge_expired_report_data(cutoff_date, simulate=True)

        self.assertEqual(len(removed_data), 1)
        self.assertEqual(removed_data[0].get("provider_uuid"), first_bill.provider_id)
        self.assertEqual(removed_data[0].get("billing_period_start"), str(first_bill.billing_period_start))

        with schema_context(self.schema_name):
            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())

    def test_purge_expired_report_data_for_provider(self):
        """Test that the provider_uuid deletes all data for the provider."""
        bill_table_name = AZURE_REPORT_TABLE_MAP["bill"]

        cleaner = AzureReportDBCleaner(self.schema_name)

        with schema_context(self.schema_name):
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

        removed_data = cleaner.purge_expired_report_data(provider_uuid=self.azure_provider_uuid)

        self.assertEqual(len(removed_data), expected_count)
        self.assertEqual(removed_data[0].get("provider_uuid"), first_bill.provider_id)
        self.assertIn(
            str(first_bill.billing_period_start), [entry.get("billing_period_start") for entry in removed_data]
        )

        with schema_context(self.schema_name):
            self.assertIsNone(self.accessor._get_db_obj_query(bill_table_name).first())

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

        bill_table_name = AZURE_REPORT_TABLE_MAP["bill"]

        cleaner = AzureReportDBCleaner(self.schema_name)

        with schema_context(self.schema_name):
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

            self.assertEqual(self.accessor._get_db_obj_query(bill_table_name).count(), expected_count)

        removed_data = cleaner.purge_expired_report_data(provider_uuid=self.azure_provider_uuid)

        self.assertEqual(len(removed_data), expected_count)
        self.assertEqual(removed_data[0].get("provider_uuid"), first_bill.provider_id)
        self.assertIn(
            str(first_bill.billing_period_start), [entry.get("billing_period_start") for entry in removed_data]
        )

        with schema_context(self.schema_name):
            self.assertEqual(self.accessor._get_db_obj_query(bill_table_name).all().count(), 0)

    def test_drop_report_partitions(self):
        """Test that cleaner drops report line item daily summary parititons"""
        provider = Provider.objects.filter(type__in=[Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL]).first()
        self.assertIsNotNone(provider)

        partitioned_table_name = AZURE_REPORT_TABLE_MAP["line_item_daily_summary"]
        report_period_table_name = AZURE_REPORT_TABLE_MAP["bill"]
        partitioned_table_model = None
        report_period_model = None
        for model in django.apps.apps.get_models():
            if model._meta.db_table == partitioned_table_name:
                partitioned_table_model = model
            elif model._meta.db_table == report_period_table_name:
                report_period_model = model
            if partitioned_table_model and report_period_model:
                break

        self.assertIsNotNone(partitioned_table_model)
        self.assertIsNotNone(report_period_model)

        with schema_context(self.schema_name):
            test_part = PartitionedTable(
                schema_name=self.schema_name,
                table_name=f"{partitioned_table_name}_2016_01",
                partition_of_table_name=partitioned_table_name,
                partition_type=PartitionedTable.RANGE,
                partition_col="usage_start",
                partition_parameters={"default": False, "from": "2016-01-01", "to": "2016-02-01"},
                active=True,
            )
            test_part.save()

            self.assertTrue(table_exists(self.schema_name, test_part.table_name))

            report_period_start = datetime.datetime(2016, 1, 1, tzinfo=settings.UTC)
            report_period_end = datetime.datetime(2016, 1, 31, tzinfo=settings.UTC)
            report_period = report_period_model(
                billing_period_start=report_period_start,
                billing_period_end=report_period_end,
                provider_id=provider.uuid,
            )
            report_period.save()

            usage_date = datetime.date(2016, 1, 12)
            lids_rec = partitioned_table_model(
                usage_start=usage_date, usage_end=usage_date, cost_entry_bill_id=report_period.id, uuid=uuid.uuid4()
            )
            lids_rec.save()

            cutoff_date = datetime.datetime(2016, 12, 31, tzinfo=settings.UTC)
            cleaner = AzureReportDBCleaner(self.schema_name)
            removed_data = cleaner.purge_expired_report_data(cutoff_date, simulate=False)

            self.assertEqual(len(removed_data), 1)
            self.assertFalse(table_exists(self.schema_name, test_part.table_name))
