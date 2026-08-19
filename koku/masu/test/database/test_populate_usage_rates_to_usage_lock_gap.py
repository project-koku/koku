#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Spike/regression: does populate_usage_rates_to_usage serialize against other RTU writers?

COST-7249 deadlock preflight, COST-8112. populate_usage_rates_to_usage -- the
first write into rates_to_usage in the whole RTU pipeline -- performs a
DELETE-then-INSERT for a given provider/date-range via raw SQL, structurally
identical to populate_distributed_cost_sql / aggregate_rates_to_daily_summary /
populate_markup_rates_to_usage / _populate_cost_breakdown_ui_summary_table,
all of which already run under OCPReportDBAccessor._distribution_provider_lock.
This method did not, leaving it exposed to the same class of race as Finding B
(see test_ocp_provider_delete_rtu_race.py): a concurrent report-period
delete's deferred FK cascade to rates_to_usage can interleave with this
method's own unprotected write for the same provider.

This test verifies the fix directly and deterministically via timing, rather
than via a data-integrity crash: a concurrent thread acquires
_distribution_provider_lock(provider_uuid) and holds it for a fixed,
measurable duration. Without the fix, populate_usage_rates_to_usage never
contends for that lock and returns almost immediately regardless of the
holder. With the fix, it must block until the holder releases, so its total
elapsed time is bounded below by the holder's hold duration -- a real,
reproducible signal rather than a timing-window-dependent crash.

Uses real (unmocked) SQL execution against the fixture cost model / price
list / rate already seeded for the OCP test provider by
ModelBakeryDataLoader, plus one dedicated OCPUsageLineItemDailySummary row so
the INSERT branch has something to write.

