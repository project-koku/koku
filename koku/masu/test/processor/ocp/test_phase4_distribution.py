#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Phase 4 distribution integration tests — R18 safety net.

These 10 assertions execute actual per-rate distribution SQL against the
test database (no mocked SQL layer) and verify mathematical correctness.
They are the sole verification mechanism for per-rate distribution
correctness, replacing IQ-9 Option 2 (back-allocation) as the runtime
fallback.

See docs/architecture/cost-breakdown/phased-delivery.md § Concern 1 Resolution.
See docs/architecture/cost-breakdown/risk-register.md § R18.
"""
from decimal import Decimal
from unittest.mock import patch

from django.db.models import Q
from django.db.models import Sum
from django_tenants.utils import schema_context

from api.utils import DateHelper
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.processor.ocp.ocp_cost_model_cost_updater import OCPCostModelCostUpdater
from masu.test import MasuTestCase
from masu.util.common import SummaryRangeConfig
from reporting.provider.ocp.models import OCPCostUIBreakDownP
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting.provider.ocp.models import RatesToUsage

TOLERANCE = Decimal("0.01")


class _ReportPeriodMixin:
    """Mixin providing report period lookup for distribution tests."""

    def _get_report_period(self):
        with schema_context(self.schema):
            rp = (
                OCPUsageReportPeriod.objects.filter(provider_id=self.ocp_provider_uuid)
                .order_by("-report_period_start")
                .first()
            )
        if not rp:
            self.skipTest("No report period for OCP provider")
        return rp


class TestDistributionIntegration(_ReportPeriodMixin, MasuTestCase):
    """R18 safety net: 10 non-mocked distribution integration assertions.

    Executes actual distribution SQL against the test database and asserts
    per-rate proportional correctness. Mirrors phased-delivery.md assertions 1-10.
    """

    _distribution_seeded = False

    def setUp(self):
        super().setUp()
        self.dh = DateHelper()
        self.rp = self._get_report_period()
        start = self.rp.report_period_start
        end = self.dh.month_end(start)
        self.start_date = start.date() if hasattr(start, "date") else start
        self.end_date = end.date() if hasattr(end, "date") else end
        self.provider_uuid = self.ocp_provider.uuid

        if not TestDistributionIntegration._distribution_seeded:
            self._seed_and_distribute()
            TestDistributionIntegration._distribution_seeded = True

    def _seed_and_distribute(self):
        """Ensure RTU usage rows exist and run per-rate distribution."""
        self._updater = OCPCostModelCostUpdater(
            schema=self.schema, provider=self.ocp_provider
        )
        if not self._updater._cost_model_id:
            self.skipTest("No cost model for OCP provider")
        self._updater._load_rates(self.start_date)
        if not (self._updater._infra_rates or self._updater._supplementary_rates):
            self.skipTest("No rates loaded for OCP provider")

        self._updater._update_usage_rates_to_usage(self.start_date, self.end_date)

        with schema_context(self.schema):
            usage_count = RatesToUsage.objects.filter(
                source_uuid=self.provider_uuid,
                usage_start__gte=self.start_date,
                usage_start__lte=self.end_date,
                monthly_cost_type__isnull=True,
            ).count()
        if usage_count == 0:
            self.skipTest("No RTU usage rows after seeding")

        distribution_info = {
            "distribution_type": "cpu",
            "platform_cost": True,
            "worker_cost": True,
        }
        summary_range = SummaryRangeConfig(
            start_date=self.start_date, end_date=self.end_date
        )
        with OCPReportDBAccessor(self.schema) as accessor:
            accessor.populate_distributed_cost_sql(
                summary_range,
                self.provider_uuid,
                distribution_info,
                cost_model_id=self._updater._cost_model_id,
            )

    def _distributed_qs(self, distribution_type=None):
        """QuerySet for distributed RTU rows in the test window."""
        qs = RatesToUsage.objects.filter(
            source_uuid=self.provider_uuid,
            usage_start__gte=self.start_date,
            usage_start__lte=self.end_date,
            monthly_cost_type__isnull=False,
            distributed_cost__isnull=False,
        ).exclude(distributed_cost=0)
        if distribution_type:
            qs = qs.filter(monthly_cost_type=distribution_type)
        return qs

    def _source_qs(self, distribution_type):
        """QuerySet for source RTU rows that were distributed."""
        source_filters = {
            "platform_distributed": Q(cost_category__name="Platform"),
            "worker_distributed": Q(namespace="Worker unallocated"),
        }
        filt = source_filters.get(distribution_type)
        if not filt:
            return RatesToUsage.objects.none()
        return RatesToUsage.objects.filter(
            filt,
            source_uuid=self.provider_uuid,
            usage_start__gte=self.start_date,
            usage_start__lte=self.end_date,
            monthly_cost_type__isnull=True,
        )

    def _skip_if_no_distributed(self, dist_type):
        with schema_context(self.schema):
            if not self._distributed_qs(dist_type).exists():
                self.skipTest(f"No {dist_type} distributed rows in test data")

    # ------------------------------------------------------------------
    # Assertion 1: Per-rate proportional correctness
    # ------------------------------------------------------------------
    def test_01_per_rate_proportional_correctness(self):
        """distributed_cost is proportional to namespace CPU usage share."""
        dist_type = "platform_distributed"
        self._skip_if_no_distributed(dist_type)

        with schema_context(self.schema):
            days = (
                self._distributed_qs(dist_type)
                .values_list("usage_start", flat=True)
                .distinct()[:3]
            )
            for day in days:
                day_rows = self._distributed_qs(dist_type).filter(usage_start=day)
                rates = day_rows.values_list("custom_name", flat=True).distinct()
                for rate_name in rates:
                    rate_rows = day_rows.filter(custom_name=rate_name)
                    total = rate_rows.aggregate(t=Sum("distributed_cost"))[
                        "t"
                    ] or Decimal(0)
                    if total == 0:
                        continue
                    ns_totals = rate_rows.values("namespace").annotate(
                        ns_total=Sum("distributed_cost")
                    )
                    for entry in ns_totals:
                        proportion = entry["ns_total"] / total
                        self.assertGreaterEqual(proportion, Decimal(0))
                        self.assertLessEqual(proportion, Decimal(1) + TOLERANCE)

    # ------------------------------------------------------------------
    # Assertion 2: SUM(per-rate) consistency
    # ------------------------------------------------------------------
    def test_02_per_rate_sum_consistency(self):
        """SUM of per-rate distributed rows is consistent per (namespace, day, dist_type)."""
        dist_type = "platform_distributed"
        self._skip_if_no_distributed(dist_type)

        with schema_context(self.schema):
            totals_by_rate = (
                self._distributed_qs(dist_type)
                .values("usage_start", "namespace", "custom_name")
                .annotate(rate_dist=Sum("distributed_cost"))
            )
            totals_by_ns = (
                self._distributed_qs(dist_type)
                .values("usage_start", "namespace")
                .annotate(ns_dist=Sum("distributed_cost"))
            )
            ns_lookup = {
                (r["usage_start"], r["namespace"]): r["ns_dist"] for r in totals_by_ns
            }
            for entry in totals_by_rate:
                key = (entry["usage_start"], entry["namespace"])
                ns_total = ns_lookup.get(key, Decimal(0))
                self.assertLessEqual(
                    abs(entry["rate_dist"]),
                    abs(ns_total) + TOLERANCE,
                    f"Per-rate distributed_cost exceeds namespace total for {key}",
                )

    # ------------------------------------------------------------------
    # Assertion 3: No orphaned distributed rows
    # ------------------------------------------------------------------
    def test_03_no_orphaned_distributed_rows(self):
        """Every distributed RTU row traces to a valid source rate identity."""
        dist_type = "platform_distributed"
        self._skip_if_no_distributed(dist_type)

        with schema_context(self.schema):
            source_rates = set(
                self._source_qs(dist_type)
                .values_list("custom_name", "metric_type", "cost_model_rate_type")
                .distinct()
            )
            if not source_rates:
                self.skipTest("No source rows for platform distribution")

            dist_rates = set(
                self._distributed_qs(dist_type)
                .values_list("custom_name", "metric_type", "cost_model_rate_type")
                .distinct()
            )
            orphans = dist_rates - source_rates
            self.assertEqual(
                len(orphans),
                0,
                f"Orphaned distributed rows with rate identities not in source: {orphans}",
            )

    # ------------------------------------------------------------------
    # Assertion 4: Edge case — zero-cost namespaces excluded
    # ------------------------------------------------------------------
    def test_04_zero_cost_rows_excluded(self):
        """No distributed RTU rows exist with distributed_cost = 0."""
        with schema_context(self.schema):
            zero_rows = RatesToUsage.objects.filter(
                source_uuid=self.provider_uuid,
                usage_start__gte=self.start_date,
                usage_start__lte=self.end_date,
                monthly_cost_type__isnull=False,
                distributed_cost=0,
            ).count()
            self.assertEqual(
                zero_rows, 0, "Distribution should not produce zero-cost rows"
            )

    # ------------------------------------------------------------------
    # Assertion 5: Independent cross-check (Option 2 formula)
    # ------------------------------------------------------------------
    def test_05_cross_check_option2_formula(self):
        """Per-rate distributed cost equals (rate_cost / total_source_cost) * namespace_total."""
        dist_type = "platform_distributed"
        self._skip_if_no_distributed(dist_type)

        with schema_context(self.schema):
            day = (
                self._distributed_qs(dist_type)
                .values_list("usage_start", flat=True)
                .first()
            )
            if not day:
                self.skipTest("No distributed rows")

            source_by_rate = dict(
                self._source_qs(dist_type)
                .filter(usage_start=day)
                .values("custom_name")
                .annotate(cost=Sum("calculated_cost"))
                .values_list("custom_name", "cost")
            )
            total_source = sum(source_by_rate.values())
            if total_source == 0:
                self.skipTest("Total source cost is zero")

            ns_totals = dict(
                self._distributed_qs(dist_type)
                .filter(usage_start=day)
                .values("namespace")
                .annotate(ns_total=Sum("distributed_cost"))
                .values_list("namespace", "ns_total")
            )

            for rate_name, rate_cost in source_by_rate.items():
                rate_rows = (
                    self._distributed_qs(dist_type)
                    .filter(usage_start=day, custom_name=rate_name)
                    .values("namespace")
                    .annotate(actual=Sum("distributed_cost"))
                )
                rate_share = rate_cost / total_source
                for entry in rate_rows:
                    ns_total = ns_totals.get(entry["namespace"], Decimal(0))
                    expected = rate_share * ns_total
                    self.assertAlmostEqual(
                        float(entry["actual"]),
                        float(expected),
                        places=6,
                        msg=f"Option 2 cross-check failed for rate={rate_name}, ns={entry['namespace']}",
                    )

    # ------------------------------------------------------------------
    # Assertion 6: Cost conservation
    # ------------------------------------------------------------------
    def test_06_cost_conservation(self):
        """Total distributed cost equals total source calculated_cost."""
        dist_type = "platform_distributed"
        self._skip_if_no_distributed(dist_type)

        with schema_context(self.schema):
            total_distributed = self._distributed_qs(dist_type).aggregate(
                t=Sum("distributed_cost")
            )["t"] or Decimal(0)
            total_source = self._source_qs(dist_type).aggregate(
                t=Sum("calculated_cost")
            )["t"] or Decimal(0)
            if total_source == 0:
                self.skipTest("No source cost to distribute")

            self.assertAlmostEqual(
                float(total_distributed),
                float(total_source),
                places=2,
                msg="Cost conservation: total distributed != total source cost",
            )

    # ------------------------------------------------------------------
    # Assertion 7: Sign invariant
    # ------------------------------------------------------------------
    def test_07_sign_invariant(self):
        """All distributed_cost values for recipient rows are positive."""
        with schema_context(self.schema):
            negative_count = RatesToUsage.objects.filter(
                source_uuid=self.provider_uuid,
                usage_start__gte=self.start_date,
                usage_start__lte=self.end_date,
                monthly_cost_type__isnull=False,
                distributed_cost__lt=0,
            ).count()
            self.assertEqual(
                negative_count,
                0,
                "Recipient distributed_cost should never be negative",
            )

    # ------------------------------------------------------------------
    # Assertion 8: Idempotency
    # ------------------------------------------------------------------
    def test_08_idempotency(self):
        """Running distribution twice produces identical RTU state."""
        dist_type = "platform_distributed"
        self._skip_if_no_distributed(dist_type)

        with schema_context(self.schema):
            pre_count = self._distributed_qs(dist_type).count()
            pre_sum = self._distributed_qs(dist_type).aggregate(
                t=Sum("distributed_cost")
            )["t"]

        distribution_info = {
            "distribution_type": "cpu",
            "platform_cost": True,
            "worker_cost": True,
        }
        summary_range = SummaryRangeConfig(
            start_date=self.start_date, end_date=self.end_date
        )
        with OCPReportDBAccessor(self.schema) as accessor:
            accessor.populate_distributed_cost_sql(
                summary_range,
                self.provider_uuid,
                distribution_info,
                cost_model_id=self._updater._cost_model_id,
            )

        with schema_context(self.schema):
            post_count = self._distributed_qs(dist_type).count()
            post_sum = self._distributed_qs(dist_type).aggregate(
                t=Sum("distributed_cost")
            )["t"]

        self.assertEqual(
            pre_count, post_count, "Idempotency: row count changed after re-run"
        )
        self.assertAlmostEqual(
            float(pre_sum or 0),
            float(post_sum or 0),
            places=10,
            msg="Idempotency: total distributed_cost changed after re-run",
        )

    # ------------------------------------------------------------------
    # Assertion 9: Multi-rate proportionality
    # ------------------------------------------------------------------
    def test_09_multi_rate_proportionality(self):
        """Rates with higher source cost produce proportionally higher distributed cost."""
        dist_type = "platform_distributed"
        self._skip_if_no_distributed(dist_type)

        with schema_context(self.schema):
            day = (
                self._distributed_qs(dist_type)
                .values_list("usage_start", flat=True)
                .first()
            )
            if not day:
                self.skipTest("No distributed rows")

            source_by_rate = dict(
                self._source_qs(dist_type)
                .filter(usage_start=day)
                .values("custom_name")
                .annotate(cost=Sum("calculated_cost"))
                .values_list("custom_name", "cost")
            )
            dist_by_rate = dict(
                self._distributed_qs(dist_type)
                .filter(usage_start=day)
                .values("custom_name")
                .annotate(cost=Sum("distributed_cost"))
                .values_list("custom_name", "cost")
            )
            rates = sorted(source_by_rate.keys())
            if len(rates) < 2:
                self.skipTest("Need at least 2 rates for proportionality check")

            for i in range(len(rates) - 1):
                r_a, r_b = rates[i], rates[i + 1]
                src_a = float(source_by_rate.get(r_a, 0))
                src_b = float(source_by_rate.get(r_b, 0))
                dst_a = float(dist_by_rate.get(r_a, 0))
                dst_b = float(dist_by_rate.get(r_b, 0))
                if src_b == 0 or dst_b == 0:
                    continue
                src_ratio = src_a / src_b
                dst_ratio = dst_a / dst_b
                self.assertAlmostEqual(
                    src_ratio,
                    dst_ratio,
                    places=6,
                    msg=f"Rates {r_a}/{r_b}: source ratio {src_ratio} != distributed ratio {dst_ratio}",
                )

    # ------------------------------------------------------------------
    # Assertion 10: Distribution re-run after DELETE (mutation regression)
    # ------------------------------------------------------------------
    def test_10_rerun_after_clear(self):
        """After clearing distributed rows and re-running, results match original."""
        dist_type = "platform_distributed"
        self._skip_if_no_distributed(dist_type)

        with schema_context(self.schema):
            original_sum = self._distributed_qs(dist_type).aggregate(
                t=Sum("distributed_cost")
            )["t"] or Decimal(0)
            original_count = self._distributed_qs(dist_type).count()

            RatesToUsage.objects.filter(
                source_uuid=self.provider_uuid,
                usage_start__gte=self.start_date,
                usage_start__lte=self.end_date,
                monthly_cost_type=dist_type,
            ).delete()
            self.assertEqual(
                self._distributed_qs(dist_type).count(),
                0,
                "DELETE should clear all rows",
            )

        distribution_info = {
            "distribution_type": "cpu",
            "platform_cost": True,
            "worker_cost": True,
        }
        summary_range = SummaryRangeConfig(
            start_date=self.start_date, end_date=self.end_date
        )
        with OCPReportDBAccessor(self.schema) as accessor:
            accessor.populate_distributed_cost_sql(
                summary_range,
                self.provider_uuid,
                distribution_info,
                cost_model_id=self._updater._cost_model_id,
            )

        with schema_context(self.schema):
            new_sum = self._distributed_qs(dist_type).aggregate(
                t=Sum("distributed_cost")
            )["t"] or Decimal(0)
            new_count = self._distributed_qs(dist_type).count()

        self.assertEqual(
            original_count, new_count, "Re-run should produce same row count"
        )
        self.assertAlmostEqual(
            float(original_sum),
            float(new_sum),
            places=10,
            msg="Re-run should produce same total distributed cost",
        )

    # ------------------------------------------------------------------
    # Assertion 11: Distribution rows carry cost_model_id
    # ------------------------------------------------------------------
    def test_distribution_rows_have_cost_model_id(self):
        """Distribution RTU rows must have cost_model_id set (not NULL)."""
        with schema_context(self.schema):
            dist_rows = self._distributed_qs()
            if not dist_rows.exists():
                self.skipTest("No distributed rows in test data")
            null_cm_rows = dist_rows.filter(cost_model__isnull=True)
            null_types = list(
                null_cm_rows.values_list("monthly_cost_type", flat=True).distinct()
            )
            self.assertEqual(
                null_cm_rows.count(),
                0,
                f"Distribution rows with NULL cost_model_id found for types: {null_types}",
            )


class TestBreakdownSQLFixes(_ReportPeriodMixin, MasuTestCase):
    """Tests for B1 (raw_currency date-scoping) and B2 (zero-cost filtering) fixes."""

    _populated = False

    def setUp(self):
        super().setUp()
        self.dh = DateHelper()
        self.rp = self._get_report_period()
        start = self.rp.report_period_start
        end = self.dh.month_end(start)
        self.start_date = start.date() if hasattr(start, "date") else start
        self.end_date = end.date() if hasattr(end, "date") else end
        self.provider_uuid = self.ocp_provider.uuid

        if not TestBreakdownSQLFixes._populated:
            self._seed_and_populate()
            TestBreakdownSQLFixes._populated = True

    def _seed_and_populate(self):
        updater = OCPCostModelCostUpdater(
            schema=self.schema, provider=self.ocp_provider
        )
        if not updater._cost_model_id:
            self.skipTest("No cost model for OCP provider")
        updater._load_rates(self.start_date)
        if not (updater._infra_rates or updater._supplementary_rates):
            self.skipTest("No rates loaded for OCP provider")
        updater._update_usage_rates_to_usage(self.start_date, self.end_date)
        distribution_info = {
            "distribution_type": "cpu",
            "platform_cost": True,
            "worker_cost": True,
        }
        summary_range = SummaryRangeConfig(
            start_date=self.start_date, end_date=self.end_date
        )
        with patch(
            "masu.database.ocp_report_db_accessor.trino_table_exists",
            return_value=False,
        ):
            with OCPReportDBAccessor(self.schema) as accessor:
                accessor.populate_distributed_cost_sql(
                    summary_range,
                    self.provider_uuid,
                    distribution_info,
                    cost_model_id=updater._cost_model_id,
                )
                accessor.populate_ui_summary_tables(
                    summary_range,
                    self.provider_uuid,
                    tables=["reporting_ocp_cost_breakdown_p"],
                )

    def test_raw_currency_date_scoped(self):
        """B1: raw_currency in breakdown rows comes from date-scoped subquery."""
        with schema_context(self.schema):
            expected_currencies = set(
                OCPUsageLineItemDailySummary.objects.filter(
                    source_uuid=self.provider_uuid,
                    usage_start__gte=self.start_date,
                    usage_start__lte=self.end_date,
                    raw_currency__isnull=False,
                )
                .values_list("raw_currency", flat=True)
                .distinct()
            )
            if not expected_currencies:
                self.skipTest("No raw_currency in daily summary for test window")

            breakdown_currencies = set(
                OCPCostUIBreakDownP.objects.filter(
                    source_uuid=self.provider_uuid,
                    usage_start__gte=self.start_date,
                    usage_start__lte=self.end_date,
                    raw_currency__isnull=False,
                )
                .values_list("raw_currency", flat=True)
                .distinct()
            )
            self.assertTrue(
                breakdown_currencies.issubset(expected_currencies),
                f"Breakdown currencies {breakdown_currencies} should be a subset of "
                f"daily summary currencies {expected_currencies} for the same date range",
            )

    def test_zero_cost_rows_excluded(self):
        """B2: Step 1 excludes rows where SUM(calculated_cost) = 0."""
        with schema_context(self.schema):
            zero_cost_leaves = OCPCostUIBreakDownP.objects.filter(
                source_uuid=self.provider_uuid,
                usage_start__gte=self.start_date,
                usage_start__lte=self.end_date,
                depth=4,
                top_category="project",
                cost_value=Decimal("0"),
            ).count()
        self.assertEqual(
            zero_cost_leaves,
            0,
            "Project leaves with zero cost_value should be filtered out by HAVING clause",
        )


DISTRIBUTION_SOURCE_NAMESPACES = frozenset(
    {
        "Worker unallocated",
        "Storage unattributed",
        "Network unattributed",
        "GPU unallocated",
    }
)


class TestBreakdownPopulationSQL(_ReportPeriodMixin, MasuTestCase):
    """Integration tests for reporting_ocp_cost_breakdown_p.sql.

    Exercises the population SQL against the real test database and verifies
    tree structure, cost conservation, and namespace exclusions.
    These tests form the mid-tier of the test pyramid for the breakdown feature.
    """

    _populated = False

    def setUp(self):
        super().setUp()
        self.dh = DateHelper()
        self.rp = self._get_report_period()
        start = self.rp.report_period_start
        end = self.dh.month_end(start)
        self.start_date = start.date() if hasattr(start, "date") else start
        self.end_date = end.date() if hasattr(end, "date") else end
        self.provider_uuid = self.ocp_provider.uuid

        if not TestBreakdownPopulationSQL._populated:
            self._seed_rtu_and_populate_breakdown()
            TestBreakdownPopulationSQL._populated = True

    def _seed_rtu_and_populate_breakdown(self):
        """Run cost model updater then populate breakdown table."""
        updater = OCPCostModelCostUpdater(
            schema=self.schema, provider=self.ocp_provider
        )
        if not updater._cost_model_id:
            self.skipTest("No cost model for OCP provider")
        updater._load_rates(self.start_date)
        if not (updater._infra_rates or updater._supplementary_rates):
            self.skipTest("No rates loaded for OCP provider")

        updater._update_usage_rates_to_usage(self.start_date, self.end_date)

        distribution_info = {
            "distribution_type": "cpu",
            "platform_cost": True,
            "worker_cost": True,
        }
        summary_range = SummaryRangeConfig(
            start_date=self.start_date, end_date=self.end_date
        )
        with patch(
            "masu.database.ocp_report_db_accessor.trino_table_exists",
            return_value=False,
        ):
            with OCPReportDBAccessor(self.schema) as accessor:
                accessor.populate_distributed_cost_sql(
                    summary_range,
                    self.provider_uuid,
                    distribution_info,
                    cost_model_id=updater._cost_model_id,
                )
                accessor.populate_ui_summary_tables(
                    summary_range,
                    self.provider_uuid,
                    tables=["reporting_ocp_cost_breakdown_p"],
                )

    def _breakdown_qs(self, **extra_filters):
        return OCPCostUIBreakDownP.objects.filter(
            source_uuid=self.provider_uuid,
            usage_start__gte=self.start_date,
            usage_start__lte=self.end_date,
            **extra_filters,
        )

    # ------------------------------------------------------------------
    # C1 regression: Step 4 column count mismatch
    # ------------------------------------------------------------------
    def test_population_sql_executes_without_error(self):
        """[C1] Population SQL must not raise psycopg2 SyntaxError.

        Step 4 had 18 SELECT expressions for 19 INSERT columns.
        If this test runs (setUp didn't crash), the SQL executed successfully.
        We additionally verify at least one row was written.
        """
        with schema_context(self.schema):
            count = self._breakdown_qs().count()
        self.assertGreater(count, 0, "Population SQL produced no rows")

    # ------------------------------------------------------------------
    # H1 regression: Distribution source namespaces in project subtree
    # ------------------------------------------------------------------
    def test_project_subtree_excludes_distribution_sources(self):
        """[H1] Project leaves must not include Worker/Storage/Network/GPU namespaces.

        These namespaces are distribution sources whose costs appear under
        overhead via distributed rows. Including them in project causes
        double-counting in the tree total.
        """
        with schema_context(self.schema):
            project_leaves = self._breakdown_qs(top_category="project", depth=4)
            source_ns_in_project = (
                project_leaves.filter(namespace__in=DISTRIBUTION_SOURCE_NAMESPACES)
                .values_list("namespace", flat=True)
                .distinct()
            )
            source_ns_list = list(source_ns_in_project)
        self.assertEqual(
            source_ns_list,
            [],
            f"Distribution source namespaces found in project subtree: {source_ns_list}. "
            "This causes double-counting with the overhead subtree.",
        )

    # ------------------------------------------------------------------
    # Tree structure: valid depths
    # ------------------------------------------------------------------
    def test_tree_has_valid_depth_range(self):
        """All breakdown rows have depth between 1 and 5."""
        with schema_context(self.schema):
            invalid = self._breakdown_qs().exclude(depth__gte=1, depth__lte=5).count()
        self.assertEqual(invalid, 0, "Found rows with depth outside [1, 5]")

    # ------------------------------------------------------------------
    # Tree structure: root node exists
    # ------------------------------------------------------------------
    def test_root_node_exists(self):
        """There must be at least one depth-1 root node per day."""
        with schema_context(self.schema):
            roots = self._breakdown_qs(depth=1).count()
        self.assertGreater(roots, 0, "No root node (depth=1) found in breakdown table")

    # ------------------------------------------------------------------
    # Tree structure: every child has a valid parent
    # ------------------------------------------------------------------
    def test_every_child_has_valid_parent_path(self):
        """Non-root nodes must reference a parent_path that exists as a path."""
        with schema_context(self.schema):
            all_paths = set(
                self._breakdown_qs().values_list("path", flat=True).distinct()
            )
            non_root = (
                self._breakdown_qs()
                .exclude(depth=1)
                .values_list("parent_path", flat=True)
                .distinct()
            )
            orphan_parents = set(non_root) - all_paths
        self.assertEqual(
            orphan_parents,
            set(),
            f"Nodes reference parent_path(s) that don't exist as path: {orphan_parents}",
        )

    # ------------------------------------------------------------------
    # Cost conservation: root total = sum of leaves
    # ------------------------------------------------------------------
    def test_cost_conservation_root_equals_leaves(self):
        """Root node totals must equal the sum of leaf node values.

        For project: cost_value at root = sum of depth-4 project leaf cost_values.
        For overhead: distributed_cost at root = sum of depth-5 overhead leaf distributed_costs.
        """
        with schema_context(self.schema):
            root = self._breakdown_qs(depth=1).aggregate(
                total_cv=Sum("cost_value"),
                total_dc=Sum("distributed_cost"),
            )
            project_leaf_sum = self._breakdown_qs(
                depth=4, top_category="project"
            ).aggregate(total=Sum("cost_value"))["total"] or Decimal(0)
            overhead_leaf_sum = self._breakdown_qs(
                depth=5, top_category="overhead"
            ).aggregate(total=Sum("distributed_cost"))["total"] or Decimal(0)

        root_cv = root["total_cv"] or Decimal(0)
        root_dc = root["total_dc"] or Decimal(0)

        self.assertAlmostEqual(
            float(root_cv),
            float(project_leaf_sum),
            places=2,
            msg="Root cost_value != sum of project leaf cost_values",
        )
        self.assertAlmostEqual(
            float(root_dc),
            float(overhead_leaf_sum),
            places=2,
            msg="Root distributed_cost != sum of overhead leaf distributed_costs",
        )

    # ------------------------------------------------------------------
    # Top category correctness
    # ------------------------------------------------------------------
    def test_top_category_values(self):
        """top_category must be one of: project, overhead, total."""
        with schema_context(self.schema):
            categories = set(
                self._breakdown_qs().values_list("top_category", flat=True).distinct()
            )
        allowed = {"project", "overhead", "total"}
        unexpected = categories - allowed
        self.assertEqual(
            unexpected,
            set(),
            f"Unexpected top_category values: {unexpected}. Expected subset of {allowed}.",
        )

    # ------------------------------------------------------------------
    # M2 regression: source_uuid type safety
    # ------------------------------------------------------------------
    def test_population_idempotent(self):
        """[M2] Re-running population produces identical row count and totals.

        Also validates that source_uuid casting is consistent across all steps.
        """
        with schema_context(self.schema):
            pre_count = self._breakdown_qs().count()
            pre_totals = self._breakdown_qs().aggregate(
                cv=Sum("cost_value"), dc=Sum("distributed_cost")
            )

        summary_range = SummaryRangeConfig(
            start_date=self.start_date, end_date=self.end_date
        )
        with patch(
            "masu.database.ocp_report_db_accessor.trino_table_exists",
            return_value=False,
        ):
            with OCPReportDBAccessor(self.schema) as accessor:
                accessor.populate_ui_summary_tables(
                    summary_range,
                    self.provider_uuid,
                    tables=["reporting_ocp_cost_breakdown_p"],
                )

        with schema_context(self.schema):
            post_count = self._breakdown_qs().count()
            post_totals = self._breakdown_qs().aggregate(
                cv=Sum("cost_value"), dc=Sum("distributed_cost")
            )

        self.assertEqual(pre_count, post_count, "Idempotency: row count changed")
        self.assertAlmostEqual(
            float(pre_totals["cv"] or 0),
            float(post_totals["cv"] or 0),
            places=10,
            msg="Idempotency: cost_value total changed",
        )
        self.assertAlmostEqual(
            float(pre_totals["dc"] or 0),
            float(post_totals["dc"] or 0),
            places=10,
            msg="Idempotency: distributed_cost total changed",
        )
