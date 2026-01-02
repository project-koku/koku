#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Unit tests for OCP provider map behavior."""
from __future__ import annotations

from decimal import Decimal

from django.db.models import DecimalField
from django.db.models import Value
from django_tenants.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.models import Provider
from api.report.ocp.provider_map import OCPProviderMap
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary


class OCPProviderMapTest(IamTestCase):
    def test_distributed_costs_use_correct_exchange_rate(self):
        """Ensure different distributed cost types use their respective exchange rates."""
        usage_date = self.dh.yesterday.date()
        cost_val = Decimal("10")

        # Matrix: (internal_rate_type, mapper_property_name, expected_multiplier)
        # We use multiplier 2 for cost-model rate and 3 for infra rate.
        test_matrix = [
            ("gpu_distributed", "distributed_unallocated_gpu_cost", Decimal("2")),
            ("platform_distributed", "distributed_platform_cost", Decimal("2")),
            ("worker_distributed", "distributed_worker_cost", Decimal("2")),
            ("unattributed_storage", "distributed_unattributed_storage_cost", Decimal("3")),
            ("unattributed_network", "distributed_unattributed_network_cost", Decimal("3")),
        ]

        with tenant_context(self.tenant):
            mapper = OCPProviderMap(
                provider=Provider.PROVIDER_OCP,
                report_type="costs_by_project",
                schema_name=self.schema_name,
            )

            for rate_type, mapper_attr, expected_multiplier in test_matrix:
                with self.subTest(rate_type=rate_type):
                    # Clean up for each subtest
                    OCPUsageLineItemDailySummary.objects.all().delete()

                    # Create the target record
                    self.baker.make(
                        OCPUsageLineItemDailySummary,
                        usage_start=usage_date,
                        usage_end=usage_date,
                        cost_model_rate_type=rate_type,
                        distributed_cost=cost_val,
                        raw_currency="CAD",
                    )

                    # Create a "bogus" record to ensure the mapper filters correctly
                    bogus_type = "other" if rate_type != "other" else "bogus"
                    self.baker.make(
                        OCPUsageLineItemDailySummary,
                        cost_model_rate_type=bogus_type,
                        distributed_cost=Decimal("1000"),
                    )

                    result = OCPUsageLineItemDailySummary.objects.annotate(
                        exchange_rate=Value(Decimal("2"), output_field=DecimalField(max_digits=33, decimal_places=15)),
                        infra_exchange_rate=Value(
                            Decimal("3"), output_field=DecimalField(max_digits=33, decimal_places=15)
                        ),
                    ).aggregate(val=getattr(mapper, mapper_attr))

                    self.assertEqual(result["val"], cost_val * expected_multiplier)
