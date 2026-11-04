#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""rates_to_usage has no database FK to its report period or source (work log item 3).

Deleting a provider or a report period must not cascade into the partitioned table in the
database; Provider.delete and the OCP retention purges delete the rows explicitly instead.
"""
from unittest.mock import patch
from uuid import uuid4

from django.db import connection
from django_tenants.utils import schema_context
from model_bakery import baker

from koku.pg_partition import PartitionHandlerMixin
from masu.processor.ocp.ocp_report_db_cleaner import OCPReportDBCleaner
from masu.test import MasuTestCase
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting.provider.ocp.models import RatesToUsage
from reporting.provider.ocp.test.test_rtu_migrations import FK_COLUMNS_SQL

CUSTOM_NAME = "RTU parent delete test"


class RatesToUsageParentDeleteTest(MasuTestCase):
    """Explicit deletes replace the report period and source cascades."""

    def _rtu_row(self, source_uuid, report_period_id, usage_start=None):
        usage_start = usage_start or self.dh.this_month_start.date()
        PartitionHandlerMixin()._handle_partitions(self.schema, ["rates_to_usage"], usage_start, usage_start)
        return baker.make(
            RatesToUsage,
            source_uuid_id=source_uuid,
            report_period_id=report_period_id,
            usage_start=usage_start,
            usage_end=usage_start,
            cluster_id="rtu-parent-test",
            custom_name=CUSTOM_NAME,
            metric_type="CPU",
        )

    def _report_period(self, provider_uuid):
        return OCPUsageReportPeriod.objects.filter(provider_id=provider_uuid).order_by("-report_period_start").first()

    def test_no_report_period_or_source_constraint(self):
        """Only cost_category_id keeps a database FK."""
        with schema_context(self.schema), connection.cursor() as cursor:
            cursor.execute(FK_COLUMNS_SQL, [self.schema])
            fk_columns = dict(cursor.fetchall())
        self.assertNotIn("report_period_id", fk_columns)
        self.assertNotIn("source_uuid", fk_columns)

    def test_insert_with_unknown_report_period_and_source_succeeds(self):
        """A pipeline insert racing a provider delete must not fail (COST-8112, Finding B)."""
        with schema_context(self.schema):
            rtu = self._rtu_row(uuid4(), 2_000_000_000)
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            self.assertTrue(RatesToUsage.objects.filter(uuid=rtu.uuid).exists())

    @patch("masu.celery.tasks.delete_archived_data")
    def test_provider_delete_removes_its_rows_only(self, _):
        """Provider.delete deletes the rows of that source and leaves other sources alone."""
        with schema_context(self.schema):
            mine = self._rtu_row(self.ocp_provider_uuid, self._report_period(self.ocp_provider_uuid).id)
            other = self._rtu_row(self.ocpaws_provider_uuid, self._report_period(self.ocpaws_provider_uuid).id)

            self.ocp_provider.delete()

            self.assertFalse(RatesToUsage.objects.filter(uuid=mine.uuid).exists())
            self.assertTrue(RatesToUsage.objects.filter(uuid=other.uuid).exists())

    def test_purge_by_provider_removes_its_rows_only(self):
        """The provider purge deletes rows of the provider's report periods only."""
        with schema_context(self.schema):
            mine = self._rtu_row(self.ocp_provider_uuid, self._report_period(self.ocp_provider_uuid).id)
            other = self._rtu_row(self.ocpaws_provider_uuid, self._report_period(self.ocpaws_provider_uuid).id)

        OCPReportDBCleaner(self.schema).purge_expired_report_data(provider_uuid=self.ocp_provider_uuid)

        with schema_context(self.schema):
            self.assertFalse(RatesToUsage.objects.filter(uuid=mine.uuid).exists())
            self.assertTrue(RatesToUsage.objects.filter(uuid=other.uuid).exists())

    def test_purge_by_date_removes_rows_of_expired_report_periods(self):
        """Rows of an expired report period go even when they sit in a partition the purge keeps."""
        with schema_context(self.schema):
            periods = OCPUsageReportPeriod.objects.filter(provider_id=self.ocp_provider_uuid).order_by(
                "report_period_start"
            )
            expired, current = periods.first(), periods.last()
            self.assertLess(expired.report_period_start, current.report_period_start)
            kept_month = current.report_period_start.date()
            expired_row = self._rtu_row(self.ocp_provider_uuid, expired.id, usage_start=kept_month)
            current_row = self._rtu_row(self.ocp_provider_uuid, current.id, usage_start=kept_month)

        OCPReportDBCleaner(self.schema).purge_expired_report_data(expired_date=expired.report_period_start)

        with schema_context(self.schema):
            self.assertFalse(OCPUsageReportPeriod.objects.filter(id=expired.id).exists())
            self.assertFalse(RatesToUsage.objects.filter(uuid=expired_row.uuid).exists())
            self.assertTrue(RatesToUsage.objects.filter(uuid=current_row.uuid).exists())
