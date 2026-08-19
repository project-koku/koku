#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Spike: does Provider.delete()'s deferred rates_to_usage cascade race concurrent RTU writers?

COST-7249 deadlock preflight, Finding B. rates_to_usage's FKs to
reporting_ocpusagereportperiod and reporting_tenant_api_provider are
`ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED` (migration 0353) --
rates_to_usage never matches Provider._get_linked_table_names' table-name
regex, so it is never explicitly/eagerly deleted by Provider.delete()'s
cascade walk. Cleanup depends entirely on the deferred FK firing at the
COMMIT of the single, dozens-of-tables-wide transaction.atomic() block in
Provider.delete().

First spike (unprotected writer, a raw INSERT with no coordination): a
concurrent writer forced into the same window as the delete blocks on the
delete's lock, then crashes with a foreign-key IntegrityError once the
delete commits and the parent row is gone -- 100% reproducible.

Fix: Provider.delete() now acquires the same pg_advisory_lock(hashtext(
provider_uuid)) as OCPReportDBAccessor._distribution_provider_lock, which
populate_distributed_cost_sql / aggregate_rates_to_daily_summary /
populate_markup_rates_to_usage / _populate_cost_breakdown_ui_summary_table
already acquire for the same provider. The second test below proves that a
writer going through that same lock now serializes cleanly against a
concurrent delete instead of crashing.

