#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the GCPReportDBCleaner utility object."""
import datetime
import uuid

import django
import pytz
from django.db import transaction
from tenant_schemas.utils import schema_context

from api.provider.models import Provider
from masu.database import GCP_REPORT_TABLE_MAP
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.processor.gcp.gcp_report_db_cleaner import GCPReportDBCleaner
from masu.processor.gcp.gcp_report_db_cleaner import GCPReportDBCleanerError
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
    return bool(res and res[0])


class GCPReportDBCleanerTest(MasuTestCase):
    """Test Cases for the GCPReportDBCleaner object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.accessor = GCPReportDBAccessor(schema=cls.schema)
        cls.report_schema = cls.accessor.report_schema
        cls.all_tables = list(GCP_REPORT_TABLE_MAP.values())
        cls.foreign_key_tables = [GCP_REPORT_TABLE_MAP["bill"]]

    def test_initializer(self):
        """Test initializer."""
        self.assertIsNotNone(self.report_schema)

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

    def test_drop_report_partitions(self):
        """Test that cleaner drops report line item daily summary parititons"""
        provider = Provider.objects.filter(type__in=[Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL]).first()
        self.assertIsNotNone(provider)

        partitioned_table_name = GCP_REPORT_TABLE_MAP["line_item_daily_summary"]
        report_period_table_name = GCP_REPORT_TABLE_MAP["bill"]
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
                table_name=f"{partitioned_table_name}_2015_01",
                partition_of_table_name=partitioned_table_name,
                partition_type=PartitionedTable.RANGE,
                partition_col="usage_start",
                partition_parameters={"default": False, "from": "2015-01-01", "to": "2015-02-01"},
                active=True,
            )
            test_part.save()

            self.assertTrue(table_exists(self.schema, test_part.table_name))

            report_period_start = datetime.datetime(2015, 1, 1, tzinfo=pytz.UTC)
            report_period_end = datetime.datetime(2015, 1, 31, tzinfo=pytz.UTC)
            report_period = report_period_model(
                billing_period_start=report_period_start,
                billing_period_end=report_period_end,
                provider_id=provider.uuid,
            )
            report_period.save()

            usage_date = datetime.date(2015, 1, 12)
            lids_rec = partitioned_table_model(
                usage_start=usage_date,
                usage_end=usage_date,
                cost_entry_bill_id=report_period.id,
                account_id="11111-11111",
                project_id="0101010101",
                project_name="gcp-eek",
                uuid=uuid.uuid4(),
            )
            lids_rec.save()

            cutoff_date = datetime.datetime(2015, 12, 31, tzinfo=pytz.UTC)
            cleaner = GCPReportDBCleaner(self.schema)
            removed_data = cleaner.purge_expired_report_data(cutoff_date, simulate=False)

            self.assertEqual(len(removed_data), 1)
            self.assertFalse(table_exists(self.schema, test_part.table_name))
