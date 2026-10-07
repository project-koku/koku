#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Spike: does deleting a stale cost-model Rate race a concurrent rates_to_usage write?

COST-7249 deadlock preflight, expanded audit, Finding E. sync_rate_table()
(cost_models/rate_sync.py) -- invoked on every cost-model/price-list rate PUT
via CostModelManager.create/update, PriceListManager.create/update, and
PriceListViewSet._ensure_rate_sync -- deletes stale Rate rows with a plain
Rate.objects.filter(...).delete(). RatesToUsage.rate is a normal Django FK
with on_delete=models.CASCADE, so this triggers Django's collector-driven,
EAGER cascade: an immediate `DELETE FROM rates_to_usage WHERE rate_id IN
(...)` inside that same call -- not the DEFERRABLE INITIALLY DEFERRED
DB-level FK that Finding B / COST-8112 deal with.

Unlike Finding B (one side takes a lock, the other crashes with an FK
violation), here neither side took any lock at all pre-fix. The blast radius
is every provider on every cost model attached to the price list being
edited, not one provider's report period, since rates_to_usage.rate_id is
not scoped to a single provider.

Fix: sync_rate_table() now resolves every provider_uuid reachable from the
price list (via PriceListCostModelMap -> CostModelMap) and acquires the same
session-scoped pg_advisory_lock(hashtext(provider_uuid)) that every RTU write
step (populate_distributed_cost_sql, aggregate_rates_to_daily_summary,
populate_markup_rates_to_usage, etc.) already takes for that provider,
before touching the Rate table at all.

Two tests below:
- test_protected_rtu_insert_serializes_cleanly_against_rate_delete: proves a
  lock-coordinated writer (one that takes _distribution_provider_lock, like
  every real RTU write step does) now serializes cleanly against a
  concurrent sync_rate_table call (red without the fix using a deterministic
  held-lock delay, green with it).
- test_unprotected_rtu_insert_crashes_during_rate_delete: characterization
  test documenting that a write which bypasses the RTU accessor's lock
  helper entirely (advisory locks are cooperative, not enforced by Postgres)
  remains exposed regardless of this fix. This is an inherent limitation of
  advisory locks, not a specific missed call site.