Fix: populate_usage_rates_to_usage now acquires the same
_distribution_provider_lock(provider_uuid) as its RTU-pipeline siblings.
"""
import threading
import time
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import django.test
from django.conf import settings
from django.db import connection
from django_tenants.utils import schema_context

from api.iam.models import Customer
from api.provider.models import Provider
from cost_models.models import CostModelMap
from koku.test_provider_delete_cascade import create_test_provider
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting.provider.ocp.models import RatesToUsage


class PopulateUsageRatesToUsageLockGapTest(django.test.TransactionTestCase):
    """COST-8112 spike: populate_usage_rates_to_usage vs. a concurrent RTU lock holder."""

    HOLD_SECONDS = 1.5

    def _fixture_teardown(self):
        """Skip TRUNCATE flush -- django-tenants FK graph breaks TransactionTestCase flush."""

    def setUp(self):
        from koku.koku_test_runner import KokuTestRunner

        self.schema = KokuTestRunner.schema
        with schema_context(self.schema):
            self.customer = Customer.objects.filter(schema_name=self.schema).first()
        if not self.customer:
            self.skipTest("No test customer fixture available")

        self.provider = Provider(
            uuid=uuid.uuid4(),
            name=f"spike-8112-{uuid.uuid4().hex[:8]}",
            type=Provider.PROVIDER_OCP,
            setup_complete=False,
            active=True,
            customer=self.customer,
        )
        self.provider.save()
        create_test_provider(self.schema, self.provider)

        self.period_start = datetime(2026, 6, 1, tzinfo=settings.UTC)
        self.period_end = datetime(2026, 7, 1, tzinfo=settings.UTC)
        with schema_context(self.schema):
            self.report_period = OCPUsageReportPeriod.objects.create(
                cluster_id=f"spike-8112-cluster-{uuid.uuid4().hex[:8]}",
                report_period_start=self.period_start,
                report_period_end=self.period_end,
                provider_id=self.provider.uuid,
            )
            # Reuse the already-seeded cost model / price list / rate (any OCP one works --
            # populate_usage_rates_to_usage's rate lookup is keyed by cost_model_id only, not
            # by provider) so this test doesn't need to hand-build a full price list + rate
            # fixture just to get the INSERT branch to have something to write.
            cmm = CostModelMap.objects.exclude(cost_model__isnull=True).first()
            if not cmm:
                self.skipTest("No seeded cost model fixture available")
            self.cost_model_id = cmm.cost_model_id

            OCPUsageLineItemDailySummary.objects.create(
                uuid=uuid.uuid4(),
                report_period=self.report_period,
                cluster_id=self.report_period.cluster_id,
                source_uuid=self.provider.uuid,
                namespace="spike-8112-ns",
                node="spike-8112-node",
                data_source="Pod",
                usage_start=self.period_start.date(),
                usage_end=self.period_start.date(),
                pod_effective_usage_cpu_core_hours=Decimal("4.0"),
                pod_usage_cpu_core_hours=Decimal("4.0"),
                node_capacity_cpu_cores=Decimal("8"),
                node_capacity_cpu_core_hours=Decimal("192"),
                cluster_capacity_cpu_core_hours=Decimal("768"),
            )

    def tearDown(self):
        with schema_context(self.schema):
            RatesToUsage.objects.filter(report_period_id=self.report_period.id).delete()
            OCPUsageLineItemDailySummary.objects.filter(report_period_id=self.report_period.id).delete()
            OCPUsageReportPeriod.objects.filter(pk=self.report_period.pk).delete()
        with patch("masu.celery.tasks.delete_archived_data.delay", lambda *a, **k: None):
            try:
                self.provider.delete()
            except Provider.DoesNotExist:
                pass

    def _hold_lock_then_release(self, results, barrier):
        try:
            with schema_context(self.schema):
                with OCPReportDBAccessor(self.schema) as accessor:
                    with accessor._distribution_provider_lock(self.provider.uuid):
                        barrier.wait()
                        time.sleep(self.HOLD_SECONDS)
            results["holder"] = "ok"
        except Exception as exc:  # noqa: BLE001 -- spike wants to see everything
            results["holder"] = f"{type(exc).__name__}: {exc}"
        finally:
            connection.close()

    def _run_populate(self, results, barrier):
        try:
            barrier.wait()
            t0 = time.monotonic()
            with schema_context(self.schema):
                with OCPReportDBAccessor(self.schema) as accessor:
                    accessor.populate_usage_rates_to_usage(
                        self.period_start.date(),
                        self.period_start.date(),
                        self.provider.uuid,
                        self.report_period.id,
                        self.cost_model_id,
                    )
            results["populate_elapsed"] = time.monotonic() - t0
            results["populate"] = "ok"
        except Exception as exc:  # noqa: BLE001
            results["populate"] = f"{type(exc).__name__}: {exc}"
        finally:
            connection.close()

    def test_populate_blocks_on_concurrent_distribution_lock_holder(self):
        """Fix verification: populate_usage_rates_to_usage now contends for the same
        _distribution_provider_lock as its RTU-pipeline siblings.

        Deterministic by construction: a concurrent thread holds the lock for a fixed
        HOLD_SECONDS after signaling readiness via a barrier. With the fix,
        populate_usage_rates_to_usage cannot begin its DELETE-then-INSERT until that lock is
        released, so its total elapsed time must be at least close to HOLD_SECONDS. Before
        the fix (verified manually by reverting the lock wrap in ocp_report_db_accessor.py),
        this same test fails: populate_usage_rates_to_usage never contends for the lock and
        returns in a small fraction of HOLD_SECONDS regardless of the concurrent holder,
        proving it was not serialized against other RTU writers for the same provider.
        """
        barrier = threading.Barrier(2, timeout=15)
        results = {"holder": None, "populate": None, "populate_elapsed": None}

        t_holder = threading.Thread(target=self._hold_lock_then_release, args=(results, barrier))
        t_populate = threading.Thread(target=self._run_populate, args=(results, barrier))
        t_holder.start()
        t_populate.start()
        t_holder.join(timeout=20)
        t_populate.join(timeout=20)

        self.assertEqual(results["holder"], "ok", f"lock-holder thread failed: {results['holder']}")
        self.assertEqual(results["populate"], "ok", f"populate_usage_rates_to_usage failed: {results['populate']}")
        self.assertIsNotNone(results["populate_elapsed"], "populate_usage_rates_to_usage never completed")
        self.assertGreaterEqual(
            results["populate_elapsed"],
            self.HOLD_SECONDS * 0.8,
            f"populate_usage_rates_to_usage returned in {results['populate_elapsed']:.3f}s, well under "
            f"the {self.HOLD_SECONDS}s the concurrent writer held _distribution_provider_lock -- it did "
            "not wait for the lock, meaning it is not serialized against other RTU writers for the same "
            "provider (COST-8112 regression).",
        )

        with schema_context(self.schema):
            inserted = RatesToUsage.objects.filter(report_period_id=self.report_period.id).count()
        self.assertGreater(
            inserted, 0, "populate_usage_rates_to_usage should have inserted at least one rates_to_usage row"
        )
