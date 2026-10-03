#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Spike: does the retention/expiration purge race a concurrent rates_to_usage write?

COST-7249 deadlock preflight, expanded audit, Finding F. masu.celery.tasks.
remove_expired_data runs on a fixed monthly crontab (koku/celery.py) for ALL
tenants, entirely independent of any single provider's deletion -- it calls
OCPReportDBCleaner.purge_expired_report_data_by_date via ExpiredDataRemover,
which cascades through OCPUsageReportPeriod's relations (reaching
RatesToUsage) using this project's own cascade_delete() utility
(koku/database.py). The provider-scoped sibling entry point,
OCPReportDBCleaner.purge_expired_report_data(provider_uuid=...), shares the
exact same cascade_delete() call and is exercised here directly (safe for
the shared test schema -- it does not touch the global, date-keyed partition
DETACH/DROP logic that purge_expired_report_data_by_date also performs across
every provider's partitions in the schema, which is out of scope for this
per-provider spike but noted as a related, larger-blast-radius risk in the
same code path -- also fixed, see the by-date path's own lock in
ocp_report_db_cleaner.py).

Pre-fix, no _distribution_provider_lock was acquired anywhere in this call
chain. Fix: purge_expired_report_data(provider_uuid=...) now acquires the
same OCPReportDBAccessor._distribution_provider_lock(provider_uuid) that
every RTU write step already takes, before its cascade_delete() call.

Two tests below, mirroring the established pattern for this class of bug
(see test_ocp_provider_delete_rtu_race.py, Finding B):
- test_protected_rtu_insert_serializes_cleanly_against_retention_purge: a
  lock-coordinated writer now serializes cleanly against the purge (red
  without the fix using a deterministic held-lock delay, green with it).
- test_unprotected_rtu_insert_during_retention_purge: characterization test
  documenting that a write which bypasses the RTU accessor's lock helper
  entirely (advisory locks are cooperative, not enforced by Postgres)
  remains exposed regardless of this fix -- and, unlike a crash, silently
  loses the concurrently-inserted row instead of raising anything on either
  side.
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

import koku.database as koku_database
from api.iam.models import Customer
from api.provider.models import Provider
from koku.test_provider_delete_cascade import create_test_provider
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.processor.ocp.ocp_report_db_cleaner import OCPReportDBCleaner
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting.provider.ocp.models import RatesToUsage


