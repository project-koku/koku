#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCIReportDBCleaner utility object."""
import datetime
import uuid

import django
import pytz
from django.db import transaction
from django_tenants.utils import schema_context

from api.provider.models import Provider
from masu.database import OCI_CUR_TABLE_MAP
from masu.database.oci_report_db_accessor import OCIReportDBAccessor
from masu.processor.oci.oci_report_db_cleaner import OCIReportDBCleaner
from masu.processor.oci.oci_report_db_cleaner import OCIReportDBCleanerError
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


class OCIReportDBCleanerTest(MasuTestCase):
    """Test Cases for the OCIReportDBCleaner object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.accessor = OCIReportDBAccessor(schema=cls.schema)
        cls.report_schema = cls.accessor.report_schema
        cls.all_tables = list(OCI_CUR_TABLE_MAP.values())
        cls.foreign_key_tables = [
            OCI_CUR_TABLE_MAP["bill"],
        ]

    def test_initializer(self):
        """Test initializer."""
        self.assertIsNotNone(self.report_schema)

    def test_purge_expired_report_data_no_args(self):
        """Test that the provider_uuid deletes all data for the provider."""
        cleaner = OCIReportDBCleaner(self.schema)
        with self.assertRaises(OCIReportDBCleanerError):
            cleaner.purge_expired_report_data()

    def test_purge_expired_report_data_both_args(self):
        """Test that the provider_uuid deletes all data for the provider."""
        now = datetime.datetime.utcnow()
        cleaner = OCIReportDBCleaner(self.schema)
        with self.assertRaises(OCIReportDBCleanerError):
            cleaner.purge_expired_report_data(expired_date=now, provider_uuid=self.oci_provider_uuid)

    def test_drop_report_partitions(self):
        """Test that cleaner drops report line item daily summary parititons"""
        provider = Provider.objects.filter(type__in=[Provider.PROVIDER_OCI, Provider.PROVIDER_OCI_LOCAL]).first()
        self.assertIsNotNone(provider)

        partitioned_table_name = OCI_CUR_TABLE_MAP["line_item_daily_summary"]
        report_period_table_name = OCI_CUR_TABLE_MAP["bill"]
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
            cluster_id = "oci-test-cluster-0001"
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
            cleaner = OCIReportDBCleaner(self.schema)
            removed_data = cleaner.purge_expired_report_data(cutoff_date, simulate=False)

            self.assertEqual(len(removed_data), 1)
            self.assertFalse(table_exists(self.schema, test_part.table_name))