"""
import threading
import time
import uuid
from datetime import date
from datetime import datetime
from unittest.mock import patch

import django.test
from django.conf import settings
from django.db import connection
from django.db import IntegrityError
from django.db import OperationalError
from django.db.models.signals import pre_delete
from django_tenants.utils import schema_context

from api.iam.models import Customer
from api.provider.models import Provider
from cost_models.models import CostModel
from cost_models.models import CostModelMap
from cost_models.models import PriceList
from cost_models.models import PriceListCostModelMap
from cost_models.models import Rate
from cost_models.rate_sync import sync_rate_table
from koku.test_provider_delete_cascade import create_test_provider
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting.provider.ocp.models import RatesToUsage


@patch("masu.celery.tasks.delete_archived_data.delay", lambda *a, **k: None)
class CostModelRateDeleteRTURaceTest(django.test.TransactionTestCase):
    """Finding E: Rate deletion (sync_rate_table) vs. a concurrent RTU writer on a different provider."""

    def _fixture_teardown(self):
        """Skip TRUNCATE flush -- django-tenants FK graph breaks TransactionTestCase flush."""

    def setUp(self):
        from koku.koku_test_runner import KokuTestRunner

        self.schema = KokuTestRunner.schema
        with schema_context(self.schema):
            self.customer = Customer.objects.filter(schema_name=self.schema).first()
        if not self.customer:
            self.skipTest("No test customer fixture available")

        with schema_context(self.schema):
            self.price_list = PriceList.objects.create(
                name=f"spike-finding-e-pl-{uuid.uuid4().hex[:8]}",
                description="Finding E spike price list",
                currency="USD",
                effective_start_date=date(2026, 1, 1),
                effective_end_date=date(2099, 12, 31),
                rates=[],
            )
            self.rate = Rate.objects.create(
                price_list=self.price_list,
                custom_name="spike-finding-e-rate",
                metric="cpu_core_usage_per_hour",
                metric_type="cpu",
                cost_type="Supplementary",
                default_rate=0.01,
            )
            self.cost_model = CostModel.objects.create(
                name=f"spike-finding-e-cm-{uuid.uuid4().hex[:8]}",
                description="Finding E spike cost model",
                source_type=Provider.PROVIDER_OCP,
                rates=[],
            )

        self.provider_a = self._create_provider("finding-e-a")
        self.provider_b = self._create_provider("finding-e-b")

        with schema_context(self.schema):
            # Both providers share the same cost model (and therefore the same
            # price list) -- this is what gives the bug its cross-provider blast
            # radius: an edit made because of provider A's rates can crash
            # provider B's concurrent RTU write.
            CostModelMap.objects.create(cost_model=self.cost_model, provider_uuid=self.provider_a.uuid)
            CostModelMap.objects.create(cost_model=self.cost_model, provider_uuid=self.provider_b.uuid)
            PriceListCostModelMap.objects.create(price_list=self.price_list, cost_model=self.cost_model, priority=1)

        period_start = datetime(2026, 4, 1, tzinfo=settings.UTC)
        period_end = datetime(2026, 5, 1, tzinfo=settings.UTC)
        with schema_context(self.schema):
            self.report_period_a = OCPUsageReportPeriod.objects.create(
                cluster_id=f"spike-e-cluster-a-{uuid.uuid4().hex[:8]}",
                report_period_start=period_start,
                report_period_end=period_end,
                provider_id=self.provider_a.uuid,
            )
            self.report_period_b = OCPUsageReportPeriod.objects.create(
                cluster_id=f"spike-e-cluster-b-{uuid.uuid4().hex[:8]}",
                report_period_start=period_start,
                report_period_end=period_end,
                provider_id=self.provider_b.uuid,
            )
            # Pre-existing RTU row for provider A referencing the rate -- this is what
            # sync_rate_table's cascade will delete, and is what forces Django to walk
            # the RatesToUsage relation at all.
            RatesToUsage.objects.create(
                source_uuid_id=self.provider_a.uuid,
                report_period_id=self.report_period_a.id,
                rate_id=self.rate.uuid,
                cost_model_id=self.cost_model.uuid,
                usage_start=period_start.date(),
                usage_end=period_start.date(),
                cluster_id=self.report_period_a.cluster_id,
                custom_name="pre-existing-rate-row",
                metric_type="cpu_usage",
            )

    def tearDown(self):
        with schema_context(self.schema):
            RatesToUsage.objects.filter(
                report_period_id__in=[self.report_period_a.id, self.report_period_b.id]
            ).delete()
            OCPUsageReportPeriod.objects.filter(pk__in=[self.report_period_a.pk, self.report_period_b.pk]).delete()
            Rate.objects.filter(price_list=self.price_list).delete()
            CostModel.objects.filter(uuid=self.cost_model.uuid).delete()
            PriceList.objects.filter(uuid=self.price_list.uuid).delete()
        # Use the instance-level delete() (not queryset .delete()) -- it routes through
        # cascade_delete(), which skips relations whose table doesn't exist in this
        # narrow test run, unlike Django's default bulk-delete collector. The class-level
        # @patch only wraps test_* methods, so post_delete's celery dispatch needs its own
        # patch here too.
        with patch("masu.celery.tasks.delete_archived_data.delay", lambda *a, **k: None):
            self.provider_a.delete()
            self.provider_b.delete()

    def _create_provider(self, tag):
        provider = Provider(
            uuid=uuid.uuid4(),
            name=f"spike-finding-e-{tag}-{uuid.uuid4().hex[:8]}",
            type=Provider.PROVIDER_OCP,
            setup_complete=False,
            active=True,
            customer=self.customer,
        )
        provider.save()
        create_test_provider(self.schema, provider)
        return provider

    def _run_rate_delete(self, results):
        """Simulates sync_rate_table's stale-rate cleanup for provider A's cost model.

        Calls sync_rate_table() directly with an empty rates payload, exactly
        what CostModelManager.update() does on a PUT that removes this rate.
        """
        try:
            with schema_context(self.schema):
                sync_rate_table(self.price_list, [])
            results["delete"] = "ok"
        except IntegrityError as exc:
            results["delete"] = f"INTEGRITY_ERROR: {type(exc).__name__}: {exc}"
        except OperationalError as exc:
            results["delete"] = f"DEADLOCK/OPERATIONAL_ERROR: {type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001 -- spike wants to see everything
            results["delete"] = f"{type(exc).__name__}: {exc}"
        finally:
            connection.close()

    def _run_rate_delete_with_mid_cascade_release(self, results, barrier):
        """Same as _run_rate_delete, but releases barrier deterministically mid-cascade.

        Connects a temporary pre_delete receiver on RatesToUsage so the
        unprotected writer is released while provider A's RatesToUsage row
        is being collected/deleted, but before the Rate row itself is gone --
        forcing the interleaving deterministically rather than relying on
        thread-scheduling luck. sync_rate_table's stale-Rate delete is a
        plain Django queryset .delete(), so it still goes through the
        collector and fires this signal, pre- or post-fix.
        """

        def _on_pre_delete(sender, instance, **kwargs):
            if isinstance(instance, RatesToUsage) and instance.rate_id == self.rate.uuid:
                barrier.wait()

        pre_delete.connect(_on_pre_delete, sender=RatesToUsage, weak=False)
        try:
            self._run_rate_delete(results)
        finally:
            pre_delete.disconnect(_on_pre_delete, sender=RatesToUsage)

    def _create_concurrent_row(self, custom_name):
        RatesToUsage.objects.create(
            source_uuid_id=self.provider_b.uuid,
            report_period_id=self.report_period_b.id,
            rate_id=self.rate.uuid,
            cost_model_id=self.cost_model.uuid,
            usage_start=date(2026, 4, 15),
            usage_end=date(2026, 4, 15),
            cluster_id=self.report_period_b.cluster_id,
            custom_name=custom_name,
            metric_type="cpu_usage",
        )

    def _run_unprotected_insert(self, results, barrier):
        """Uncoordinated concurrent write into rates_to_usage for a DIFFERENT provider, same rate_id."""
        try:
            barrier.wait()
            with schema_context(self.schema):
                self._create_concurrent_row("unprotected-writer-rate")
            results["insert"] = "ok"
        except IntegrityError as exc:
            results["insert"] = f"INTEGRITY_ERROR: {type(exc).__name__}: {exc}"
        except OperationalError as exc:
            results["insert"] = f"DEADLOCK/OPERATIONAL_ERROR: {type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001
            results["insert"] = f"{type(exc).__name__}: {exc}"
        finally:
            connection.close()

    def _run_protected_insert(self, results, barrier, hold_seconds=1.5):
        """Simulates a write going through _distribution_provider_lock for provider B, like a real RTU step.

        Sleeps for hold_seconds while still holding the lock, *after*
        signaling the barrier, so the (much faster, near-empty schema)
        sync_rate_table call has ample time to attempt -- and, with the fix,
        block on -- the same advisory lock before this thread's actual
        INSERT runs.
        """
        try:
            with schema_context(self.schema):
                accessor = OCPReportDBAccessor(schema=self.schema)
                with accessor._distribution_provider_lock(self.provider_b.uuid):
                    barrier.wait()
                    time.sleep(hold_seconds)
                    self._create_concurrent_row("protected-writer-rate")
            results["insert"] = "ok"
        except IntegrityError as exc:
            results["insert"] = f"INTEGRITY_ERROR: {type(exc).__name__}: {exc}"
        except OperationalError as exc:
            results["insert"] = f"DEADLOCK/OPERATIONAL_ERROR: {type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001
            results["insert"] = f"{type(exc).__name__}: {exc}"
        finally:
            connection.close()

    def test_unprotected_rtu_insert_crashes_during_rate_delete(self):
        """Known residual gap: a write that bypasses the RTU lock helper entirely still crashes.

        Advisory locks are cooperative -- Postgres does not enforce them on
        the underlying table. This documents that a raw, uncoordinated
        RatesToUsage.objects.create() call (something outside the
        established RTU accessor pattern) remains exposed even after the
        fix. If this test ever stops crashing, something changed about how
        Postgres enforces (or this codebase issues) advisory locks and this
        test's expectations need updating.
        """
        barrier = threading.Barrier(2, timeout=15)
        results = {"delete": None, "insert": None}

        t_delete = threading.Thread(
            target=self._run_rate_delete_with_mid_cascade_release,
            args=(results, barrier),
        )
        t_insert = threading.Thread(target=self._run_unprotected_insert, args=(results, barrier))
        t_delete.start()
        t_insert.start()
        t_delete.join(timeout=20)
        t_insert.join(timeout=20)

        self.assertIsNotNone(results["delete"], "delete thread did not complete")
        self.assertIsNotNone(results["insert"], "insert thread did not complete")
        deadlocked = any(r and r.startswith("DEADLOCK") for r in results.values())
        if deadlocked:
            self.fail(f"Concurrent Rate delete vs. unprotected RTU insert deadlocked: {results}")
        self.assertEqual(
            results["delete"],
            "ok",
            f"sync_rate_table thread failed unexpectedly: {results['delete']}",
        )
        self.assertTrue(
            results["insert"].startswith("INTEGRITY_ERROR"),
            "Expected the known, still-open FK-violation crash for an uncoordinated writer; got: "
            f"{results['insert']}. If this now succeeds, something about how Postgres enforces (or this "
            "codebase issues) advisory locks may have changed -- update this test.",
        )

    def test_protected_rtu_insert_serializes_cleanly_against_rate_delete(self):
        """Fix verification: a writer using _distribution_provider_lock no longer crashes.

        sync_rate_table() now takes the same pg_advisory_lock(hashtext(
        provider_uuid)) for every provider on every cost model attached to
        the price list before it starts deleting stale Rate rows. A writer
        already holding that lock for provider B (as every real RTU write
        step does) forces sync_rate_table to wait until the writer's lock is
        released, instead of racing it.

        Deterministic by construction: the protected writer holds the lock
        for 1.5s (real wall-clock sleep) before its actual INSERT. Without
        the fix, sync_rate_table's delete over a near-empty tenant schema
        reliably completes in well under that window, deleting the Rate row
        out from under the writer and reproducing an IntegrityError. With the
        fix, sync_rate_table blocks on the same advisory lock for the full
        1.5s and only proceeds after the writer's INSERT has already landed
        -- both succeed.
        """
        barrier = threading.Barrier(2, timeout=15)
        results = {"delete": None, "insert": None}

        t_insert = threading.Thread(target=self._run_protected_insert, args=(results, barrier))
        t_delete = threading.Thread(target=self._run_rate_delete, args=(results,))
        t_insert.start()
        barrier.wait(timeout=15)  # don't start sync_rate_table until the writer actually holds the lock
        t_delete.start()
        t_delete.join(timeout=20)
        t_insert.join(timeout=20)

        deadlocked = any(r and r.startswith("DEADLOCK") for r in results.values())
        if deadlocked:
            self.fail(f"Concurrent Rate delete vs. protected RTU insert deadlocked: {results}")

        self.assertEqual(
            results["insert"],
            "ok",
            f"protected writer thread failed: {results['insert']}",
        )
        self.assertEqual(
            results["delete"],
            "ok",
            f"sync_rate_table thread failed: {results['delete']}",
        )
