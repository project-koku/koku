#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Unit tests for OCP provider map behavior."""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from django.db.models import DecimalField
from django.db.models import Value
from django_tenants.utils import tenant_context
from model_bakery import baker

from api.iam.test.iam_test_case import IamTestCase
from api.models import Provider
from api.report.ocp.provider_map import OCPProviderMap
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary


class OCPProviderMapTest(IamTestCase):
    def test_gpu_distributed_uses_cost_model_exchange_rate(self):
        """
        Ensure gpu_distributed (shown as gpu_unallocated_distributed) uses the cost model exchange rate.
        """
        usage_date = self.dh.yesterday.date()

        with tenant_context(self.tenant):
            baker.make(
                OCPUsageLineItemDailySummary,
                uuid=uuid4(),
                usage_start=usage_date,
                usage_end=usage_date,
                cost_model_rate_type="gpu_distributed",
                distributed_cost=Decimal("10"),
                raw_currency="CAD",
            )
            # Ensure other distributed types do not affect the gpu_distributed calculation.
            baker.make(
                OCPUsageLineItemDailySummary,
                uuid=uuid4(),
                usage_start=usage_date,
                usage_end=usage_date,
                cost_model_rate_type="worker_distributed",
                distributed_cost=Decimal("999"),
                raw_currency="CAD",
            )

            mapper = OCPProviderMap(
                provider=Provider.PROVIDER_OCP,
                report_type="costs_by_project",
                schema_name=self.tenant.schema_name,
            )

            # If the implementation incorrectly uses infra_exchange_rate, this would produce 30 instead of 20.
            result = OCPUsageLineItemDailySummary.objects.annotate(
                exchange_rate=Value(
                    Decimal("2"),
                    output_field=DecimalField(max_digits=33, decimal_places=15),
                ),
                infra_exchange_rate=Value(
                    Decimal("3"),
                    output_field=DecimalField(max_digits=33, decimal_places=15),
                ),
            ).aggregate(val=mapper.distributed_unallocated_gpu_cost)

            self.assertEqual(result["val"], Decimal("20"))
