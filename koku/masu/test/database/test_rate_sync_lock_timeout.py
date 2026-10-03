#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Regression test: _provider_distribution_lock must not block indefinitely.

COST-8126 (follow-up to COST-8113 / PR #6268's deferred lock_timeout CodeRabbit
finding: https://github.com/project-koku/koku/pull/6268#discussion_r3823451698).

cost_models.rate_sync._provider_distribution_lock acquires a session-scoped
pg_advisory_lock(hashtext(provider_uuid)) with no timeout, so a concurrent
holder of the same key -- e.g. OCPReportDBAccessor._distribution_provider_lock
(every RTU write step), Provider._rtu_distribution_lock (Provider.delete()),
or another sync_rate_table call for the same provider -- blocks this call
indefinitely. Because sync_rate_table is reached synchronously from the
cost-model/price-list API (CostModelManager.create/update,
PriceListManager.create/update, PriceListViewSet._ensure_rate_sync), an
indefinite wait here hangs the API request thread with no way to fail fast or
retry.

Spiked and confirmed against a real Postgres 16 instance (see COST-8126): a
plain, non-LOCAL `SET lock_timeout = '<n>ms'` immediately before the
pg_advisory_lock acquisition -- reset via `RESET lock_timeout` in a finally --
bounds the wait and raises psycopg2.errors.LockNotAvailable (SQLSTATE 55P03,
wrapped by Django as OperationalError) instead of hanging. Confirmed this does
NOT poison the session: lock acquisition here runs in autocommit mode (no
transaction.atomic() -- see _provider_distribution_lock's docstring), so a
55P03 failure leaves the connection fully usable, and RESET plus any
statements after it execute normally.

Fix: _provider_distribution_lock now accepts a timeout_ms bound (default
PROVIDER_LOCK_TIMEOUT_MS) and raises ProviderDistributionLockTimeout, wrapping
the underlying OperationalError, when it cannot acquire the lock in time --
instead of waiting forever.
"""
import threading
import time
import uuid

import django.test
from django.db import connection

from cost_models.rate_sync import _provider_distribution_lock
from cost_models.rate_sync import ProviderDistributionLockTimeout


class ProviderDistributionLockTimeoutTest(django.test.TransactionTestCase):
    """COST-8126: _provider_distribution_lock must bound its pg_advisory_lock wait.

    Uses a short, test-local timeout_ms (passed directly to
    _provider_distribution_lock) rather than the real production default, so
    this runs in a couple of seconds instead of tying up the suite for the
    full production timeout.
    """

    TEST_TIMEOUT_MS = 500

    def _fixture_teardown(self):
        """Skip TRUNCATE flush -- django-tenants FK graph breaks TransactionTestCase flush."""

    def tearDown(self):
        # Defensive: release anything this connection may still hold for the test key(s),
        # in case an assertion fails mid-test and skips the normal unlock path.
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock_all()")

    def _hold_lock_then_release(self, provider_uuid, hold_seconds, results, barrier):
        try:
            with _provider_distribution_lock(provider_uuid):
                barrier.wait()
                time.sleep(hold_seconds)
            results["holder"] = "ok"
        except Exception as exc:  # noqa: BLE001 -- test wants to see everything
            results["holder"] = f"{type(exc).__name__}: {exc}"
        finally:
            connection.close()

    def test_waiter_times_out_instead_of_blocking_indefinitely(self):
        """Fix verification: a concurrent _provider_distribution_lock call for the same
        provider_uuid, held by another session for longer than timeout_ms, must raise
        ProviderDistributionLockTimeout well before the holder releases -- not block
        until it does.

        Before the fix, this test fails: the waiter has no timeout at all, so it blocks
        for the holder's full hold_seconds (proving there is no bound), and no
        ProviderDistributionLockTimeout is ever raised.
        """
        provider_uuid = f"spike-8126-{uuid.uuid4()}"
        hold_seconds = (self.TEST_TIMEOUT_MS / 1000) + 2.0
        barrier = threading.Barrier(2, timeout=15)
        results = {"holder": None}

        t_holder = threading.Thread(
            target=self._hold_lock_then_release, args=(provider_uuid, hold_seconds, results, barrier)
        )
        t_holder.start()
        barrier.wait(timeout=15)

        t0 = time.monotonic()
        with self.assertRaises(ProviderDistributionLockTimeout):
            with _provider_distribution_lock(provider_uuid, timeout_ms=self.TEST_TIMEOUT_MS):
                self.fail("waiter should never have acquired the lock while the holder held it")
        elapsed = time.monotonic() - t0

        t_holder.join(timeout=hold_seconds + 10)
        self.assertEqual(results["holder"], "ok", f"lock-holder thread failed: {results['holder']}")

        self.assertLess(
            elapsed,
            hold_seconds,
            f"waiter took {elapsed:.3f}s, not less than the holder's {hold_seconds:.3f}s hold -- it "
            "blocked for (at least close to) the full hold duration instead of timing out early "
            "(COST-8126 regression: no lock_timeout bound).",
        )
        self.assertGreaterEqual(
            elapsed,
            (self.TEST_TIMEOUT_MS / 1000) * 0.5,
            f"waiter returned in {elapsed:.3f}s, well under its {self.TEST_TIMEOUT_MS}ms timeout -- "
            "it did not actually contend for the lock, so this isn't testing what it claims to.",
        )

    def test_successful_acquisition_still_works_and_resets_lock_timeout(self):
        """Fix must not regress the non-contended path: the lock acquires normally, the
        protected body runs, the lock releases, and lock_timeout is reset afterward so it
        doesn't leak onto unrelated statements later on this pooled connection.
        """
        provider_uuid = f"spike-8126-{uuid.uuid4()}"
        entered = False
        with _provider_distribution_lock(provider_uuid, timeout_ms=self.TEST_TIMEOUT_MS):
            entered = True
        self.assertTrue(entered, "_provider_distribution_lock did not yield control to its caller")

        with connection.cursor() as cursor:
            cursor.execute("SHOW lock_timeout")
            self.assertEqual(
                cursor.fetchone()[0],
                "0",
                "lock_timeout leaked past _provider_distribution_lock's scope -- RESET did not run "
                "(or ran incorrectly), which would silently apply a lock_timeout to unrelated "
                "statements on this pooled connection afterward.",
            )
