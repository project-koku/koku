#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the RatesToUsage foreign keys to Rate and CostModel.

`rate_id` and `cost_model_id` are write-only traceability columns: nothing reads
them, and RTU is rebuilt per date range on every cost model run. They therefore
carry no database constraint and no cascade, so deleting a Rate or CostModel
never deletes from (or blocks inserts into) the partitioned rates_to_usage table.
The report period and source FKs keep their database-level CASCADE.
"""
from datetime import date
from decimal import Decimal
from uuid import uuid4

from django.db import connection
from django_tenants.utils import tenant_context
from model_bakery import baker

from cost_models.models import CostModel
from cost_models.models import PriceList
from cost_models.models import PriceListCostModelMap
from cost_models.models import Rate
from koku.pg_partition import PartitionHandlerMixin
from masu.test import MasuTestCase
from reporting.provider.ocp.models import RatesToUsage

FK_COLUMNS_SQL = """
SELECT a.attname, c.confdeltype
FROM pg_constraint c
JOIN pg_class t ON t.oid = c.conrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
WHERE n.nspname = %s
  AND t.relname = 'rates_to_usage'
  AND NOT t.relispartition
  AND c.contype = 'f'
"""


class RatesToUsageForeignKeyTest(MasuTestCase):
    """Rate and CostModel deletes leave rates_to_usage alone; provider and report period FKs still cascade."""

    def _ensure_rtu_partition(self, usage_start):
        PartitionHandlerMixin()._handle_partitions(
            self.schema,
            ["rates_to_usage"],
            usage_start,
            usage_start,
        )

    def _create_rtu_row(self, *, rate=None, rate_id=None, cost_model, usage_start=None):
        usage_start = usage_start or self.dh.this_month_start.date()
        self._ensure_rtu_partition(usage_start)
        return baker.make(
            RatesToUsage,
            rate=rate,
            rate_id=rate_id if rate is None else rate.uuid,
            cost_model=cost_model,
            source_uuid_id=self.ocp_provider_uuid,
            usage_start=usage_start,
            usage_end=usage_start,
            cluster_id=self.ocp_cluster_id,
            custom_name="CPU usage",
            metric_type="CPU",
        )

    def _create_cost_model_rate(self, name):
        cost_model = CostModel.objects.create(
            name=name,
            description="Test",
            source_type="OCP",
            rates=[],
        )
        price_list = PriceList.objects.create(
            name=f"{name} prices",
            description="Test",
            currency="USD",
            effective_start_date=date(2026, 3, 1),
            effective_end_date=date(2099, 12, 31),
            enabled=True,
            version=1,
            rates=[],
        )
        PriceListCostModelMap.objects.create(
            price_list=price_list,
            cost_model=cost_model,
            priority=1,
        )
        rate = Rate.objects.create(
            price_list=price_list,
            custom_name="CPU usage",
            metric="cpu_core_usage_per_hour",
            metric_type="CPU",
            cost_type="Infrastructure",
            default_rate=Decimal("0.01"),
        )
        return cost_model, rate

    def _fk_columns(self):
        """Map each FK column of the rates_to_usage parent table to its ON DELETE action."""
        with connection.cursor() as cursor:
            cursor.execute(FK_COLUMNS_SQL, [self.schema])
            return dict(cursor.fetchall())

    def tearDown(self):
        with tenant_context(self.tenant):
            RatesToUsage.objects.filter(custom_name="CPU usage", cluster_id=self.ocp_cluster_id).delete()
            CostModel.objects.filter(name__startswith="RTU ").delete()
        super().tearDown()

    def test_rate_and_cost_model_columns_have_no_constraint(self):
        """Only the report period and source FKs remain, and both cascade in the database."""
        with tenant_context(self.tenant):
            fk_columns = self._fk_columns()
        self.assertNotIn("rate_id", fk_columns)
        self.assertNotIn("cost_model_id", fk_columns)
        self.assertEqual(fk_columns.get("report_period_id"), "c")
        self.assertEqual(fk_columns.get("source_uuid"), "c")

    def test_rate_delete_keeps_rtu_rows(self):
        """Deleting a Rate does not touch rates_to_usage; the next rebuild of the range removes the rows."""
        with tenant_context(self.tenant):
            cost_model, rate = self._create_cost_model_rate(name="RTU Rate delete CM")
            rtu = self._create_rtu_row(rate=rate, cost_model=cost_model)

            rate.delete()

            self.assertTrue(RatesToUsage.objects.filter(uuid=rtu.uuid, rate_id=rtu.rate_id).exists())

    def test_cost_model_delete_keeps_rtu_rows(self):
        """Deleting a CostModel does not touch rates_to_usage."""
        with tenant_context(self.tenant):
            cost_model, rate = self._create_cost_model_rate(name="RTU CM delete CM")
            rtu = self._create_rtu_row(rate=rate, cost_model=cost_model)

            cost_model.delete()

            self.assertTrue(RatesToUsage.objects.filter(uuid=rtu.uuid).exists())

    def test_insert_with_deleted_rate_id_succeeds(self):
        """A pipeline insert that still carries a deleted rate's UUID must not fail (stale rate_uuid race)."""
        with tenant_context(self.tenant):
            cost_model, rate = self._create_cost_model_rate(name="RTU stale rate CM")
            stale_rate_id = rate.uuid
            rate.delete()

            rtu = self._create_rtu_row(rate_id=stale_rate_id, cost_model=cost_model)
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

            self.assertTrue(RatesToUsage.objects.filter(uuid=rtu.uuid, rate_id=stale_rate_id).exists())

    def test_insert_with_unknown_cost_model_id_succeeds(self):
        """cost_model_id is traceability only; an unknown UUID is stored as is."""
        with tenant_context(self.tenant):
            _, rate = self._create_cost_model_rate(name="RTU unknown CM")
            unknown_cost_model_id = uuid4()
            usage_start = self.dh.this_month_start.date()
            self._ensure_rtu_partition(usage_start)
            rtu = baker.make(
                RatesToUsage,
                rate=rate,
                cost_model_id=unknown_cost_model_id,
                source_uuid_id=self.ocp_provider_uuid,
                usage_start=usage_start,
                usage_end=usage_start,
                cluster_id=self.ocp_cluster_id,
                custom_name="CPU usage",
                metric_type="CPU",
            )
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

            self.assertTrue(RatesToUsage.objects.filter(uuid=rtu.uuid, cost_model_id=unknown_cost_model_id).exists())
