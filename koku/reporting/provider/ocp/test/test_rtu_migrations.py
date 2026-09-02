#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for RatesToUsage CASCADE foreign keys."""
from datetime import date
from decimal import Decimal

from django_tenants.utils import tenant_context
from model_bakery import baker

from cost_models.models import CostModel
from cost_models.models import PriceList
from cost_models.models import PriceListCostModelMap
from cost_models.models import Rate
from koku.pg_partition import PartitionHandlerMixin
from masu.test import MasuTestCase
from reporting.provider.ocp.models import RatesToUsage


class RatesToUsageCascadeTest(MasuTestCase):
    """Deleting a Rate or CostModel must remove related RatesToUsage rows."""

    def _ensure_rtu_partition(self, usage_start):
        PartitionHandlerMixin()._handle_partitions(
            self.schema,
            ["rates_to_usage"],
            usage_start,
            usage_start,
        )

    def _create_rtu_row(self, *, rate, cost_model, usage_start=None):
        usage_start = usage_start or self.dh.this_month_start.date()
        self._ensure_rtu_partition(usage_start)
        return baker.make(
            RatesToUsage,
            rate=rate,
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

    def tearDown(self):
        with tenant_context(self.tenant):
            CostModel.objects.filter(name__startswith="RTU ").delete()
        super().tearDown()

    def test_cascade_deletes_rtu_when_rate_deleted(self):
        """CASCADE removes RTU rows when a Rate is deleted."""
        with tenant_context(self.tenant):
            cost_model, rate = self._create_cost_model_rate(name="RTU Rate CASCADE CM")
            rtu = self._create_rtu_row(rate=rate, cost_model=cost_model)
            rtu_uuid = rtu.uuid

            rate.delete()

            self.assertFalse(RatesToUsage.objects.filter(uuid=rtu_uuid).exists())

    def test_cascade_deletes_rtu_when_cost_model_deleted(self):
        """CASCADE removes RTU rows when a CostModel is deleted."""
        with tenant_context(self.tenant):
            cost_model, rate = self._create_cost_model_rate(name="RTU CM CASCADE CM")
            rtu = self._create_rtu_row(rate=rate, cost_model=cost_model)
            rtu_uuid = rtu.uuid

            cost_model.delete()

            self.assertFalse(RatesToUsage.objects.filter(uuid=rtu_uuid).exists())
