#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Unit tests for OCP provider map behavior."""
from __future__ import annotations

from decimal import Decimal

from django.db.models import DecimalField
from django.db.models import Sum
from django.db.models import Value
from django_tenants.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.models import Provider
from api.report.ocp.provider_map import OCPProviderMap
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary


class OCPProviderMapTest(IamTestCase):
    def test_distributed_costs_use_correct_exchange_rate(self):
        """Ensure different distributed cost types use their respective exchange rates (Cursor.ai assisted)."""
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

    def test_wasted_cost_cpu_reads_precomputed_column_with_exchange_rate(self):
        """wasted_cpu_cost_expr sums the pre-computed column and applies exchange_rate.

        The SQL summarization pre-computes per-pod waste before any cross-pod aggregation,
        avoiding the pooling problem (over- and under-utilised pods cancelling each other).
        The provider map expression simply reads that value and converts to display currency.
        """
        cluster_id = "s1a-waste-test-cpu"
        usage_date = self.dh.yesterday.date()
        _dec = DecimalField(max_digits=33, decimal_places=15)
        exchange_rate = Value(Decimal("2"), output_field=_dec)

        with tenant_context(self.tenant):
            OCPUsageLineItemDailySummary.objects.filter(cluster_id=cluster_id).delete()

            # Row representing a pod group with pre-computed waste=50 (e.g. 50% waste on 100 cost)
            self.baker.make(
                OCPUsageLineItemDailySummary,
                cluster_id=cluster_id,
                data_source="Pod",
                namespace="s1a-test",
                usage_start=usage_date,
                usage_end=usage_date,
                wasted_cpu_cost=Decimal("50"),
            )
            # Row representing an over-utilised pod group — waste already clamped to 0 by SQL
            self.baker.make(
                OCPUsageLineItemDailySummary,
                cluster_id=cluster_id,
                data_source="Pod",
                namespace="s1a-test",
                usage_start=usage_date,
                usage_end=usage_date,
                wasted_cpu_cost=Decimal("0"),
            )

            mapper = OCPProviderMap(provider=Provider.PROVIDER_OCP, report_type="cpu", schema_name=self.schema_name)
            aggregates = mapper.report_type_map["aggregates"]
            qs = OCPUsageLineItemDailySummary.objects.filter(cluster_id=cluster_id, data_source="Pod").annotate(
                exchange_rate=exchange_rate,
                infra_exchange_rate=exchange_rate,
            )
            result = qs.aggregate(wasted_cost=aggregates["wasted_cost"])
            # SUM(50 + 0) * exchange_rate(2) = 100
            self.assertEqual(result["wasted_cost"], Decimal("100"))

    def test_wasted_cost_memory_reads_precomputed_column_with_exchange_rate(self):
        """wasted_memory_cost_expr mirrors the CPU expression for the memory report."""
        cluster_id = "s1a-waste-test-mem"
        usage_date = self.dh.yesterday.date()
        _dec = DecimalField(max_digits=33, decimal_places=15)
        one = Value(Decimal("1"), output_field=_dec)

        with tenant_context(self.tenant):
            OCPUsageLineItemDailySummary.objects.filter(cluster_id=cluster_id).delete()

            self.baker.make(
                OCPUsageLineItemDailySummary,
                cluster_id=cluster_id,
                data_source="Pod",
                namespace="s1a-test",
                usage_start=usage_date,
                usage_end=usage_date,
                wasted_memory_cost=Decimal("30"),
            )
            self.baker.make(
                OCPUsageLineItemDailySummary,
                cluster_id=cluster_id,
                data_source="Pod",
                namespace="s1a-test",
                usage_start=usage_date,
                usage_end=usage_date,
                wasted_memory_cost=Decimal("20"),
            )

            mapper = OCPProviderMap(provider=Provider.PROVIDER_OCP, report_type="memory", schema_name=self.schema_name)
            aggregates = mapper.report_type_map["aggregates"]
            qs = OCPUsageLineItemDailySummary.objects.filter(cluster_id=cluster_id, data_source="Pod").annotate(
                exchange_rate=one,
                infra_exchange_rate=one,
            )
            result = qs.aggregate(wasted_cost=aggregates["wasted_cost"])
            self.assertEqual(result["wasted_cost"], Decimal("50"))

    def test_wasted_cost_null_column_contributes_zero(self):
        """Rows without a pre-computed wasted_cost (NULL) are treated as zero."""
        cluster_id = "s1a-waste-test-null"
        usage_date = self.dh.yesterday.date()
        _dec = DecimalField(max_digits=33, decimal_places=15)
        one = Value(Decimal("1"), output_field=_dec)

        with tenant_context(self.tenant):
            OCPUsageLineItemDailySummary.objects.filter(cluster_id=cluster_id).delete()

            self.baker.make(
                OCPUsageLineItemDailySummary,
                cluster_id=cluster_id,
                data_source="Pod",
                namespace="s1a-test",
                usage_start=usage_date,
                usage_end=usage_date,
                wasted_cpu_cost=None,
            )

            mapper = OCPProviderMap(provider=Provider.PROVIDER_OCP, report_type="cpu", schema_name=self.schema_name)
            aggregates = mapper.report_type_map["aggregates"]
            qs = OCPUsageLineItemDailySummary.objects.filter(cluster_id=cluster_id, data_source="Pod").annotate(
                exchange_rate=one,
                infra_exchange_rate=one,
            )
            result = qs.aggregate(wasted_cost=aggregates["wasted_cost"])
            self.assertEqual(result["wasted_cost"], Decimal("0"))

    def test_per_row_cost_cpu_sums_to_aggregate_cost_total(self):
        """Sanity: Sum(row infra + markup + cm cpu) matches existing cost_total aggregate."""
        cluster_id = "s1a-cost-consistency"
        usage_date = self.dh.yesterday.date()
        _dec = DecimalField(max_digits=33, decimal_places=15)
        one = Value(Decimal("1"), output_field=_dec)

        with tenant_context(self.tenant):
            OCPUsageLineItemDailySummary.objects.filter(cluster_id=cluster_id).delete()

            self.baker.make(
                OCPUsageLineItemDailySummary,
                cluster_id=cluster_id,
                data_source="Pod",
                namespace="s1a-test",
                usage_start=usage_date,
                usage_end=usage_date,
                infrastructure_raw_cost=Decimal("30"),
                infrastructure_markup_cost=Decimal("7"),
                cost_model_cpu_cost=Decimal("5"),
                pod_request_cpu_core_hours=Decimal("1"),
                pod_usage_cpu_core_hours=Decimal("1"),
            )
            self.baker.make(
                OCPUsageLineItemDailySummary,
                cluster_id=cluster_id,
                data_source="Pod",
                namespace="s1a-test",
                usage_start=usage_date,
                usage_end=usage_date,
                infrastructure_raw_cost=Decimal("10"),
                infrastructure_markup_cost=Decimal("2"),
                cost_model_cpu_cost=Decimal("1"),
                pod_request_cpu_core_hours=Decimal("1"),
                pod_usage_cpu_core_hours=Decimal("1"),
            )

            mapper = OCPProviderMap(provider=Provider.PROVIDER_OCP, report_type="cpu", schema_name=self.schema_name)
            aggregates = mapper.report_type_map["aggregates"]
            qs = OCPUsageLineItemDailySummary.objects.filter(cluster_id=cluster_id, data_source="Pod").annotate(
                exchange_rate=one,
                infra_exchange_rate=one,
            )
            row_cost = mapper._per_row_cost_cpu_expr()
            summed = qs.aggregate(from_rows=Sum(row_cost), cost_total=aggregates["cost_total"])
            self.assertEqual(summed["from_rows"], summed["cost_total"])

    def test_wasted_cost_order_by_desc_matches_annotation(self):
        """Grouped wasted_cost annotation is sortable (used by order_by[wasted_cost])."""
        cluster_id = "s1a-waste-order"
        usage_date = self.dh.yesterday.date()
        _dec = DecimalField(max_digits=33, decimal_places=15)
        one = Value(Decimal("1"), output_field=_dec)

        with tenant_context(self.tenant):
            OCPUsageLineItemDailySummary.objects.filter(cluster_id=cluster_id).delete()

            self.baker.make(
                OCPUsageLineItemDailySummary,
                cluster_id=cluster_id,
                data_source="Pod",
                namespace="low-waste",
                usage_start=usage_date,
                usage_end=usage_date,
                wasted_cpu_cost=Decimal("10"),
            )
            self.baker.make(
                OCPUsageLineItemDailySummary,
                cluster_id=cluster_id,
                data_source="Pod",
                namespace="high-waste",
                usage_start=usage_date,
                usage_end=usage_date,
                wasted_cpu_cost=Decimal("90"),
            )

            mapper = OCPProviderMap(provider=Provider.PROVIDER_OCP, report_type="cpu", schema_name=self.schema_name)
            ann = mapper.report_type_map["annotations"]
            rows = list(
                OCPUsageLineItemDailySummary.objects.filter(cluster_id=cluster_id, data_source="Pod")
                .annotate(exchange_rate=one, infra_exchange_rate=one)
                .values("namespace")
                .annotate(**{k: ann[k] for k in ("wasted_cost",) if k in ann})
                .order_by("-wasted_cost")
            )
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["namespace"], "high-waste")
            self.assertEqual(rows[1]["namespace"], "low-waste")
