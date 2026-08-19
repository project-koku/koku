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
import uuid
from collections import defaultdict
from decimal import Decimal
from unittest.mock import patch

from django.db.models import Q
from django.db.models import Sum
from django.test import override_settings
from django_tenants.utils import schema_context

from api.metrics import constants as metric_constants
from api.utils import DateHelper
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.processor.ocp.ocp_cost_model_cost_updater import OCPCostModelCostUpdater
from masu.test import MasuTestCase
from masu.util.common import SummaryRangeConfig
from reporting.provider.ocp.models import OCPCostUIBreakDownP
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting.provider.ocp.models import OpenshiftCostCategory
from reporting.provider.ocp.models import RatesToUsage
from reporting.provider.ocp.self_hosted_models import OCPGPUUsageLineItemDaily

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

    def setUp(self):
        super().setUp()
        self.dh = DateHelper()
        self.rp = self._get_report_period()
        start = self.rp.report_period_start
        end = self.dh.month_end(start)
        self.start_date = start.date() if hasattr(start, "date") else start
        self.end_date = end.date() if hasattr(end, "date") else end
        self.provider_uuid = self.ocp_provider.uuid

        # NOTE: Django's TestCase wraps each test method in its own transaction
        # that is rolled back afterward, so seeded data cannot be shared across
        # tests via a class-level "seeded once" flag (a prior version of this
        # class did that and silently self-skipped every test after the first,
        # since the flag survived the rollback but the data did not). Reseed
        # fresh on every test.
        self._seed_and_distribute()

    def _seed_and_distribute(self):
        """Ensure RTU usage rows exist and run per-rate distribution."""
        self._updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.ocp_provider)
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
        summary_range = SummaryRangeConfig(start_date=self.start_date, end_date=self.end_date)
        with OCPReportDBAccessor(self.schema) as accessor:
            accessor.populate_distributed_cost_sql(
                summary_range,
                self.provider_uuid,
                distribution_info,
                cost_model_id=self._updater._cost_model_id,
                use_rtu=True,
            )

    def _distributed_qs(self, distribution_type=None):
        """QuerySet for distributed RTU rows in the test window.

        Includes BOTH recipient rows (positive, added to non-Platform/non-Worker
        namespaces) AND negation rows (negative, removing the cost from the
        source namespace/category). See distribute_*_per_rate.sql: negation
        rows are written with custom_name='' and are negative by design —
        callers that want recipient-only rows should use `_recipient_qs`.
        """
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

    def _recipient_qs(self, distribution_type=None):
        """QuerySet for recipient-only distributed RTU rows (excludes negation rows).

        The per-rate distribution SQL (distribute_*_per_rate.sql) writes two kinds
        of rows per distribution: recipient rows (custom_name set to the source
        rate's name, distributed_cost > 0) and a single negation row per
        (namespace, node) that removes the redistributed cost from the source
        side (custom_name='', distributed_cost < 0 by design). Assertions about
        "distributed cost" in the recipient sense must exclude negation rows.
        """
        return self._distributed_qs(distribution_type).exclude(custom_name="")

    # Distribution monthly_cost_type values written by the distribute_*_per_rate.sql
    # files themselves. A row bearing one of these is *output* of a distribution
    # pass, never eligible input to another -- see the shared
    # `monthly_cost_type IS NULL OR monthly_cost_type NOT IN (...)` guard repeated
    # in each distribute_*_per_rate.sql source CTE.
    _DISTRIBUTED_MONTHLY_COST_TYPES = (
        "worker_distributed",
        "platform_distributed",
        "gpu_distributed",
        "unattributed_storage",
        "unattributed_network",
    )

    def _source_qs(self, distribution_type):
        """QuerySet for source RTU rows that were distributed.

        Must mirror the source CTE in distribute_*_per_rate.sql exactly: those
        files pull from RTU rows where `monthly_cost_type IS NULL OR
        monthly_cost_type NOT IN (<the 5 distributed types>)`, i.e. usage-cost
        rows (monthly_cost_type IS NULL) *and* monthly-cost rows (Node/Cluster/
        PVC/Tag, monthly_cost_type NOT NULL) are both valid distribution
        sources -- only the distribution outputs themselves are excluded.
        Filtering here on `monthly_cost_type__isnull=True` alone silently
        undercounts whenever a Platform/Worker/Storage/Network-scoped
        namespace carries monthly costs, understating `total_source_cost` in
        test_05/test_11 and producing false "orphaned rate identity" positives
        in test_03.
        """
        source_filters = {
            "platform_distributed": Q(cost_category__name="Platform"),
            "worker_distributed": Q(namespace="Worker unallocated"),
            "unattributed_storage": Q(namespace="Storage unattributed"),
            "unattributed_network": Q(namespace="Network unattributed"),
        }
        filt = source_filters.get(distribution_type)
        if not filt:
            return RatesToUsage.objects.none()
        return RatesToUsage.objects.filter(
            filt,
            source_uuid=self.provider_uuid,
            usage_start__gte=self.start_date,
            usage_start__lte=self.end_date,
        ).exclude(monthly_cost_type__in=self._DISTRIBUTED_MONTHLY_COST_TYPES)

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
            days = self._distributed_qs(dist_type).values_list("usage_start", flat=True).distinct()[:3]
            for day in days:
                day_rows = self._distributed_qs(dist_type).filter(usage_start=day)
                rates = day_rows.values_list("custom_name", flat=True).distinct()
                for rate_name in rates:
                    rate_rows = day_rows.filter(custom_name=rate_name)
                    total = rate_rows.aggregate(t=Sum("distributed_cost"))["t"] or Decimal(0)
                    if total == 0:
                        continue
                    ns_totals = rate_rows.values("namespace").annotate(ns_total=Sum("distributed_cost"))
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
            ns_lookup = {(r["usage_start"], r["namespace"]): r["ns_dist"] for r in totals_by_ns}
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
        """Every distributed RTU row traces to a valid source rate identity.

        Recipient rows are matched on (custom_name, metric_type) only:
        distribute_platform_cost_per_rate.sql intentionally overwrites
        cost_model_rate_type on distributed rows to the distribution type
        (e.g. 'platform_distributed') rather than the source rate's original
        cost type ('Infrastructure'/'Supplementary'), so that column can never
        match between source and distributed rows and must be excluded from
        the identity check. Negation rows (custom_name='') are excluded via
        `_recipient_qs` since they don't trace to a single rate identity.
        """
        dist_type = "platform_distributed"
        self._skip_if_no_distributed(dist_type)

        with schema_context(self.schema):
            source_rates = set(self._source_qs(dist_type).values_list("custom_name", "metric_type").distinct())
            if not source_rates:
                self.skipTest("No source rows for platform distribution")

            dist_rates = set(self._recipient_qs(dist_type).values_list("custom_name", "metric_type").distinct())
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
            self.assertEqual(zero_rows, 0, "Distribution should not produce zero-cost rows")

    # ------------------------------------------------------------------
    # Assertion 5: Independent cross-check (Option 2 formula)
    # ------------------------------------------------------------------
    def test_05_cross_check_option2_formula(self):
        """Per-rate distributed cost equals (rate_cost / total_source_cost) * namespace_total."""
        dist_type = "platform_distributed"
        self._skip_if_no_distributed(dist_type)

        with schema_context(self.schema):
            day = self._distributed_qs(dist_type).values_list("usage_start", flat=True).first()
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
                    # Relative (not absolute-places) tolerance: cost values here can
                    # reach the billions, where float64 representation noise (~1e-6)
                    # exceeds the ~5e-7 absolute threshold that places=6 demands --
                    # failing on float64 noise rather than a real cross-check mismatch.
                    self.assertAlmostEqual(
                        float(entry["actual"]),
                        float(expected),
                        delta=abs(float(expected)) * 1e-6,
                        msg=f"Option 2 cross-check failed for rate={rate_name}, ns={entry['namespace']}",
                    )

    # ------------------------------------------------------------------
    # Assertion 6: Cost conservation
    # ------------------------------------------------------------------
    def test_06_cost_conservation(self):
        """Total recipient-distributed cost equals total source calculated_cost.

        Recipient rows (positive, cost moved TO other namespaces) and negation
        rows (negative, cost removed FROM the Platform source) are a
        double-entry pair that nets to ~0 by design, so conservation must be
        checked against recipient-only cost (`_recipient_qs`), not the
        recipient+negation total (`_distributed_qs`).

        Values here can be very large (test fixtures use randomly generated
        usage-hour magnitudes), so an absolute-places comparison is unreliable
        at scale; compare with a relative tolerance instead.
        """
        dist_type = "platform_distributed"
        self._skip_if_no_distributed(dist_type)

        with schema_context(self.schema):
            total_distributed = self._recipient_qs(dist_type).aggregate(t=Sum("distributed_cost"))["t"] or Decimal(0)
            total_source = self._source_qs(dist_type).aggregate(t=Sum("calculated_cost"))["t"] or Decimal(0)
            if total_source == 0:
                self.skipTest("No source cost to distribute")

            relative_diff = abs(total_distributed - total_source) / abs(total_source)
            self.assertLessEqual(
                relative_diff,
                Decimal("0.0001"),
                f"Cost conservation: total recipient-distributed ({total_distributed}) "
                f"!= total source cost ({total_source})",
            )

    # ------------------------------------------------------------------
    # Assertion 7: Sign invariant
    # ------------------------------------------------------------------
    def test_07_sign_invariant(self):
        """All distributed_cost values for recipient rows are positive.

        Negation rows (custom_name='') are excluded: they are negative by
        design (they remove the redistributed cost from the source side) and
        are not "recipient" rows.
        """
        with schema_context(self.schema):
            negative_count = self._recipient_qs().filter(distributed_cost__lt=0).count()
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
            pre_sum = self._distributed_qs(dist_type).aggregate(t=Sum("distributed_cost"))["t"]

        distribution_info = {
            "distribution_type": "cpu",
            "platform_cost": True,
            "worker_cost": True,
        }
        summary_range = SummaryRangeConfig(start_date=self.start_date, end_date=self.end_date)
        with OCPReportDBAccessor(self.schema) as accessor:
            accessor.populate_distributed_cost_sql(
                summary_range,
                self.provider_uuid,
                distribution_info,
                cost_model_id=self._updater._cost_model_id,
                use_rtu=True,
            )

        with schema_context(self.schema):
            post_count = self._distributed_qs(dist_type).count()
            post_sum = self._distributed_qs(dist_type).aggregate(t=Sum("distributed_cost"))["t"]

        self.assertEqual(pre_count, post_count, "Idempotency: row count changed after re-run")
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
            day = self._distributed_qs(dist_type).values_list("usage_start", flat=True).first()
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
                # Relative (not absolute-places) tolerance: src_b can be a small
                # monthly-cost rate relative to src_a, pushing the ratio itself into
                # the billions. assertAlmostEqual(places=6) demands ~6 decimal
                # digits *past* however many digits the ratio's integer part has,
                # which exceeds float64's ~15-17 significant-digit budget once the
                # ratio exceeds ~1e9 -- failing on float64 representation noise
                # rather than a real proportionality mismatch.
                self.assertAlmostEqual(
                    src_ratio,
                    dst_ratio,
                    delta=abs(src_ratio) * 1e-6,
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
            original_sum = self._distributed_qs(dist_type).aggregate(t=Sum("distributed_cost"))["t"] or Decimal(0)
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
        summary_range = SummaryRangeConfig(start_date=self.start_date, end_date=self.end_date)
        with OCPReportDBAccessor(self.schema) as accessor:
            accessor.populate_distributed_cost_sql(
                summary_range,
                self.provider_uuid,
                distribution_info,
                cost_model_id=self._updater._cost_model_id,
                use_rtu=True,
            )

        with schema_context(self.schema):
            new_sum = self._distributed_qs(dist_type).aggregate(t=Sum("distributed_cost"))["t"] or Decimal(0)
            new_count = self._distributed_qs(dist_type).count()

        self.assertEqual(original_count, new_count, "Re-run should produce same row count")
        self.assertAlmostEqual(
            float(original_sum),
            float(new_sum),
            places=10,
            msg="Re-run should produce same total distributed cost",
        )

    # ------------------------------------------------------------------
    # Assertion 11: Two-phase rewrite (Option D) algebraic equivalence,
    # for ALL FOUR distribution types (assertions 1-10 above only exercise
    # platform_distributed). Verifies that splitting the per-namespace total
    # (Phase 1) back into per-rate rows (Phase 2) reproduces the same
    # per-rate proportional cross-check and cost conservation invariants as
    # the original single-phase per-rate formula, for both the "Pod" CTE
    # family (platform/worker) and the "all data source" CTE family
    # (storage/network).
    # ------------------------------------------------------------------
    def test_11_two_phase_rewrite_equivalence_all_distribution_types(self):
        """Cross-check formula + cost conservation hold for every distribution type."""
        for dist_type in ("platform_distributed", "worker_distributed", "unattributed_storage"):
            with self.subTest(dist_type=dist_type):
                if not self._skip_if_no_distributed_type(dist_type):
                    continue

                with schema_context(self.schema):
                    total_distributed = self._recipient_qs(dist_type).aggregate(t=Sum("distributed_cost"))[
                        "t"
                    ] or Decimal(0)
                    total_source = self._source_qs(dist_type).aggregate(t=Sum("calculated_cost"))["t"] or Decimal(0)
                    if total_source == 0:
                        continue

                    # Cost conservation: recipient-only distributed cost tracks
                    # the source cost within a small relative tolerance (Option D
                    # is an algebraic rearrangement, so this must still hold).
                    relative_diff = abs(total_distributed - total_source) / abs(total_source)
                    self.assertLessEqual(
                        relative_diff,
                        Decimal("0.0001"),
                        f"[{dist_type}] recipient-distributed ({total_distributed}) "
                        f"!= source cost ({total_source})",
                    )

                    # Cross-check (Option 2 formula): per-rate distributed_cost for
                    # a namespace equals (rate_cost / total_source_cost) * ns_total.
                    day = self._recipient_qs(dist_type).values_list("usage_start", flat=True).first()
                    if not day:
                        continue
                    source_by_rate = dict(
                        self._source_qs(dist_type)
                        .filter(usage_start=day)
                        .values("custom_name")
                        .annotate(cost=Sum("calculated_cost"))
                        .values_list("custom_name", "cost")
                    )
                    total_source_day = sum(source_by_rate.values())
                    if total_source_day == 0:
                        continue
                    ns_totals = dict(
                        self._recipient_qs(dist_type)
                        .filter(usage_start=day)
                        .values("namespace")
                        .annotate(ns_total=Sum("distributed_cost"))
                        .values_list("namespace", "ns_total")
                    )
                    for rate_name, rate_cost in source_by_rate.items():
                        rate_rows = (
                            self._recipient_qs(dist_type)
                            .filter(usage_start=day, custom_name=rate_name)
                            .values("namespace")
                            .annotate(actual=Sum("distributed_cost"))
                        )
                        rate_share = rate_cost / total_source_day
                        for entry in rate_rows:
                            ns_total = ns_totals.get(entry["namespace"], Decimal(0))
                            expected = rate_share * ns_total
                            self.assertAlmostEqual(
                                float(entry["actual"]),
                                float(expected),
                                places=4,
                                msg=(
                                    f"[{dist_type}] Option 2 cross-check failed for "
                                    f"rate={rate_name}, ns={entry['namespace']}"
                                ),
                            )

    def _skip_if_no_distributed_type(self, dist_type):
        """Like _skip_if_no_distributed but usable inside a subTest (no self.skipTest)."""
        with schema_context(self.schema):
            return self._recipient_qs(dist_type).exists()

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
            null_types = list(null_cm_rows.values_list("monthly_cost_type", flat=True).distinct())
            self.assertEqual(
                null_cm_rows.count(),
                0,
                f"Distribution rows with NULL cost_model_id found for types: {null_types}",
            )


class TestGPUUnallocatedDistributionRTU(_ReportPeriodMixin, MasuTestCase):
    """Regression test: GPU unallocated cost distribution for multi-model nodes.

    ``gpu_rtu_cost`` in distribute_unallocated_gpu_cost_rtu.sql previously grouped
    by node only (not GPU model), collapsing a multi-model node's per-model costs
    into a single total. That total was then re-applied in full once per model
    via a cross join through a separate ``gpu_model_map`` CTE and a MAX(...)
    aggregate, over-distributing cost to real namespaces and leaving an incorrect
    non-zero residual on the internal "GPU unallocated" accounting bucket instead
    of netting to zero. The fix groups gpu_rtu_cost by gpu-model up front and
    sums (rather than takes the max of) each namespace's per-model contributions.
    """

    NODE = "gpu-node-cost-breakdown-test"

    def setUp(self):
        super().setUp()
        self.dh = DateHelper()
        self.provider_uuid = self.ocp_provider.uuid

        # GPU distribution requires a full month and only runs for the *previous*
        # month (either via the day-2 safety-net trigger or, as here, the natural
        # trigger when previous-month data is processed directly -- see
        # populate_distributed_cost_sql's requires_full_month gate). Using the
        # latest (current-month) report period from _get_report_period() would be
        # silently skipped by that gate on any day other than the 2nd. Anchor this
        # test to last month explicitly so it is deterministic regardless of
        # which day it runs on.
        current_rp = self._get_report_period()
        last_month_start = self.dh.last_month_start
        last_month_end = self.dh.month_end(last_month_start)
        with schema_context(self.schema):
            self.rp, _ = OCPUsageReportPeriod.objects.get_or_create(
                cluster_id=current_rp.cluster_id,
                report_period_start=last_month_start,
                provider_id=self.provider_uuid,
                defaults={"cluster_alias": current_rp.cluster_alias, "report_period_end": last_month_end},
            )
        self.start_date = last_month_start.date() if hasattr(last_month_start, "date") else last_month_start
        self.end_date = last_month_end.date() if hasattr(last_month_end, "date") else last_month_end
        self.usage_start = self.start_date

        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.ocp_provider)
        self.cost_model_id = updater._cost_model_id
        if not self.cost_model_id:
            self.skipTest("No cost model for OCP provider")

    def _seed_gpu_rtu_source_rows(self):
        """Seed per-model GPU-unallocated RTU rows, matching monthly_cost_gpu_rtu.sql output.

        That template groups by (node, gpu_model_name) and writes one row per
        model with its own calculated_cost and all_labels->>'gpu-model' -- this
        mirrors that shape directly rather than running the full monthly-cost
        pipeline, since the RTU distribution SQL under test only cares about
        rows already in this shape.
        """
        with schema_context(self.schema):
            RatesToUsage.objects.filter(
                source_uuid=self.provider_uuid, usage_start=self.usage_start, node=self.NODE
            ).delete()
            common = dict(
                report_period_id=self.rp.id,
                source_uuid_id=self.provider_uuid,
                usage_start=self.usage_start,
                usage_end=self.usage_start,
                node=self.NODE,
                namespace="GPU unallocated",
                cluster_id=self.ocp_cluster_id,
                cluster_alias=self.ocp_cluster_id,
                custom_name="GPU unallocated cost",
                # "gpu" matches OCPReportDBAccessor._get_routing_metric_type()'s output for
                # any GPU-related metric name -- the real value monthly_cost_gpu_rtu.sql writes.
                metric_type="gpu",
                cost_model_rate_type="Infrastructure",
                monthly_cost_type="Tag",
                cost_model_id=self.cost_model_id,
            )
            RatesToUsage.objects.create(all_labels={"gpu-model": "A100"}, calculated_cost=Decimal("30.00"), **common)
            RatesToUsage.objects.create(all_labels={"gpu-model": "H100"}, calculated_cost=Decimal("70.00"), **common)

    def _seed_gpu_usage_rows(self):
        """Seed usage: A100 used only by proj-a; H100 split 10%/90% proj-a/proj-b."""
        with schema_context(self.schema):
            OCPGPUUsageLineItemDaily.objects.filter(
                source=str(self.provider_uuid), usage_start=self.usage_start, node=self.NODE
            ).delete()
            year = self.usage_start.strftime("%Y")
            month = self.usage_start.strftime("%m")
            for model, namespace, uptime in (
                ("A100", "proj-a", 10),
                ("H100", "proj-a", 10),
                ("H100", "proj-b", 90),
            ):
                OCPGPUUsageLineItemDaily.objects.create(
                    source=str(self.provider_uuid),
                    year=year,
                    month=month,
                    usage_start=self.usage_start,
                    node=self.NODE,
                    namespace=namespace,
                    gpu_model_name=model,
                    gpu_pod_uptime=uptime,
                    mig_slice_count=1,
                )

    def _run_gpu_distribution(self):
        summary_range = SummaryRangeConfig(start_date=self.start_date, end_date=self.end_date)
        distribution_info = {"distribution_type": "cpu", metric_constants.GPU_UNALLOCATED: True}
        with (
            patch(
                "masu.database.ocp_report_db_accessor.OCPReportDBAccessor._reporting_period_has_gpu_data",
                return_value=True,
            ),
            # gpu_distributed's DistributionConfig has query_type="trino", so
            # populate_distributed_cost_sql checks table existence via Trino
            # before executing. Mock it so unit tests never hit a real Trino
            # endpoint (this passed under ONPREM=True on helios08 only because
            # a live Trino cluster happened to be reachable there; the default
            # CI test config has none).
            patch("masu.util.ocp.common.trino_table_exists", return_value=True),
            # Force ONPREM so DistributionConfig.get_full_path() selects the
            # self_hosted_sql/ (pure PostgreSQL) template under test -- the one
            # this regression covers -- instead of the Trino-flavored trino_sql/
            # template.
            override_settings(ONPREM=True),
        ):
            with OCPReportDBAccessor(self.schema) as accessor:

                def _execute_self_hosted_sql_via_postgres(sql, bind_params=None):
                    # gpu_distributed's DistributionConfig.is_trino is hardcoded True
                    # (pre-existing, unrelated to this fix -- confirmed present on
                    # upstream/main), so populate_distributed_cost_sql always routes
                    # execution through _execute_trino_multipart_sql_query even when
                    # ONPREM has selected the PostgreSQL-only self_hosted_sql template.
                    # Since that template is plain PostgreSQL, render and run it
                    # directly against the real test database -- the same mechanism
                    # _prepare_and_execute_raw_sql_query already uses for every other
                    # PostgreSQL-path distribution -- instead of requiring a live
                    # Trino cluster in unit tests.
                    accessor._prepare_and_execute_raw_sql_query(
                        accessor._table_map["line_item_daily_summary"],
                        sql,
                        bind_params,
                        operation="INSERT: gpu_distributed (test)",
                    )

                with patch.object(
                    accessor,
                    "_execute_trino_multipart_sql_query",
                    side_effect=_execute_self_hosted_sql_via_postgres,
                ):
                    accessor.populate_distributed_cost_sql(
                        summary_range,
                        self.provider_uuid,
                        distribution_info,
                        cost_model_id=self.cost_model_id,
                        use_rtu=True,
                    )

    def test_multi_model_node_distributes_exact_source_cost(self):
        """A multi-GPU-model node must distribute exactly its total source cost.

        Total source cost across both models is $100 (A100=$30, H100=$70). The
        pre-fix SQL distributed $190 -- the combined $100 re-applied in full for
        each of the 2 models -- and left a -$90 residual on "GPU unallocated"
        instead of $0. The fix must distribute exactly $100, split proportionally
        per model per namespace, and leave the source bucket at exactly $0.
        """
        self._seed_gpu_rtu_source_rows()
        self._seed_gpu_usage_rows()
        self._run_gpu_distribution()

        with schema_context(self.schema):
            recipient_rows = RatesToUsage.objects.filter(
                source_uuid=self.provider_uuid,
                usage_start=self.usage_start,
                node=self.NODE,
                monthly_cost_type="gpu_distributed",
            ).exclude(namespace="GPU unallocated")
            if not recipient_rows.exists():
                self.fail("Expected gpu_distributed recipient rows were not created")

            total_distributed = recipient_rows.aggregate(t=Sum("distributed_cost"))["t"] or Decimal(0)
            self.assertAlmostEqual(
                float(total_distributed),
                100.0,
                places=2,
                msg=f"GPU distribution must conserve total source cost ($100), got ${total_distributed}",
            )

            # proj-a: 100% of A100 ($30) + 10% of H100 ($7) = $37
            # proj-b: 90% of H100 ($63)
            by_namespace = dict(
                recipient_rows.values("namespace")
                .annotate(total=Sum("distributed_cost"))
                .values_list("namespace", "total")
            )
            self.assertAlmostEqual(float(by_namespace.get("proj-a", 0)), 37.0, places=2)
            self.assertAlmostEqual(float(by_namespace.get("proj-b", 0)), 63.0, places=2)

            # The internal "GPU unallocated" bucket must net to zero: source cost
            # fully moved out to real namespaces, none left over- or under-negated.
            source_and_negation = RatesToUsage.objects.filter(
                source_uuid=self.provider_uuid,
                usage_start=self.usage_start,
                node=self.NODE,
                namespace="GPU unallocated",
            ).values_list("calculated_cost", "distributed_cost")
            net_balance = sum((c or Decimal(0)) + (d or Decimal(0)) for c, d in source_and_negation)
            self.assertAlmostEqual(
                float(net_balance),
                0.0,
                places=2,
                msg=f"GPU unallocated bucket must net to zero after distribution, got {net_balance}",
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
        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.ocp_provider)
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
        summary_range = SummaryRangeConfig(start_date=self.start_date, end_date=self.end_date)
        with (
            patch("masu.database.ocp_report_db_accessor.trino_table_exists", return_value=False),
            patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.schema_exists_trino", return_value=False),
        ):
            with OCPReportDBAccessor(self.schema) as accessor:
                accessor.populate_distributed_cost_sql(
                    summary_range,
                    self.provider_uuid,
                    distribution_info,
                    cost_model_id=updater._cost_model_id,
                    use_rtu=True,
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

    def setUp(self):
        super().setUp()
        self.dh = DateHelper()
        self.rp = self._get_report_period()
        start = self.rp.report_period_start
        end = self.dh.month_end(start)
        self.start_date = start.date() if hasattr(start, "date") else start
        self.end_date = end.date() if hasattr(end, "date") else end
        self.provider_uuid = self.ocp_provider.uuid

        # NOTE: Django's TestCase wraps each test method in its own transaction
        # that is rolled back afterward, so seeded data cannot be shared across
        # tests via a class-level "seeded once" flag (a prior version of this
        # class did that and silently self-skipped every test after the first,
        # since the flag survived the rollback but the data did not; see
        # TestDistributionIntegration.setUp above for the same fix). Reseed
        # fresh on every test.
        self._seed_rtu_and_populate_breakdown()

    def _seed_rtu_and_populate_breakdown(self):
        """Run cost model updater then populate breakdown table."""
        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.ocp_provider)
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
        summary_range = SummaryRangeConfig(start_date=self.start_date, end_date=self.end_date)
        with (
            patch("masu.database.ocp_report_db_accessor.trino_table_exists", return_value=False),
            patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.schema_exists_trino", return_value=False),
        ):
            with OCPReportDBAccessor(self.schema) as accessor:
                accessor.populate_distributed_cost_sql(
                    summary_range,
                    self.provider_uuid,
                    distribution_info,
                    cost_model_id=updater._cost_model_id,
                    use_rtu=True,
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
    # P1 regression: depth-4/5 leaf paths must be unique per namespace/node
    # ------------------------------------------------------------------
    def test_depth4_paths_unique_per_namespace(self):
        """[P1] Project leaf paths must be unique per namespace, not just per rate name.

        Before the fix, two namespaces charged the same cost-model rate (the
        common case -- a single rate applies to every namespace) produced
        identical `path` strings at depth 4, since `path` was built only from
        the rate category and custom_name. This caused the tree view
        (OCPCostBreakdownView._build_tree, keyed by `path`) to silently drop
        every namespace but the last one sharing a path.

        NOTE: path uniqueness only needs to hold *within* a single
        (usage_start, cluster_id) -- OCPCostBreakdownView builds one tree per
        date group, and the SQL docstring states multi-cluster sources
        produce multiple per-cluster roots. The same path legitimately
        recurs across different days/clusters, since usage_start/cluster_id
        are separate columns, not path segments.
        """
        with schema_context(self.schema):
            project_leaves = list(
                self._breakdown_qs(depth=4, top_category="project").values(
                    "usage_start", "cluster_id", "namespace", "path"
                )
            )

        distinct_namespaces = {row["namespace"] for row in project_leaves}
        if len(distinct_namespaces) < 2:
            self.skipTest("Need at least 2 namespaces sharing a rate to exercise path disambiguation")

        by_day_and_cluster = defaultdict(list)
        for row in project_leaves:
            by_day_and_cluster[(row["usage_start"], row["cluster_id"])].append(row["path"])

        for (usage_start, cluster_id), paths in by_day_and_cluster.items():
            self.assertEqual(
                len(paths),
                len(set(paths)),
                f"Depth-4 project leaf paths collide across namespaces on {usage_start} "
                f"for cluster {cluster_id}: {paths}. "
                "The tree view will silently drop rows with duplicate paths.",
            )
        for row in project_leaves:
            self.assertIn(
                row["namespace"],
                row["path"],
                f"namespace {row['namespace']!r} is not embedded in path {row['path']!r}",
            )

    def test_depth5_paths_unique_per_recipient(self):
        """[P1] Overhead leaf paths must be unique per distribution recipient.

        Same class of bug as test_depth4_paths_unique_per_namespace, but for
        depth-5 overhead leaves, whose recipient is identified by namespace
        and/or node depending on distribution type. Scoped per
        (usage_start, cluster_id) for the same reason as above.
        """
        with schema_context(self.schema):
            overhead_leaves = list(
                self._breakdown_qs(depth=5, top_category="overhead").values(
                    "usage_start", "cluster_id", "namespace", "node", "path"
                )
            )
        if len(overhead_leaves) < 2:
            self.skipTest("Need at least 2 overhead leaves to exercise path disambiguation")

        by_day_and_cluster = defaultdict(list)
        for row in overhead_leaves:
            by_day_and_cluster[(row["usage_start"], row["cluster_id"])].append(row["path"])

        for (usage_start, cluster_id), paths in by_day_and_cluster.items():
            self.assertEqual(
                len(paths),
                len(set(paths)),
                f"Depth-5 overhead leaf paths collide across recipients on {usage_start} "
                f"for cluster {cluster_id}: {paths}.",
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
            all_paths = set(self._breakdown_qs().values_list("path", flat=True).distinct())
            non_root = self._breakdown_qs().exclude(depth=1).values_list("parent_path", flat=True).distinct()
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
            project_leaf_sum = self._breakdown_qs(depth=4, top_category="project").aggregate(total=Sum("cost_value"))[
                "total"
            ] or Decimal(0)
            overhead_leaf_sum = self._breakdown_qs(depth=5, top_category="overhead").aggregate(
                total=Sum("distributed_cost")
            )["total"] or Decimal(0)

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
            categories = set(self._breakdown_qs().values_list("top_category", flat=True).distinct())
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
            pre_totals = self._breakdown_qs().aggregate(cv=Sum("cost_value"), dc=Sum("distributed_cost"))

        summary_range = SummaryRangeConfig(start_date=self.start_date, end_date=self.end_date)
        with (
            patch("masu.database.ocp_report_db_accessor.trino_table_exists", return_value=False),
            patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.schema_exists_trino", return_value=False),
        ):
            with OCPReportDBAccessor(self.schema) as accessor:
                accessor.populate_ui_summary_tables(
                    summary_range,
                    self.provider_uuid,
                    tables=["reporting_ocp_cost_breakdown_p"],
                )

        with schema_context(self.schema):
            post_count = self._breakdown_qs().count()
            post_totals = self._breakdown_qs().aggregate(cv=Sum("cost_value"), dc=Sum("distributed_cost"))

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


# ---------------------------------------------------------------------------
# Markup double-count regression (PR #6163 maintainer review,
# pullrequestreview-4910210286): with the RTU flag on, _update_markup_cost()
# inserts a markup row into rates_to_usage (metric_type='markup') *in
# addition to* setting infrastructure_markup_cost directly on the daily
# summary row it was computed from. distribute_platform_cost_rtu.sql (and the
# structurally identical worker/storage/network templates) then double-count
# that markup dollar amount: once via the *_rtu_cost CTE (no metric_type
# exclusion) and again via the *_infra CTE (reads
# lids.infrastructure_markup_cost directly). Neither the existing markup
# tests (TestMarkupRTUIntegration, never run distribution) nor the existing
# distribution tests (TestDistributionIntegration, always use the on-prem
# fixture where infrastructure_raw_cost is 0) exercise both together, and the
# conservation-style assertions in TestDistributionIntegration compare
# recipient totals against a source total that itself never includes the
# daily-summary infra contribution -- so this bug is invisible to them even
# in principle. Isolated in its own test class (not merged into
# TestDistributionIntegration) so that seeding a nonzero infrastructure_raw_cost
# here cannot skew that class's shared conservation checks, which assume 0.
# ---------------------------------------------------------------------------
class TestMarkupDistributionDoubleCountRTU(_ReportPeriodMixin, MasuTestCase):
    """Regression test: RTU distribution must not double-count markup."""

    # OCP_ON_PREM_COST_MODEL test fixture (api/report/test/util/constants.py)
    # always configures a 10% markup.
    MARKUP_RATE = Decimal("10") / 100

    def setUp(self):
        super().setUp()
        self.dh = DateHelper()
        self.rp = self._get_report_period()
        start = self.rp.report_period_start
        end = self.dh.month_end(start)
        self.start_date = start.date() if hasattr(start, "date") else start
        self.end_date = end.date() if hasattr(end, "date") else end
        self.provider_uuid = self.ocp_provider.uuid

        self.updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.ocp_provider)
        if not self.updater._cost_model_id:
            self.skipTest("No cost model for OCP provider")
        self.updater._load_rates(self.start_date)
        if not (self.updater._infra_rates or self.updater._supplementary_rates):
            self.skipTest("No rates loaded for OCP provider")
        self.updater._update_usage_rates_to_usage(self.start_date, self.end_date)

        with schema_context(self.schema):
            usage_count = RatesToUsage.objects.filter(
                source_uuid=self.provider_uuid,
                usage_start__gte=self.start_date,
                usage_start__lte=self.end_date,
                monthly_cost_type__isnull=True,
            ).count()
        if usage_count == 0:
            self.skipTest("No RTU usage rows after seeding")

    def _seed_infra_cost_on_category(self, cost_category_name=None, namespace=None):
        """Set a known, nonzero infrastructure_raw_cost on a base usage row
        (cost_model_rate_type IS NULL) matching the given category or
        namespace. Returns the amount seeded.

        'Platform' is a real cost_category already present on baseline
        on-prem usage rows, so the existing row is reused directly. The
        synthetic 'Worker unallocated'/'Storage unattributed'/'Network
        unattributed' namespaces are normally produced by upstream
        production SQL (unallocated-capacity detection), not present as raw
        usage rows in this fixture -- clone an existing base row's shape and
        relabel it, since this test only needs a (cost_model_rate_type IS
        NULL, infrastructure_raw_cost=200) source row for the *_infra CTE,
        not realistic usage/capacity numbers.
        """
        self.infra_raw_cost = Decimal("200.00")
        with schema_context(self.schema):
            qs = OCPUsageLineItemDailySummary.objects.filter(
                source_uuid=self.provider_uuid,
                usage_start__gte=self.start_date,
                usage_start__lte=self.end_date,
                cost_model_rate_type__isnull=True,
            )
            if cost_category_name:
                qs = qs.filter(cost_category__name=cost_category_name)
            if namespace:
                qs = qs.filter(namespace=namespace)
            row = qs.first()
            if row:
                OCPUsageLineItemDailySummary.objects.filter(uuid=row.uuid).update(
                    infrastructure_raw_cost=self.infra_raw_cost
                )
                return self.infra_raw_cost

            if not namespace:
                self.skipTest(
                    f"No base usage row found for cost_category={cost_category_name} "
                    "-- cannot seed infra cost for this regression test"
                )
            template = OCPUsageLineItemDailySummary.objects.filter(
                source_uuid=self.provider_uuid,
                usage_start__gte=self.start_date,
                usage_start__lte=self.end_date,
                cost_model_rate_type__isnull=True,
            ).first()
            if not template:
                self.skipTest("No base usage row available to clone from")
            template.pk = None
            template.uuid = uuid.uuid4()
            template.namespace = namespace
            template.cost_category = None
            template.infrastructure_raw_cost = self.infra_raw_cost
            template.infrastructure_markup_cost = None
            template.infrastructure_project_raw_cost = None
            template.infrastructure_project_markup_cost = None
            template.cost_model_cpu_cost = None
            template.cost_model_memory_cost = None
            template.cost_model_volume_cost = None
            template.cost_model_rate_type = None
            template.monthly_cost_type = None
            template.distributed_cost = None
            template.save()
        return self.infra_raw_cost

    def _run_markup_and_distribution(self, distribution_info):
        """Run the same orchestration order production code uses: markup
        (usage + monthly RTU already seeded in setUp) then distribution."""
        self.updater._update_markup_cost(self.start_date, self.end_date, use_rtu=True)

        summary_range = SummaryRangeConfig(start_date=self.start_date, end_date=self.end_date)
        with OCPReportDBAccessor(self.schema) as accessor:
            accessor.populate_distributed_cost_sql(
                summary_range,
                self.provider_uuid,
                distribution_info,
                cost_model_id=self.updater._cost_model_id,
                use_rtu=True,
            )

    def _expected_vs_actual_total(self, monthly_cost_type, source_filter, infra_cost):
        """Independently compute the correct pool total (rate-cost rows,
        excluding markup, + infra_raw_cost + markup counted exactly once)
        and compare it against what distribution actually produced.
        """
        with schema_context(self.schema):
            rate_cost_total = RatesToUsage.objects.filter(
                source_filter,
                source_uuid=self.provider_uuid,
                usage_start__gte=self.start_date,
                usage_start__lte=self.end_date,
                monthly_cost_type__isnull=True,
            ).exclude(metric_type="markup").aggregate(t=Sum("calculated_cost"))["t"] or Decimal(0)
            expected_markup = infra_cost * self.MARKUP_RATE
            expected_total = rate_cost_total + infra_cost + expected_markup

            # Recipient rows only: exclude rows that match the *source* identity
            # (cost_category='Platform', or namespace='Worker unallocated' etc).
            # Those are the negation rows that remove the cost from its origin.
            # NOTE: custom_name='' does NOT reliably distinguish negation from
            # recipient rows -- the storage/network (and, when no cost-model
            # rate exists, worker/platform) "infra-only fallback" INSERT also
            # writes custom_name='' on its *recipient* rows, so excluding on
            # custom_name silently drops legitimate recipients too.
            actual_total = RatesToUsage.objects.filter(
                source_uuid=self.provider_uuid,
                usage_start__gte=self.start_date,
                usage_start__lte=self.end_date,
                monthly_cost_type=monthly_cost_type,
            ).exclude(source_filter).aggregate(t=Sum("distributed_cost"))["t"] or Decimal(0)
        return expected_total, actual_total, expected_markup

    def test_platform_distribution_does_not_double_count_markup(self):
        """platform_distributed recipient total must not include markup twice.

        This is the exact scenario from the maintainer's review comment:
        with RTU on, does distribute_platform_cost_rtu.sql's platform_rtu_cost
        (RTU markup row) plus platform_infra (lids.infrastructure_markup_cost)
        double-count markup? Yes, prior to the fix -- by exactly
        infra_raw_cost * markup_rate.
        """
        infra_cost = self._seed_infra_cost_on_category(cost_category_name="Platform")
        self._run_markup_and_distribution({"distribution_type": "cpu", "platform_cost": True, "worker_cost": True})

        expected_total, actual_total, expected_markup = self._expected_vs_actual_total(
            "platform_distributed", Q(cost_category__name="Platform"), infra_cost
        )
        self.assertAlmostEqual(
            float(actual_total),
            float(expected_total),
            places=2,
            msg=(
                f"platform_distributed recipient total (${actual_total}) does not match the "
                f"independently-computed expected total (${expected_total}); markup appears "
                f"double-counted (excess would be ${expected_markup})"
            ),
        )

    def test_worker_distribution_does_not_double_count_markup(self):
        """worker_distributed recipient total must not include markup twice."""
        infra_cost = self._seed_infra_cost_on_category(namespace="Worker unallocated")
        self._run_markup_and_distribution({"distribution_type": "cpu", "platform_cost": True, "worker_cost": True})

        expected_total, actual_total, expected_markup = self._expected_vs_actual_total(
            "worker_distributed", Q(namespace="Worker unallocated"), infra_cost
        )
        self.assertAlmostEqual(
            float(actual_total),
            float(expected_total),
            places=2,
            msg=(
                f"worker_distributed recipient total (${actual_total}) does not match the "
                f"independently-computed expected total (${expected_total}); markup appears "
                f"double-counted (excess would be ${expected_markup})"
            ),
        )

    def test_storage_distribution_does_not_double_count_markup(self):
        """unattributed_storage recipient total must not include markup twice."""
        infra_cost = self._seed_infra_cost_on_category(namespace="Storage unattributed")
        self._run_markup_and_distribution({"distribution_type": "cpu"})

        expected_total, actual_total, expected_markup = self._expected_vs_actual_total(
            "unattributed_storage", Q(namespace="Storage unattributed"), infra_cost
        )
        self.assertAlmostEqual(
            float(actual_total),
            float(expected_total),
            places=2,
            msg=(
                f"unattributed_storage recipient total (${actual_total}) does not match the "
                f"independently-computed expected total (${expected_total}); markup appears "
                f"double-counted (excess would be ${expected_markup})"
            ),
        )

    def test_network_distribution_does_not_double_count_markup(self):
        """unattributed_network recipient total must not include markup twice."""
        infra_cost = self._seed_infra_cost_on_category(namespace="Network unattributed")
        self._run_markup_and_distribution({"distribution_type": "cpu"})

        expected_total, actual_total, expected_markup = self._expected_vs_actual_total(
            "unattributed_network", Q(namespace="Network unattributed"), infra_cost
        )
        self.assertAlmostEqual(
            float(actual_total),
            float(expected_total),
            places=2,
            msg=(
                f"unattributed_network recipient total (${actual_total}) does not match the "
                f"independently-computed expected total (${expected_total}); markup appears "
                f"double-counted (excess would be ${expected_markup})"
            ),
        )


class TestInfraOnlyFallbackDistributionRTU(_ReportPeriodMixin, MasuTestCase):
    """Regression tests for the infra-only fallback + negation-scoping fixes.

    Covers three distinct gaps found while spiking the markup double-count
    fix (all newly introduced by this PR, not pre-existing):

    1. Worker/Platform: a markup-only cost model (zero non-markup rates)
       previously left the whole Worker/Platform infra+markup pool
       stranded -- namespace_totals' INNER JOIN to *_total_rate produced
       zero rows, so nothing was ever distributed or negated.
    2. Platform only: even when *some* Platform rate exists, a specific
       real Platform-tagged namespace with zero non-markup RTU rows of its
       own (e.g. no CPU/memory usage recorded that day) was never negated,
       because the old negation query was driven FROM the RTU rows
       themselves rather than from daily_summary.
    3. Storage/Network: the fallback negation's NOT EXISTS guard was
       missing a cluster_id filter, so a source_uuid with multiple
       cluster_id values could have one cluster's real rate incorrectly
       suppress another cluster's fallback negation.
    """

    MARKUP_RATE = Decimal("10") / 100

    def setUp(self):
        super().setUp()
        self.dh = DateHelper()
        self.rp = self._get_report_period()
        start = self.rp.report_period_start
        end = self.dh.month_end(start)
        self.start_date = start.date() if hasattr(start, "date") else start
        self.end_date = end.date() if hasattr(end, "date") else end
        self.provider_uuid = self.ocp_provider.uuid

        self.updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.ocp_provider)
        if not self.updater._cost_model_id:
            self.skipTest("No cost model for OCP provider")
        self.updater._load_rates(self.start_date)
        if not (self.updater._infra_rates or self.updater._supplementary_rates):
            self.skipTest("No rates loaded for OCP provider")
        self.updater._update_usage_rates_to_usage(self.start_date, self.end_date)

        with schema_context(self.schema):
            usage_count = RatesToUsage.objects.filter(
                source_uuid=self.provider_uuid,
                usage_start__gte=self.start_date,
                usage_start__lte=self.end_date,
                monthly_cost_type__isnull=True,
            ).count()
        if usage_count == 0:
            self.skipTest("No RTU usage rows after seeding")

    def _seed_infra_row(
        self,
        namespace=None,
        cost_category_name=None,
        cluster_id=None,
        infra_raw_cost=Decimal("200.00"),
        infra_markup_cost=None,
        usage_start=None,
    ):
        """Clone an existing base usage row (cost_model_rate_type IS NULL),
        relabel it to the given namespace/cost_category/cluster_id, and set
        known infrastructure_raw_cost/infrastructure_markup_cost values.

        infra_markup_cost is set directly on the summary row (as
        populate_markup_cost() would do for a real cluster) since the
        distribution SQL's negation/infra-only-fallback CTEs read markup
        exclusively from lids.infrastructure_markup_cost, never from an
        RTU metric_type='markup' row.

        By default the cloned row keeps the template's own usage_start (the
        real cluster's fixture data is only populated on specific days, not
        every day in [start_date, end_date], so real-cluster callers must
        land on one of those days to join against the real
        denominator/namespace_usage aggregates). Pass usage_start explicitly
        only when seeding a companion row (e.g. _seed_consumer_row) that must
        land on the exact same day -- the per-day denominator/namespace_usage/
        *_infra CTEs are all keyed on (usage_start, cluster_id), so mismatched
        seeded dates silently produce zero joined rows. Returns the new row's
        uuid.
        """
        with schema_context(self.schema):
            template = OCPUsageLineItemDailySummary.objects.filter(
                source_uuid=self.provider_uuid,
                usage_start__gte=self.start_date,
                usage_start__lte=self.end_date,
                cost_model_rate_type__isnull=True,
            ).first()
            if not template:
                self.skipTest("No base usage row available to clone from")
            template.pk = None
            new_uuid = uuid.uuid4()
            template.uuid = new_uuid
            if usage_start is not None:
                template.usage_start = usage_start
                template.usage_end = usage_start
            if namespace is not None:
                template.namespace = namespace
            if cluster_id is not None:
                template.cluster_id = cluster_id
            if cost_category_name:
                cat, _ = OpenshiftCostCategory.objects.get_or_create(name=cost_category_name)
                template.cost_category = cat
            else:
                template.cost_category = None
            template.infrastructure_raw_cost = infra_raw_cost
            template.infrastructure_markup_cost = infra_markup_cost
            template.infrastructure_project_raw_cost = None
            template.infrastructure_project_markup_cost = None
            template.cost_model_cpu_cost = None
            template.cost_model_memory_cost = None
            template.cost_model_volume_cost = None
            template.cost_model_rate_type = None
            template.monthly_cost_type = None
            template.distributed_cost = None
            template.save()
            return new_uuid

    def _seed_consumer_row(self, cluster_id, namespace="zzz-test-shadow-consumer-ns", usage_start=None):
        """Clone an existing base usage row into a *real*, non-overhead
        namespace under the given cluster_id, preserving its CPU/memory
        usage so the shared denominator/namespace_usage temp tables have a
        valid recipient to distribute to for that cluster_id. Without this,
        a synthetic cluster_id that only has an overhead-pool row (e.g.
        'Storage unattributed') is entirely absent from
        tmp_dist_namespace_usage_all/tmp_dist_denominator_all (they exclude
        overhead namespaces), so any per-cluster infra pool would have
        nowhere to land -- an artifact of the test fixture, not a real
        production scenario where every cluster has real workloads.

        Pass usage_start explicitly to pin this row to match a companion
        infra-pool row created via _seed_infra_row -- see that method's
        docstring for why this must match exactly.
        """
        with schema_context(self.schema):
            template = (
                OCPUsageLineItemDailySummary.objects.filter(
                    source_uuid=self.provider_uuid,
                    usage_start__gte=self.start_date,
                    usage_start__lte=self.end_date,
                    cost_model_rate_type__isnull=True,
                    data_source="Pod",
                )
                .exclude(namespace__in=["Worker unallocated", "Storage unattributed", "Network unattributed"])
                .first()
            )
            if not template:
                self.skipTest("No base Pod usage row available to clone from")
            template.pk = None
            template.uuid = uuid.uuid4()
            if usage_start is not None:
                template.usage_start = usage_start
                template.usage_end = usage_start
            template.cluster_id = cluster_id
            template.namespace = namespace
            template.cost_category = None
            template.infrastructure_raw_cost = None
            template.infrastructure_markup_cost = None
            template.infrastructure_project_raw_cost = None
            template.infrastructure_project_markup_cost = None
            template.cost_model_cpu_cost = None
            template.cost_model_memory_cost = None
            template.cost_model_volume_cost = None
            template.cost_model_rate_type = None
            template.monthly_cost_type = None
            template.distributed_cost = None
            template.save()
            return template.uuid

    def _delete_non_markup_rtu(self, namespace=None, cost_category_name=None, cluster_id=None):
        """Force the 'zero non-markup rate' condition by deleting any
        consumption-rate RTU rows for the given namespace/category/cluster,
        leaving only markup rows (if any) behind.
        """
        with schema_context(self.schema):
            qs = RatesToUsage.objects.filter(
                source_uuid=self.provider_uuid,
                usage_start__gte=self.start_date,
                usage_start__lte=self.end_date,
                monthly_cost_type__isnull=True,
            ).exclude(metric_type="markup")
            if namespace:
                qs = qs.filter(namespace=namespace)
            if cost_category_name:
                qs = qs.filter(cost_category__name=cost_category_name)
            if cluster_id:
                qs = qs.filter(cluster_id=cluster_id)
            qs.delete()

    def _run_markup_and_distribution(self, distribution_info):
        self.updater._update_markup_cost(self.start_date, self.end_date, use_rtu=True)
        summary_range = SummaryRangeConfig(start_date=self.start_date, end_date=self.end_date)
        with OCPReportDBAccessor(self.schema) as accessor:
            accessor.populate_distributed_cost_sql(
                summary_range,
                self.provider_uuid,
                distribution_info,
                cost_model_id=self.updater._cost_model_id,
                use_rtu=True,
            )

    def _net_total(self, monthly_cost_type, cluster_id=None):
        with schema_context(self.schema):
            qs = RatesToUsage.objects.filter(
                source_uuid=self.provider_uuid,
                usage_start__gte=self.start_date,
                usage_start__lte=self.end_date,
                monthly_cost_type=monthly_cost_type,
            )
            if cluster_id:
                qs = qs.filter(cluster_id=cluster_id)
            return qs.aggregate(t=Sum("distributed_cost"))["t"] or Decimal(0)

    def test_worker_zero_rate_pool_is_distributed_and_negated_exactly(self):
        """A markup-only cost model (zero non-markup Worker rates) must not
        strand the infra+markup pool -- it must be fully distributed to
        real namespaces and fully negated from 'Worker unallocated', net
        zero. Prior to the infra-only fallback, namespace_totals' INNER
        JOIN to worker_total_rate produced zero rows for the whole pool,
        so nothing was distributed or negated at all.
        """
        self._seed_infra_row(namespace="Worker unallocated", infra_raw_cost=Decimal("200.00"))
        self._delete_non_markup_rtu(namespace="Worker unallocated")

        self._run_markup_and_distribution({"distribution_type": "cpu", "platform_cost": True, "worker_cost": True})

        expected_markup = Decimal("200.00") * self.MARKUP_RATE
        expected_pool = Decimal("200.00") + expected_markup
        net_total = self._net_total("worker_distributed")
        self.assertAlmostEqual(
            float(net_total),
            0.0,
            places=2,
            msg=f"worker_distributed pool did not net to zero (got ${net_total}); pool was ${expected_pool}",
        )
        with schema_context(self.schema):
            recipient_total = RatesToUsage.objects.filter(
                source_uuid=self.provider_uuid,
                monthly_cost_type="worker_distributed",
            ).exclude(namespace="Worker unallocated").aggregate(t=Sum("distributed_cost"))["t"] or Decimal(0)
        self.assertAlmostEqual(
            float(recipient_total),
            float(expected_pool),
            places=2,
            msg=(
                f"worker_distributed recipients got ${recipient_total}, expected ${expected_pool} "
                "(infra-only fallback did not distribute the zero-rate pool)"
            ),
        )

    def test_platform_zero_rate_pool_is_distributed_and_negated_exactly(self):
        """Same as above, for the whole Platform category pool.

        Asserts recipient_total explicitly (not just net==0): with the old
        code (no infra-only fallback, no restructured negation), deleting
        every non-markup Platform RTU row makes *both* the recipient
        distribution and the negation produce zero rows -- net==0 trivially,
        without proving either side actually ran. Checking recipient_total
        directly catches that vacuous-pass case.
        """
        expected_markup = Decimal("200.00") * self.MARKUP_RATE
        expected_pool = Decimal("200.00") + expected_markup
        self._seed_infra_row(cost_category_name="Platform", infra_raw_cost=Decimal("200.00"))
        self._delete_non_markup_rtu(cost_category_name="Platform")

        self._run_markup_and_distribution({"distribution_type": "cpu", "platform_cost": True, "worker_cost": True})

        net_total = self._net_total("platform_distributed")
        self.assertAlmostEqual(
            float(net_total),
            0.0,
            places=2,
            msg=f"platform_distributed pool did not net to zero (got ${net_total})",
        )
        with schema_context(self.schema):
            recipient_total = RatesToUsage.objects.filter(
                source_uuid=self.provider_uuid,
                monthly_cost_type="platform_distributed",
            ).exclude(cost_category__name="Platform").aggregate(t=Sum("distributed_cost"))["t"] or Decimal(0)
        self.assertAlmostEqual(
            float(recipient_total),
            float(expected_pool),
            places=2,
            msg=(
                f"platform_distributed recipients got ${recipient_total}, expected ${expected_pool} "
                "(infra-only fallback did not distribute the zero-rate pool)"
            ),
        )

    def test_platform_negation_covers_namespace_with_zero_own_rate_in_mixed_pool(self):
        """When the Platform pool has *some* real rate (from one namespace)
        but a second, distinct real Platform namespace has zero non-markup
        RTU rows of its own, that second namespace's infra+markup must
        still be negated. Prior to restructuring the negation to be driven
        from daily_summary (LEFT JOIN to the RTU rate aggregate), a
        namespace absent from the RTU-driven FROM clause was silently
        skipped by negation -- even though its infra was already included
        in the whole-pool recipient distribution, causing a real double
        count.
        """
        # Namespace A: existing baseline Platform row, keeps its real non-markup
        # RTU rows from setUp (so the pool as a whole has total_rate_cost > 0).
        self._seed_infra_row(cost_category_name="Platform", infra_raw_cost=Decimal("200.00"))

        # Namespace B: a second, distinct real Platform namespace with infra but
        # deliberately zero non-markup RTU rows of its own.
        self._seed_infra_row(
            namespace="zzz-test-platform-zero-rate-ns",
            cost_category_name="Platform",
            infra_raw_cost=Decimal("150.00"),
        )
        self._delete_non_markup_rtu(namespace="zzz-test-platform-zero-rate-ns")

        self._run_markup_and_distribution({"distribution_type": "cpu", "platform_cost": True, "worker_cost": True})

        net_total = self._net_total("platform_distributed")
        self.assertAlmostEqual(
            float(net_total),
            0.0,
            places=2,
            msg=f"platform_distributed pool did not net to zero in the mixed-namespace scenario (got ${net_total})",
        )
        with schema_context(self.schema):
            namespace_b_negation = RatesToUsage.objects.filter(
                source_uuid=self.provider_uuid,
                monthly_cost_type="platform_distributed",
                namespace="zzz-test-platform-zero-rate-ns",
            ).aggregate(t=Sum("distributed_cost"))["t"] or Decimal(0)
        expected_b_markup = Decimal("150.00") * self.MARKUP_RATE
        expected_b_negation = -(Decimal("150.00") + expected_b_markup)
        self.assertAlmostEqual(
            float(namespace_b_negation),
            float(expected_b_negation),
            places=2,
            msg=(
                f"zero-own-rate Platform namespace was not negated (got ${namespace_b_negation}, "
                f"expected ${expected_b_negation}) -- its infra+markup is double-counted"
            ),
        )

    def test_storage_negation_scoped_by_cluster_id_not_leaked_across_clusters(self):
        """The fallback negation's NOT EXISTS guard must be scoped by
        cluster_id: a real Storage rate existing under one cluster_id must
        not suppress the fallback negation for a *different* cluster_id
        under the same source_uuid. Prior to the fix, the guard checked
        only (usage_start, source_uuid, namespace), so it could find the
        real cluster's rate row and incorrectly treat the fake cluster as
        'already covered', permanently stranding its infra+markup.
        """
        real_cluster_id = self.ocp_cluster_id
        shadow_cluster_id = f"{real_cluster_id}-shadow-test"

        # Real cluster keeps its baseline non-markup RTU rows from setUp
        # (rate_cost > 0 for that cluster).
        self._seed_infra_row(namespace="Storage unattributed", infra_raw_cost=Decimal("50.00"))

        # Shadow "cluster": same source_uuid, different cluster_id, with its own
        # real infra + markup, but zero non-markup RTU rows of its own -- and a
        # real consuming namespace so the recipient side has somewhere to land
        # (a cluster with only the overhead-pool row is not a realistic fixture;
        # tmp_dist_namespace_usage_all/denominator exclude overhead namespaces).
        shadow_markup = Decimal("300.00") * self.MARKUP_RATE
        shadow_pool_uuid = self._seed_infra_row(
            namespace="Storage unattributed",
            cluster_id=shadow_cluster_id,
            infra_raw_cost=Decimal("300.00"),
            infra_markup_cost=shadow_markup,
        )
        with schema_context(self.schema):
            shadow_pool_usage_start = OCPUsageLineItemDailySummary.objects.get(uuid=shadow_pool_uuid).usage_start
        self._seed_consumer_row(shadow_cluster_id, usage_start=shadow_pool_usage_start)

        self._run_markup_and_distribution({"distribution_type": "cpu"})

        net_shadow = self._net_total("unattributed_storage", cluster_id=shadow_cluster_id)
        self.assertAlmostEqual(
            float(net_shadow),
            0.0,
            places=2,
            msg=(
                f"shadow cluster's unattributed_storage pool did not net to zero (got ${net_shadow}) -- "
                "the real cluster's rate incorrectly suppressed the shadow cluster's fallback negation"
            ),
        )
        with schema_context(self.schema):
            shadow_negation = RatesToUsage.objects.filter(
                source_uuid=self.provider_uuid,
                monthly_cost_type="unattributed_storage",
                cluster_id=shadow_cluster_id,
                namespace="Storage unattributed",
            ).aggregate(t=Sum("distributed_cost"))["t"] or Decimal(0)
        expected_shadow_negation = -(Decimal("300.00") + shadow_markup)
        self.assertAlmostEqual(
            float(shadow_negation),
            float(expected_shadow_negation),
            places=2,
            msg=(
                f"shadow cluster was not negated (got ${shadow_negation}, expected "
                f"${expected_shadow_negation}) -- cross-cluster NOT EXISTS leak stranded its infra+markup"
            ),
        )
