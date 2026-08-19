#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Regression tests: concurrent, overlapping-range distribution calls must not double-count.

populate_distributed_cost_sql, aggregate_rates_to_daily_summary, and
populate_markup_rates_to_usage each run a DELETE followed by an INSERT as
separate, independently-autocommitted statements (see
ReportDBAccessorBase._execute_raw_sql_query -- each call is its own unit of
work, no shared transaction). Before the per-provider advisory lock
(OCPReportDBAccessor._distribution_provider_lock) was added, two
overlapping-but-different-range invocations of populate_distributed_cost_sql
for the SAME provider (e.g. a cost-model update racing a resummarize --
WorkerCache's cache key includes start_date/end_date, so it does not dedupe
these; see PR #6162) could interleave DELETE/INSERT and silently double
distributed_cost, with no deadlock or exception to surface it. This was the
root cause of a real IQE failure (test_api_ocp_on_gcp_source_raw_calc) where
infrastructure cost was reported at ~2x the expected value after a cost-model
update triggered a resummarize.

The fix deliberately uses session-scoped pg_advisory_lock/pg_advisory_unlock,
NOT pg_advisory_xact_lock wrapped in transaction.atomic(): the guarded calls
retry on deadlock (see RawSqlRetryIdempotencyGuardTest), and that retry is
only safe when each call remains independently autocommitted. Wrapping it in
transaction.atomic() would abort the whole transaction on a deadlock,
breaking the per-statement retry instead of fixing this race.

Must use TransactionTestCase (not TestCase/MasuTestCase): TestCase wraps the
whole test body in one outer transaction bound to the main thread's
connection, so worker threads (which get their own DB connections) would
never see uncommitted setUp() data, producing a false "nothing happened"
result. TransactionTestCase autocommits, making writes immediately visible
across connections/threads, matching how two real Celery workers behave.

Django's automatic TransactionTestCase teardown (a full-database
sql_flush/TRUNCATE) fails in this schema because reporting_tenant_api_provider
has an FK to api_provider, and the standing fixture data seeded once by
KokuTestRunner is not supposed to be torn down per-test anyway. Test isolation
is instead handled explicitly in setUp (defensive delete of any leftover
seeded/distributed rows for this provider/window before reseeding), so the
automatic fixture teardown is overridden to a no-op.
"""
import threading
import uuid as uuid_mod
from decimal import Decimal
from unittest import mock

from django.db.models import Sum
from django.test import TransactionTestCase
from django_tenants.utils import schema_context

from api.iam.serializers import create_schema_name
from api.models import Tenant
from api.provider.models import Provider
from api.utils import DateHelper
from koku.koku_test_runner import KokuTestRunner
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.processor.ocp.ocp_cost_model_cost_updater import OCPCostModelCostUpdater
from masu.util.common import SummaryRangeConfig
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting.provider.ocp.models import RatesToUsage


class TestConcurrentOverlappingRangeDistributionRace(TransactionTestCase):
    """Two concurrent, overlapping-range calls must not double-count distributed cost."""

    # Standing baseline fixture data (seeded once by KokuTestRunner at DB
    # setup, already committed) -- not created/rolled back per test.
    reset_sequences = False

    def _fixture_teardown(self):
        """Skip Django's automatic full-database flush.

        See module docstring: flush fails on this schema's FK constraints,
        and the standing fixture data must not be torn down. setUp() handles
        isolation explicitly instead.
        """

    def setUp(self):
        super().setUp()
        self.schema = KokuTestRunner.schema
        Tenant.objects.get_or_create(schema_name=create_schema_name(KokuTestRunner.org_id))
        self.ocp_provider = Provider.objects.get(
            type=Provider.PROVIDER_OCP, authentication__credentials__cluster_id="OCP-on-Prem"
        )
        self.provider_uuid = self.ocp_provider.uuid
        self.dh = DateHelper()

        with schema_context(self.schema):
            report_period = (
                OCPUsageReportPeriod.objects.filter(provider_id=self.provider_uuid)
                .order_by("-report_period_start")
                .first()
            )
        if not report_period:
            self.skipTest("No report period for OCP provider")
        start = report_period.report_period_start
        end = self.dh.month_end(start)
        self.start_date = start.date() if hasattr(start, "date") else start
        self.end_date = end.date() if hasattr(end, "date") else end

        self._updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.ocp_provider)
        if not self._updater._cost_model_id:
            self.skipTest("No cost model for OCP provider")

        with schema_context(self.schema):
            # Defensive cleanup: remove any leftover seeded/distributed rows
            # for this provider/window from a prior run so each test starts
            # from a known, single pool amount.
            OCPUsageLineItemDailySummary.objects.filter(
                source_uuid=self.provider_uuid,
                usage_start__gte=self.start_date,
                usage_start__lte=self.end_date,
                namespace="Worker unallocated",
            ).delete()
            OCPUsageLineItemDailySummary.objects.filter(
                source_uuid=self.provider_uuid,
                usage_start__gte=self.start_date,
                usage_start__lte=self.end_date,
                cost_model_rate_type="worker_distributed",
            ).delete()
            RatesToUsage.objects.filter(
                source_uuid=self.provider_uuid,
                usage_start__gte=self.start_date,
                usage_start__lte=self.end_date,
                monthly_cost_type="worker_distributed",
            ).delete()

            # Seed a known infra_raw_cost on a synthetic "Worker unallocated"
            # pool row (normally produced by upstream unallocated-capacity
            # SQL, not present in the base fixture) by cloning an existing
            # base usage row's shape and relabeling it.
            template = OCPUsageLineItemDailySummary.objects.filter(
                source_uuid=self.provider_uuid,
                usage_start__gte=self.start_date,
                usage_start__lte=self.end_date,
                cost_model_rate_type__isnull=True,
            ).first()
            if not template:
                self.skipTest("No base usage row available to clone from")
            self.pool_amount = Decimal("300.00")
            template.pk = None
            template.uuid = uuid_mod.uuid4()
            template.namespace = "Worker unallocated"
            template.cost_category = None
            template.infrastructure_raw_cost = self.pool_amount
            template.infrastructure_markup_cost = 0
            template.infrastructure_project_raw_cost = None
            template.infrastructure_project_markup_cost = None
            template.cost_model_cpu_cost = None
            template.cost_model_memory_cost = None
            template.cost_model_volume_cost = None
            template.cost_model_rate_type = None
            template.monthly_cost_type = None
            template.distributed_cost = None
            template.save()

        self.distribution_info = {
            "distribution_type": "cpu",
            "worker_cost": True,
            "platform_cost": False,
            "storage_unattributed": False,
            "network_unattributed": False,
        }

    def _worker_distributed_total(self):
        with schema_context(self.schema):
            agg = (
                OCPUsageLineItemDailySummary.objects.filter(
                    source_uuid=self.provider_uuid,
                    usage_start__gte=self.start_date,
                    usage_start__lte=self.end_date,
                    cost_model_rate_type="worker_distributed",
                )
                .exclude(namespace="Worker unallocated")
                .aggregate(total=Sum("distributed_cost"))
            )
            return agg["total"] or Decimal("0")

    def _worker_rtu_recipient_total(self):
        with schema_context(self.schema):
            agg = (
                RatesToUsage.objects.filter(
                    source_uuid=self.provider_uuid,
                    usage_start__gte=self.start_date,
                    usage_start__lte=self.end_date,
                    monthly_cost_type="worker_distributed",
                    distributed_cost__isnull=False,
                )
                .exclude(namespace="Worker unallocated")
                .aggregate(total=Sum("distributed_cost"))
            )
            return agg["total"] or Decimal("0")

    def _run_two_concurrent_calls(self, use_rtu):
        """Run two threads that both call populate_distributed_cost_sql for the
        same provider/date-range, forced to interleave their DELETE and INSERT
        phases for the Worker category specifically.
        """
        barrier = threading.Barrier(2, timeout=30)
        orig = OCPReportDBAccessor._prepare_and_execute_raw_sql_query

        def synced(self_accessor, table_name, sql, params, operation=None, **kwargs):
            result = orig(self_accessor, table_name, sql, params, operation=operation, **kwargs)
            # Only synchronize on the Worker category's DELETE step so the two
            # threads' loops over (Platform, Worker, Storage, Network, GPU)
            # stay index-aligned and interleaving is forced exactly at the
            # point of interest.
            if operation == "DELETE" and params.get("cost_model_rate_type") == "worker_distributed":
                try:
                    barrier.wait()
                except threading.BrokenBarrierError:
                    pass
            return result

        results = {}

        def run(key):
            try:
                summary_range = SummaryRangeConfig(start_date=self.start_date, end_date=self.end_date)
                with OCPReportDBAccessor(self.schema) as accessor:
                    accessor.populate_distributed_cost_sql(
                        summary_range,
                        self.provider_uuid,
                        self.distribution_info,
                        cost_model_id=self._updater._cost_model_id,
                        use_rtu=use_rtu,
                    )
                results[key] = "ok"
            except Exception as exc:  # noqa: BLE001
                import traceback

                results[key] = f"error: {exc}\n{traceback.format_exc()}"

        with mock.patch.object(OCPReportDBAccessor, "_prepare_and_execute_raw_sql_query", synced):
            t1 = threading.Thread(target=run, args=("A",))
            t2 = threading.Thread(target=run, args=("B",))
            t1.start()
            t2.start()
            t1.join(timeout=60)
            t2.join(timeout=60)

        for key, outcome in results.items():
            self.assertEqual(outcome, "ok", f"thread {key} raised: {outcome}")

    def test_concurrent_overlapping_ranges_do_not_double_count_legacy(self):
        """Two overlapping, concurrently-interleaved calls to
        populate_distributed_cost_sql(use_rtu=False) must distribute the pool
        exactly once, not twice, thanks to the per-provider advisory lock.
        """
        self._run_two_concurrent_calls(use_rtu=False)
        total = self._worker_distributed_total()
        self.assertAlmostEqual(
            total,
            self.pool_amount,
            places=2,
            msg=(
                f"Concurrent overlapping-range calls produced recipient total {total}, "
                f"expected {self.pool_amount} -- indicates the per-provider advisory "
                "lock regressed and double-distribution is possible again."
            ),
        )

    def test_concurrent_overlapping_ranges_do_not_double_count_rtu(self):
        """Same race, but against the RTU path (use_rtu=True)."""
        self._run_two_concurrent_calls(use_rtu=True)
        total = self._worker_rtu_recipient_total()
        self.assertAlmostEqual(
            total,
            self.pool_amount,
            places=2,
            msg=(
                f"[RTU] Concurrent overlapping-range calls produced recipient total {total}, "
                f"expected {self.pool_amount} -- indicates the per-provider advisory "
                "lock regressed and double-distribution is possible again on the RTU path."
            ),
        )