@patch("masu.celery.tasks.delete_archived_data.delay", lambda *a, **k: None)
class ExpiredDataPurgeRTURaceTest(django.test.TransactionTestCase):
    """Finding F: retention-purge cascade_delete() vs. a concurrent RTU writer, same provider."""

    def _fixture_teardown(self):
        """Skip TRUNCATE flush -- django-tenants FK graph breaks TransactionTestCase flush."""

    def setUp(self):
        from koku.koku_test_runner import KokuTestRunner

        self.schema = KokuTestRunner.schema
        with schema_context(self.schema):
            self.customer = Customer.objects.filter(schema_name=self.schema).first()
        self.assertIsNotNone(
            self.customer,
            f"No Customer fixture for schema {self.schema}; the RTU race regression cannot run.",
        )

        self.provider = Provider(
            uuid=uuid.uuid4(),
            name=f"spike-finding-f-{uuid.uuid4().hex[:8]}",
            type=Provider.PROVIDER_OCP,
            setup_complete=False,
            active=True,
            customer=self.customer,
        )
        self.provider.save()
        create_test_provider(self.schema, self.provider)

        # An "expired" period -- old enough that a retention job would target it --
        # but nothing here actually depends on the date for this provider-scoped spike;
        # what matters is that RatesToUsage rows exist for report_period_id at the moment
        # cascade_delete() walks OCPUsageReportPeriod's relations.
        period_start = datetime(2024, 1, 1, tzinfo=settings.UTC)
        period_end = datetime(2024, 2, 1, tzinfo=settings.UTC)
        with schema_context(self.schema):
            self.report_period = OCPUsageReportPeriod.objects.create(
                cluster_id=f"spike-f-cluster-{uuid.uuid4().hex[:8]}",
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
                custom_name="pre-existing-rate-row",
                metric_type="cpu_usage",
            )

    def tearDown(self):
        with schema_context(self.schema):
            RatesToUsage.objects.filter(report_period_id=self.report_period.id).delete()
            OCPUsageReportPeriod.objects.filter(pk=self.report_period.pk).delete()
        with patch("masu.celery.tasks.delete_archived_data.delay", lambda *a, **k: None):
            self.provider.delete()

    def _run_purge(self, results):
        """Simulates the scheduled retention job's cascade for this provider's expired period.

        Exercises OCPReportDBCleaner.purge_expired_report_data(provider_uuid=...),
        which shares the same cascade_delete() call as the date-based
        purge_expired_report_data_by_date used by the actual monthly beat task.
        """
        try:
            with patch(
                "masu.processor.ocp.ocp_report_db_cleaner.is_ocp_tag_cleanup_disabled",
                return_value=True,
            ), patch("django.conf.settings.ONPREM", False):
                OCPReportDBCleaner(self.schema).purge_expired_report_data(provider_uuid=self.provider.uuid)
            results["purge"] = "ok"
        except IntegrityError as exc:
            results["purge"] = f"INTEGRITY_ERROR: {type(exc).__name__}: {exc}"
        except OperationalError as exc:
            results["purge"] = f"DEADLOCK/OPERATIONAL_ERROR: {type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001 -- spike wants to see everything
            results["purge"] = f"{type(exc).__name__}: {exc}"
        finally:
            connection.close()

    def _run_purge_with_mid_cascade_release(self, results, barrier, insert_committed_event):
        """Same as _run_purge, but releases the unprotected writer deterministically mid-cascade.

        cascade_delete() issues raw SQL via execute_delete_sql() rather than
        Django's ORM collector, so it does not fire pre_delete/post_delete
        signals. To force the race window open deterministically, this wraps
        koku.database.execute_delete_sql itself: when it is about to delete
        RatesToUsage rows for this test's report_period, it releases the
        concurrent writer via the barrier, then blocks on
        insert_committed_event -- set by the writer only after its INSERT has
        actually committed -- instead of a fixed wall-clock sleep. This removes
        the timing assumption (no guessing how long the writer's connection
        setup/INSERT will take under a loaded CI runner) while preserving the
        documented ordering: the writer's row must land before this specific
        DELETE's WHERE clause is (re-)evaluated at execution time.
        """
        real_execute_delete_sql = koku_database.execute_delete_sql

        def _traced_execute_delete_sql(query):
            model = getattr(getattr(query, "query", None), "model", None)
            if model is RatesToUsage:
                barrier.wait()
                if not insert_committed_event.wait(timeout=15):
                    raise AssertionError("Concurrent writer never signaled its INSERT committed within 15s")
            return real_execute_delete_sql(query)

        with patch("koku.database.execute_delete_sql", side_effect=_traced_execute_delete_sql):
            self._run_purge(results)

    def _create_concurrent_row(self, custom_name):
        RatesToUsage.objects.create(
            source_uuid_id=self.provider.uuid,
            report_period_id=self.report_period.id,
            usage_start=self.report_period.report_period_start.date(),
            usage_end=self.report_period.report_period_start.date(),
            cluster_id=self.report_period.cluster_id,
            custom_name=custom_name,
            metric_type="cpu_usage",
        )

    def _run_unprotected_insert(self, results, barrier, insert_committed_event):
        """Uncoordinated concurrent write into rates_to_usage for the SAME provider/report_period.

        Sets insert_committed_event only after the INSERT has actually
        committed (Django's default autocommit mode commits each .create()
        call immediately), so the purge thread's traced execute_delete_sql
        can wait on a real signal instead of a fixed sleep.
        """
        try:
            barrier.wait()
            with schema_context(self.schema):
                self._create_concurrent_row("unprotected-backfill-rate")
            results["insert"] = "ok"
        except IntegrityError as exc:
            results["insert"] = f"INTEGRITY_ERROR: {type(exc).__name__}: {exc}"
        except OperationalError as exc:
            results["insert"] = f"DEADLOCK/OPERATIONAL_ERROR: {type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001
            results["insert"] = f"{type(exc).__name__}: {exc}"
        finally:
            insert_committed_event.set()
            connection.close()

    def _run_protected_insert(self, results, barrier, hold_seconds=1.5):
        """Simulates a write going through _distribution_provider_lock, like a real RTU step."""
        try:
            with schema_context(self.schema):
                accessor = OCPReportDBAccessor(schema=self.schema)
                with accessor._distribution_provider_lock(self.provider.uuid):
                    barrier.wait()
                    time.sleep(hold_seconds)
                    self._create_concurrent_row("protected-backfill-rate")
            results["insert"] = "ok"
        except IntegrityError as exc:
            results["insert"] = f"INTEGRITY_ERROR: {type(exc).__name__}: {exc}"
        except OperationalError as exc:
            results["insert"] = f"DEADLOCK/OPERATIONAL_ERROR: {type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001
            results["insert"] = f"{type(exc).__name__}: {exc}"
        finally:
            connection.close()

    def test_unprotected_rtu_insert_during_retention_purge(self):
        """Known residual gap: a write that bypasses the RTU lock helper entirely still races.

        Advisory locks are cooperative -- Postgres does not enforce them on
        the underlying table. This documents that a raw, uncoordinated
        RatesToUsage.objects.create() call (something outside the
        established RTU accessor pattern) remains exposed even after the
        fix: no crash, no deadlock, but the concurrently-inserted row is
        silently discarded by the purge's cascade_delete(), because that
        raw DELETE's WHERE clause is re-evaluated at execution time and
        happily matches a row inserted moments earlier by an uncoordinated
        writer holding no lock. If this test ever fails, something changed
        about how Postgres enforces (or this codebase issues) advisory
        locks and this test's expectations need updating.
        """
        barrier = threading.Barrier(2, timeout=15)
        insert_committed_event = threading.Event()
        results = {"purge": None, "insert": None}

        t_purge = threading.Thread(
            target=self._run_purge_with_mid_cascade_release,
            args=(results, barrier, insert_committed_event),
        )
        t_insert = threading.Thread(
            target=self._run_unprotected_insert,
            args=(results, barrier, insert_committed_event),
        )
        t_purge.start()
        t_insert.start()
        t_purge.join(timeout=20)
        t_insert.join(timeout=20)

        self.assertIsNotNone(results["purge"], "purge thread did not complete")
        self.assertIsNotNone(results["insert"], "insert thread did not complete")
        deadlocked = any(r and r.startswith("DEADLOCK") for r in results.values())
        if deadlocked:
            self.fail(f"Concurrent retention purge vs. unprotected RTU insert deadlocked: {results}")
        self.assertEqual(
            results["purge"],
            "ok",
            f"purge thread failed unexpectedly: {results['purge']}",
        )
        self.assertEqual(
            results["insert"],
            "ok",
            f"insert thread failed unexpectedly: {results['insert']}",
        )

        with schema_context(self.schema):
            survived = RatesToUsage.objects.filter(
                report_period_id=self.report_period.id,
                custom_name="unprotected-backfill-rate",
            ).exists()
        self.assertFalse(
            survived,
            "Expected the known, still-open silent-data-loss gap for an uncoordinated writer racing "
            "the purge; the row unexpectedly survived. If this now survives consistently, something "
            "changed about how Postgres enforces (or this codebase issues) advisory locks -- update "
            "this test.",
        )

    def test_protected_rtu_insert_serializes_cleanly_against_retention_purge(self):
        """Fix verification: a writer using _distribution_provider_lock no longer loses its row.

        purge_expired_report_data(provider_uuid=...) now takes the same
        pg_advisory_lock(hashtext(provider_uuid)) before its cascade_delete()
        call. A writer already holding that lock (as every real RTU write
        step does) forces the purge to wait until the writer's lock is
        released, instead of racing it and silently discarding its row.

        Deterministic by construction: the protected writer holds the lock
        for 1.5s (real wall-clock sleep) before its actual INSERT. Without
        the fix, the purge's cascade over a near-empty tenant schema
        reliably completes in well under that window and silently discards
        the row inserted moments later. With the fix, the purge blocks on
        the same advisory lock for the full 1.5s and only proceeds after the
        writer's INSERT has already landed -- and that row survives.
        """
        barrier = threading.Barrier(2, timeout=15)
        results = {"purge": None, "insert": None}

        t_insert = threading.Thread(target=self._run_protected_insert, args=(results, barrier))
        t_purge = threading.Thread(target=self._run_purge, args=(results,))
        t_insert.start()
        barrier.wait(timeout=15)  # don't start the purge until the writer actually holds the lock
        t_purge.start()
        t_purge.join(timeout=20)
        t_insert.join(timeout=20)

        deadlocked = any(r and r.startswith("DEADLOCK") for r in results.values())
        if deadlocked:
            self.fail(f"Concurrent retention purge vs. protected RTU insert deadlocked: {results}")

        # This provider-scoped purge deletes *all* of this provider's report periods
        # unconditionally, so the freshly-inserted row is still expected to be swept
        # up once the purge proceeds -- that's correct, not a regression. What the
        # fix actually guarantees is the assertion below: the writer's INSERT itself
        # lands cleanly against a still-existing parent report_period (no FK
        # IntegrityError) instead of racing the purge's cascade to completion, which
        # -- without the fix -- reliably finishes (deleting the parent report period
        # entirely) well inside this writer's 1.5s held-lock window, since nothing
        # blocks it pre-fix.
        self.assertEqual(
            results["insert"],
            "ok",
            f"protected writer thread failed: {results['insert']}",
        )
        self.assertEqual(results["purge"], "ok", f"purge thread failed: {results['purge']}")
