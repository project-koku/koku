#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AWSReportDBCleaner utility object."""
import datetime
import uuid

import django
import pytz
from dateutil import relativedelta
from django.db import transaction
from tenant_schemas.utils import schema_context

from api.provider.models import Provider
from masu.database import AWS_CUR_TABLE_MAP
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.processor.aws.aws_report_db_cleaner import AWSReportDBCleaner
from masu.processor.aws.aws_report_db_cleaner import AWSReportDBCleanerError
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator
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


class AWSReportDBCleanerTest(MasuTestCase):
    """Test Cases for the AWSReportDBCleaner object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.accessor = AWSReportDBAccessor(schema=cls.schema)
        cls.report_schema = cls.accessor.report_schema
        cls.creator = ReportObjectCreator(cls.schema)
        cls.all_tables = list(AWS_CUR_TABLE_MAP.values())
        cls.foreign_key_tables = [
            AWS_CUR_TABLE_MAP["bill"],
            AWS_CUR_TABLE_MAP["product"],
            AWS_CUR_TABLE_MAP["pricing"],
            AWS_CUR_TABLE_MAP["reservation"],
        ]

    def test_initializer(self):
        """Test initializer."""
        self.assertIsNotNone(self.report_schema)

    def test_purge_expired_report_data_on_date(self):
        """Test to remove report data on a provided date."""
        bill_table_name = AWS_CUR_TABLE_MAP["bill"]
        line_item_table_name = AWS_CUR_TABLE_MAP["line_item"]
        cost_entry_table_name = AWS_CUR_TABLE_MAP["cost_entry"]

        cleaner = AWSReportDBCleaner(self.schema)
        with schema_context(self.schema):
            # Verify that data is cleared for a cutoff date == billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).order_by("-billing_period_start").first()
            cutoff_date = first_bill.billing_period_start
            expected_count = (
                self.accessor._get_db_obj_query(bill_table_name).filter(billing_period_start__lte=cutoff_date).count()
            )

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(cost_entry_table_name).first())

        removed_data = cleaner.purge_expired_report_data(cutoff_date)

        self.assertEqual(len(removed_data), expected_count)
        self.assertIn(first_bill.payer_account_id, [entry.get("account_payer_id") for entry in removed_data])
        self.assertIn(
            str(first_bill.billing_period_start), [entry.get("billing_period_start") for entry in removed_data]
        )

    def test_purge_expired_report_data_before_date(self):
        """Test to remove report data before a provided date."""
        bill_table_name = AWS_CUR_TABLE_MAP["bill"]
        line_item_table_name = AWS_CUR_TABLE_MAP["line_item"]
        cost_entry_table_name = AWS_CUR_TABLE_MAP["cost_entry"]

        cleaner = AWSReportDBCleaner(self.schema)

        with schema_context(self.schema):
            # Verify that data is not cleared for a cutoff date < billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
            cutoff_date = first_bill.billing_period_start
            earlier_cutoff = cutoff_date.replace(day=15) + relativedelta.relativedelta(months=-1)

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(cost_entry_table_name).first())

        removed_data = cleaner.purge_expired_report_data(earlier_cutoff)

        self.assertEqual(len(removed_data), 0)

        with schema_context(self.schema):
            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(cost_entry_table_name).first())

    def test_purge_expired_report_data_after_date(self):
        """Test to remove report data after a provided date."""
        bill_table_name = AWS_CUR_TABLE_MAP["bill"]
        line_item_table_name = AWS_CUR_TABLE_MAP["line_item"]
        cost_entry_table_name = AWS_CUR_TABLE_MAP["cost_entry"]

        cleaner = AWSReportDBCleaner(self.schema)

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
            self.assertIsNotNone(self.accessor._get_db_obj_query(cost_entry_table_name).first())

        removed_data = cleaner.purge_expired_report_data(later_cutoff)

        self.assertEqual(len(removed_data), expected_count)
        self.assertIn(first_bill.payer_account_id, [entry.get("account_payer_id") for entry in removed_data])
        self.assertIn(
            str(first_bill.billing_period_start), [entry.get("billing_period_start") for entry in removed_data]
        )

    def test_purge_expired_report_data_on_date_simulate(self):
        """Test to simulate removing report data on a provided date."""
        bill_table_name = AWS_CUR_TABLE_MAP["bill"]
        line_item_table_name = AWS_CUR_TABLE_MAP["line_item"]
        cost_entry_table_name = AWS_CUR_TABLE_MAP["cost_entry"]

        cleaner = AWSReportDBCleaner(self.schema)

        # Verify that data is cleared for a cutoff date == billing_period_start
        with schema_context(self.schema):
            first_bill = self.accessor._get_db_obj_query(bill_table_name).first()
            cutoff_date = first_bill.billing_period_start

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(cost_entry_table_name).first())

        removed_data = cleaner.purge_expired_report_data(cutoff_date, simulate=True)

        self.assertEqual(len(removed_data), 1)
        self.assertEqual(removed_data[0].get("account_payer_id"), first_bill.payer_account_id)
        self.assertEqual(removed_data[0].get("billing_period_start"), str(first_bill.billing_period_start))

        with schema_context(self.schema):
            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(cost_entry_table_name).first())

    def test_purge_expired_report_data_for_provider(self):
        """Test that the provider_uuid deletes all data for the provider."""
        bill_table_name = AWS_CUR_TABLE_MAP["bill"]
        line_item_table_name = AWS_CUR_TABLE_MAP["line_item"]
        cost_entry_table_name = AWS_CUR_TABLE_MAP["cost_entry"]

        cleaner = AWSReportDBCleaner(self.schema)

        with schema_context(self.schema):
            # Verify that data is cleared for a cutoff date == billing_period_start
            first_bill = self.accessor._get_db_obj_query(bill_table_name).order_by("-billing_period_start").first()

            self.assertIsNotNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(cost_entry_table_name).first())

            expected_count = (
                self.accessor._get_db_obj_query(bill_table_name).filter(provider_id=self.aws_provider_uuid).count()
            )

        removed_data = cleaner.purge_expired_report_data(provider_uuid=self.aws_provider_uuid)

        self.assertEqual(len(removed_data), expected_count)
        self.assertIn(first_bill.payer_account_id, [entry.get("account_payer_id") for entry in removed_data])
        self.assertIn(
            str(first_bill.billing_period_start), [entry.get("billing_period_start") for entry in removed_data]
        )

        with schema_context(self.schema):
            self.assertIsNone(self.accessor._get_db_obj_query(bill_table_name).first())
            self.assertIsNone(self.accessor._get_db_obj_query(cost_entry_table_name).first())
            self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

    def test_purge_expired_report_data_no_args(self):
        """Test that the provider_uuid deletes all data for the provider."""
        cleaner = AWSReportDBCleaner(self.schema)
        with self.assertRaises(AWSReportDBCleanerError):
            cleaner.purge_expired_report_data()

    def test_purge_expired_report_data_both_args(self):
        """Test that the provider_uuid deletes all data for the provider."""
        now = datetime.datetime.utcnow()
        cleaner = AWSReportDBCleaner(self.schema)
        with self.assertRaises(AWSReportDBCleanerError):
            cleaner.purge_expired_report_data(expired_date=now, provider_uuid=self.aws_provider_uuid)

    def test_drop_report_partitions(self):
        """Test that cleaner drops report line item daily summary parititons"""
        provider = Provider.objects.filter(type__in=[Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL]).first()
        self.assertIsNotNone(provider)

        partitioned_table_name = AWS_CUR_TABLE_MAP["line_item_daily_summary"]
        report_period_table_name = AWS_CUR_TABLE_MAP["bill"]
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

        with schema_context(self.schema):
            test_part = PartitionedTable(
                schema_name=self.schema,
                table_name=f"{partitioned_table_name}_2017_01",
                partition_of_table_name=partitioned_table_name,
                partition_type=PartitionedTable.RANGE,
                partition_col="usage_start",
                partition_parameters={"default": False, "from": "2017-01-01", "to": "2017-02-01"},
                active=True,
            )
            test_part.save()

            self.assertTrue(table_exists(self.schema, test_part.table_name))

            report_period_start = datetime.datetime(2017, 1, 1, tzinfo=pytz.UTC)
            report_period_end = datetime.datetime(2017, 1, 31, tzinfo=pytz.UTC)
            cluster_id = "aws-test-cluster-0001"
            report_period = report_period_model(
                billing_resource=cluster_id,
                billing_period_start=report_period_start,
                billing_period_end=report_period_end,
                provider_id=provider.uuid,
            )
            report_period.save()

            usage_date = datetime.date(2017, 1, 12)
            lids_rec = partitioned_table_model(
                usage_start=usage_date, usage_end=usage_date, cost_entry_bill_id=report_period.id, uuid=uuid.uuid4()
            )
            lids_rec.save()

            cutoff_date = datetime.datetime(2017, 12, 31, tzinfo=pytz.UTC)
            cleaner = AWSReportDBCleaner(self.schema)
            removed_data = cleaner.purge_expired_report_data(cutoff_date, simulate=False)

            self.assertEqual(len(removed_data), 1)
            self.assertFalse(table_exists(self.schema, test_part.table_name))
