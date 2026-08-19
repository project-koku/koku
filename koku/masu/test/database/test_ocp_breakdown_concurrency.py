#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Spike: does concurrent _populate_cost_breakdown_ui_summary_table corrupt or deadlock?

COST-7249 deadlock preflight, Finding A. This method populates
reporting_ocp_cost_breakdown_p from rates_to_usage via _execute_processing_script
-- a raw-SQL helper with NO retry-on-deadlock and NOT bracketed by
_distribution_provider_lock, unlike its siblings (populate_distributed_cost_sql,
aggregate_rates_to_daily_summary, populate_markup_rates_to_usage) that operate on
the same provider/date-range and face the identical concurrent-invocation risk
per _distribution_provider_lock's own docstring.

This test empirically reproduces two overlapping runs for the SAME provider and
date range (e.g. a cost-model update racing a resummarize -- the exact scenario
_distribution_provider_lock exists to prevent for the other methods) and records
whichever failure mode actually occurs: a raised OperationalError/deadlock, or
silent data corruption (duplicated/missing breakdown rows) with no exception at
all.
"""
import threading
import uuid
from decimal import Decimal

import django.test
from django.db import connection
from django.db.utils import OperationalError
from django_tenants.utils import schema_context
from django_tenants.utils import tenant_context

from api.models import Tenant
from api.provider.models import Provider
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from reporting.provider.ocp.models import OCPCostUIBreakDownP
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting.provider.ocp.models import RatesToUsage


class PopulateCostBreakdownConcurrencyTest(django.test.TransactionTestCase):
    """Finding A spike: concurrent breakdown population for the same provider/range."""

    def _fixture_teardown(self):
        """Skip TRUNCATE flush -- django-tenants FK graph breaks TransactionTestCase flush.

        Matches PopulateMarkupCostConcurrencyTest (COST-7995) -- fixture data
        seeded once by KokuTestRunner.setup_databases() must survive.
        """

    def setUp(self):
        from koku.koku_test_runner import KokuTestRunner

        self.schema = KokuTestRunner.schema
        self.tenant = Tenant.objects.get(schema_name=self.schema)

        with tenant_context(self.tenant):
            provider = Provider.objects.filter(type=Provider.PROVIDER_OCP).first()
        if not provider:
            self.skipTest("No OCP provider fixture available")
        self.provider_uuid = provider.uuid

        with schema_context(self.schema):
            rp = (
                OCPUsageReportPeriod.objects.filter(provider_id=self.provider_uuid)
                .order_by("-report_period_start")
                .first()
            )
        if not rp:
            self.skipTest("No report period for OCP provider")
        self.report_period_id = rp.id
        self.cluster_id = rp.cluster_id
        self.start_date = rp.report_period_start.date()
        self.end_date = self.start_date

        self.run_tag = f"breakdown-race-{uuid.uuid4().hex[:8]}"
        self._seed_rates_to_usage()

    def tearDown(self):
        with schema_context(self.schema):
            RatesToUsage.objects.filter(cluster_id=self.run_tag).delete()
            OCPCostUIBreakDownP.objects.filter(cluster_id=self.run_tag).delete()

    def _seed_rates_to_usage(self):
        """Seed depth-4 (usage) and depth-5 (distributed) qualifying RTU rows.

        Uses a synthetic, unique cluster_id (self.run_tag) so the breakdown
        tree built by this test is fully isolated from any other cluster's
        rows for this provider/date, and from the other thread's writes only
        insofar as they target the SAME rows on purpose (that overlap is the
        point of the race).
        """
        with schema_context(self.schema):
            for i in range(10):
                RatesToUsage.objects.create(
                    source_uuid_id=self.provider_uuid,
                    report_period_id=self.report_period_id,
                    usage_start=self.start_date,
                    usage_end=self.end_date,
                    cluster_id=self.run_tag,
                    namespace=f"ns-{i}",
                    node=f"node-{i}",
                    custom_name="cpu-usage-rate",
                    metric_type="cpu_usage",
                    cost_model_rate_type="Supplementary",
                    calculated_cost=Decimal("10.00"),
                )
                RatesToUsage.objects.create(
                    source_uuid_id=self.provider_uuid,
                    report_period_id=self.report_period_id,
                    usage_start=self.start_date,
                    usage_end=self.end_date,
                    cluster_id=self.run_tag,
                    namespace=f"ns-{i}",
                    node=f"node-{i}",
                    custom_name="cpu-usage-rate",
                    metric_type="cpu_usage",
                    cost_model_rate_type="Infrastructure",
                    monthly_cost_type="Node_Core_Month",
                    distributed_cost=Decimal("5.00"),
                )

    def _expected_totals_single_run(self):
        """Ground truth: run once, single-threaded, and record the resulting totals."""
        with schema_context(self.schema):
            OCPCostUIBreakDownP.objects.filter(cluster_id=self.run_tag).delete()
        with OCPReportDBAccessor(self.schema) as accessor:
            sql_params = {
                "start_date": self.start_date,
                "end_date": self.end_date,
                "schema": self.schema,
                "source_uuid": self.provider_uuid,
            }
            accessor._populate_cost_breakdown_ui_summary_table(sql_params)
        with schema_context(self.schema):
            rows = OCPCostUIBreakDownP.objects.filter(cluster_id=self.run_tag)
            totals = {
                "row_count": rows.count(),
                "depth4_count": rows.filter(depth=4).count(),
                "depth5_count": rows.filter(depth=5).count(),
            }
            OCPCostUIBreakDownP.objects.filter(cluster_id=self.run_tag).delete()
        return totals

    def test_concurrent_breakdown_population_same_provider(self):
        """Two concurrent runs for the SAME provider/date-range: deadlock or corruption?

        Mirrors _distribution_provider_lock's own documented race (a cost-model
        update racing a resummarize for the same provider) but exercises the one
        step in that call chain -- cost-breakdown population -- that is not
        bracketed by that lock.
        """
        expected = self._expected_totals_single_run()

        barrier = threading.Barrier(2, timeout=10)
        results = [None, None]

        def run_population(index):
            try:
                barrier.wait()
                with OCPReportDBAccessor(self.schema) as accessor:
                    sql_params = {
                        "start_date": self.start_date,
                        "end_date": self.end_date,
                        "schema": self.schema,
                        "source_uuid": self.provider_uuid,
                    }
                    accessor._populate_cost_breakdown_ui_summary_table(sql_params)
                results[index] = "ok"
            except OperationalError as exc:
                results[index] = f"DEADLOCK/OPERATIONAL_ERROR: {type(exc).__name__}: {exc}"
            except Exception as exc:  # noqa: BLE001 -- spike wants to see everything
                results[index] = f"{type(exc).__name__}: {exc}"
            finally:
                connection.close()

        t1 = threading.Thread(target=run_population, args=(0,))
        t2 = threading.Thread(target=run_population, args=(1,))
        t1.start()
        t2.start()
        t1.join(timeout=20)
        t2.join(timeout=20)

        with schema_context(self.schema):
            rows = OCPCostUIBreakDownP.objects.filter(cluster_id=self.run_tag)
            actual = {
                "row_count": rows.count(),
                "depth4_count": rows.filter(depth=4).count(),
                "depth5_count": rows.filter(depth=5).count(),
            }

        deadlocked = any(r and r.startswith("DEADLOCK") for r in results)
        corrupted = not deadlocked and actual != expected

        if deadlocked:
            self.fail(
                f"[SPIKE CONFIRMED] Concurrent breakdown population deadlocked: {results}. "
                "This reproduces Finding A as a genuine Postgres deadlock."
            )
        if corrupted:
            self.fail(
                f"[SPIKE CONFIRMED] Concurrent breakdown population silently corrupted data "
                f"with no exception raised. expected={expected} actual={actual}. "
                "This reproduces Finding A as the same silent-corruption failure mode "
                "_distribution_provider_lock exists to prevent in the sibling methods."
            )
        self.assertEqual(results[0], "ok", f"Thread 1 failed: {results[0]}")
        self.assertEqual(results[1], "ok", f"Thread 2 failed: {results[1]}")
        self.assertEqual(actual, expected, "Concurrent run produced different totals than a single run")