Known residual gap (not fixed here, tracked separately as COST-8112):
populate_usage_rates_to_usage -- the very first write into rates_to_usage in
the whole RTU pipeline, also a DELETE-then-INSERT for the same provider/date
-range -- does not acquire _distribution_provider_lock today, so it remains
exposed to this exact race. See ocp_report_db_accessor.py.
"""
import threading
import time
import uuid
from datetime import datetime
from unittest.mock import patch

import django.test
from django.conf import settings
from django.db import connection
from django.db import IntegrityError
from django.db import OperationalError
from django_tenants.utils import schema_context

from api.iam.models import Customer
from api.provider.models import Provider
from koku.test_provider_delete_cascade import create_test_provider
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting.provider.ocp.models import RatesToUsage


@patch("masu.celery.tasks.delete_archived_data.delay", lambda *a, **k: None)
class ProviderDeleteRTURaceTest(django.test.TransactionTestCase):
    """Finding B spike: Provider.delete() vs. a concurrent RTU writer on the same report period."""

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
            name=f"spike-finding-b-{uuid.uuid4().hex[:8]}",
            type=Provider.PROVIDER_OCP,
            setup_complete=False,
            active=True,
            customer=self.customer,
        )
        self.provider.save()
        create_test_provider(self.schema, self.provider)

        period_start = datetime(2026, 3, 1, tzinfo=settings.UTC)
        period_end = datetime(2026, 4, 1, tzinfo=settings.UTC)
        with schema_context(self.schema):
            self.report_period = OCPUsageReportPeriod.objects.create(
                cluster_id=f"spike-cluster-{uuid.uuid4().hex[:8]}",
                report_period_start=period_start,
                report_period_end=period_end,
                provider_id=self.provider.uuid,
            )
            RatesToUsage.objects.create(
                source_uuid_id=self.provider.uuid,
                report_period_id=self.report_period.id,
                usage_start=period_start.date(),
                usage_end=period_start.date(),
                cluster_id=self.report_period.cluster_id,
                custom_name="pre-existing-rate",
                metric_type="cpu_usage",
            )

    def tearDown(self):
        with schema_context(self.schema):
            RatesToUsage.objects.filter(report_period_id=self.report_period.id).delete()
            OCPUsageReportPeriod.objects.filter(pk=self.report_period.pk).delete()
        Provider.objects.filter(pk=self.provider.pk).delete()

    def _run_delete(self, results):
        try:
            with connection.cursor():
                pass  # ensure this thread has its own connection before patching kicks in
            self.provider.delete()
            results["delete"] = "ok"
        except Exception as exc:  # noqa: BLE001 -- spike wants to see everything
            results["delete"] = f"{type(exc).__name__}: {exc}"
        finally:
            connection.close()

    def _create_concurrent_row(self, custom_name):
        RatesToUsage.objects.create(
            source_uuid_id=self.provider.uuid,
            report_period_id=self.report_period.id,
            usage_start=datetime(2026, 3, 15).date(),
            usage_end=datetime(2026, 3, 15).date(),
            cluster_id=self.report_period.cluster_id,
            custom_name=custom_name,
            metric_type="cpu_usage",
        )

    def _run_unprotected_insert(self, results, barrier):
        """Simulates a raw rates_to_usage write with no distribution-lock coordination."""
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
        """Simulates a write going through _distribution_provider_lock, like the RTU steps that use it.

        Sleeps for hold_seconds while still holding the lock, *after* signaling
        the barrier that the lock is acquired, so the (much faster, near-empty
        schema) delete cascade has ample time to attempt -- and, with the fix,
        block on -- the same advisory lock before this thread's actual INSERT
        runs. Without the fix, delete() has nothing to block on and reliably
        finishes well inside this window, reproducing the crash deterministically
        rather than by timing luck.
        """
        try:
            with schema_context(self.schema):
                accessor = OCPReportDBAccessor(schema=self.schema)
                with accessor._distribution_provider_lock(self.provider.uuid):
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

    def _delete_with_barrier_before_final_branch(self, results, barrier):
        original_delete_from_target = Provider._delete_from_target

        def patched_delete_from_target(self_provider, target_info, target_values=None):
            if target_info.get("table_name") == "reporting_ocpusagereportperiod":
                barrier.wait()
            return original_delete_from_target(self_provider, target_info, target_values)

        with patch.object(Provider, "_delete_from_target", patched_delete_from_target):
            self._run_delete(results)

    def test_unprotected_rtu_insert_crashes_during_provider_delete(self):
        """Known residual gap: an uncoordinated writer still crashes even after the fix.

        This documents populate_usage_rates_to_usage's exposure (it does not
        take _distribution_provider_lock today -- tracked as COST-8112)
        rather than asserting it is fixed -- it is intentionally not fixed by
        this change. If this test ever starts failing (i.e. the insert stops
        crashing), it means that write path started participating in the
        lock and this test's expectations -- and its docstring -- need
        updating accordingly.
        """
        barrier = threading.Barrier(2, timeout=15)
        results = {"delete": None, "insert": None}

        t_delete = threading.Thread(target=self._delete_with_barrier_before_final_branch, args=(results, barrier))
        t_insert = threading.Thread(target=self._run_unprotected_insert, args=(results, barrier))
        t_delete.start()
        t_insert.start()
        t_delete.join(timeout=20)
        t_insert.join(timeout=20)

        self.assertEqual(results["delete"], "ok", f"delete() thread failed unexpectedly: {results['delete']}")
        self.assertIsNotNone(results["insert"], "concurrent insert thread did not run")
        self.assertTrue(
            results["insert"].startswith("INTEGRITY_ERROR"),
            "Expected the known, still-open FK-violation crash for an uncoordinated writer; got: "
            f"{results['insert']}. If this now succeeds, populate_usage_rates_to_usage-style writers "
            "may have started participating in _distribution_provider_lock -- update this test.",
        )

    def test_protected_rtu_insert_serializes_cleanly_against_provider_delete(self):
        """Fix verification: a writer using _distribution_provider_lock no longer crashes.

        Provider.delete() now takes the same pg_advisory_lock(hashtext(
        provider_uuid)) before it starts its cascade. A writer already
        holding that lock (as populate_distributed_cost_sql,
        aggregate_rates_to_daily_summary, populate_markup_rates_to_usage, and
        _populate_cost_breakdown_ui_summary_table all now do) forces the
        delete to wait until the writer's lock is released, instead of
        racing it.

        Deterministic by construction, not by timing luck: the protected
        writer holds the lock for 1.5s (real wall-clock sleep) before its
        actual INSERT. Without the fix, delete()'s cascade over a near-empty
        tenant schema reliably completes in well under that window (compare
        the unprotected test's ~0.1-0.2s total runtime), so it would delete
        the report_period out from under the writer and reproduce the same
        IntegrityError as the unprotected case. With the fix, delete() blocks
        on the same advisory lock for the full 1.5s and only proceeds after
        the writer's INSERT has already landed -- both succeed.
        """
        barrier = threading.Barrier(2, timeout=15)
        results = {"delete": None, "insert": None}

        # No _delete_from_target barrier here: Provider.delete() should simply
        # block on the advisory lock at the very top, before it ever reaches
        # _cascade_delete, so there is nothing to synchronize mid-cascade.
        t_delete = threading.Thread(target=self._run_delete, args=(results,))
        t_insert = threading.Thread(target=self._run_protected_insert, args=(results, barrier))
        t_insert.start()
        barrier.wait(timeout=15)  # don't start delete() until the writer actually holds the lock
        t_delete.start()
        t_delete.join(timeout=20)
        t_insert.join(timeout=20)

        self.assertEqual(results["insert"], "ok", f"protected writer thread failed: {results['insert']}")
        self.assertEqual(results["delete"], "ok", f"delete() thread failed: {results['delete']}")
