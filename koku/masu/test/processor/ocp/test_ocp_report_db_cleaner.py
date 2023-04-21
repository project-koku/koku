#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCPReportDBCleaner utility object."""
import datetime
import uuid

import django
import pytz
from dateutil import relativedelta
from django.db import transaction
from django_tenants.utils import schema_context

from api.provider.models import Provider
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.processor.ocp.ocp_report_db_cleaner import OCPReportDBCleaner
from masu.processor.ocp.ocp_report_db_cleaner import OCPReportDBCleanerError
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

    def setUp(self):
        """Set up shared variables."""
        super().setUp()
        self.provider_uuid = self.ocp_provider_uuid
        reporting_period = self.creator.create_ocp_report_period(provider_uuid=self.provider_uuid)
        report = self.creator.create_ocp_report(reporting_period, reporting_period.report_period_start)
        self.creator.create_ocp_usage_line_item(reporting_period, report)
        self.creator.create_ocp_storage_line_item(reporting_period, report)

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

        # with schema_context(self.schema):
        #     self.assertIsNone(self.accessor._get_db_obj_query(report_period_table_name).first())
        #     self.assertIsNone(self.accessor._get_db_obj_query(report_table_name).first())
        #     self.assertIsNotNone(self.accessor._get_db_obj_query(storage_line_item_table_name).first())
        #     self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

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

        # with schema_context(self.schema):
        #     self.assertIsNone(self.accessor._get_db_obj_query(report_period_table_name).first())
        #     self.assertIsNone(self.accessor._get_db_obj_query(report_table_name).first())
        #     self.assertIsNotNone(self.accessor._get_db_obj_query(storage_line_item_table_name).first())
        #     self.assertIsNotNone(self.accessor._get_db_obj_query(line_item_table_name).first())

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

    def test_drop_report_partitions(self):
        """Test that cleaner drops report line item daily summary parititons"""
        provider = Provider.objects.filter(type=Provider.PROVIDER_OCP).first()
        self.assertIsNotNone(provider)

        partitioned_table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]
        report_period_table_name = OCP_REPORT_TABLE_MAP["report_period"]
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
                table_name=f"{partitioned_table_name}_2018_01",
                partition_of_table_name=partitioned_table_name,
                partition_type=PartitionedTable.RANGE,
                partition_col="usage_start",
                partition_parameters={"default": False, "from": "2018-01-01", "to": "2018-02-01"},
                active=True,
            )
            test_part.save()

            self.assertTrue(table_exists(self.schema, test_part.table_name))

            report_period_start = datetime.datetime(2018, 1, 1, tzinfo=pytz.UTC)
            report_period_end = datetime.datetime(2018, 1, 31, tzinfo=pytz.UTC)
            cluster_id = "ocp-test-cluster-0001"
            report_period = report_period_model(
                cluster_id=cluster_id,
                report_period_start=report_period_start,
                report_period_end=report_period_end,
                provider_id=provider.uuid,
            )
            report_period.save()

            usage_date = datetime.date(2018, 1, 12)
            lids_rec = partitioned_table_model(
                usage_start=usage_date, usage_end=usage_date, report_period_id=report_period.id, uuid=uuid.uuid4()
            )
            lids_rec.save()

        cutoff_date = datetime.datetime(2018, 12, 31, tzinfo=pytz.UTC)
        cleaner = OCPReportDBCleaner(self.schema)
        removed_data = cleaner.purge_expired_report_data(cutoff_date, simulate=False)

        self.assertEqual(len(removed_data), 1)
        with schema_context(self.schema):
            self.assertFalse(table_exists(self.schema, test_part.table_name))
