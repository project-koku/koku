#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Regression test: sync_rate_table must not leak its advisory lock on error.

COST-7249 deadlock preflight, broader audit, Finding G. sync_rate_table()'s
own fix for Finding E (COST-8113) acquires a session-scoped
pg_advisory_lock(hashtext(provider_uuid)) directly via a raw cursor.execute,
mirroring OCPReportDBAccessor._distribution_provider_lock and
Provider._rtu_distribution_lock.

sync_rate_table() is called from CostModelManager.create/update, both of
which are decorated @transaction.atomic -- so the lock can be acquired
*inside* an already-open Django transaction. If the protected body
(Rate.objects.filter(...).delete() / .bulk_create()) raises a DB-level
error with no intervening savepoint, Postgres marks the *entire*
transaction as aborted; the lock's own
`finally: cursor.execute("SELECT pg_advisory_unlock(...))")` then tries to
run another statement on that aborted transaction, which itself fails with
"current transaction is aborted, commands ignored until end of transaction
block" -- so the unlock never happens and the advisory lock leaks on that
connection until it's closed. A later, completely unrelated caller trying to
acquire the same provider's lock (e.g. any real RTU write step) then blocks
indefinitely -- a hang, not a Postgres-detected deadlock, so it wouldn't
show up in pg_stat_activity's deadlock logs.

The fix wraps the protected body in its own `transaction.atomic()` call
*inside* the lock's scope (see sync_rate_table), giving Postgres a rollback
boundary (a savepoint, when nested) so a raised exception is fully rolled
back before the lock's own finally block runs -- the same pattern
Provider.delete() already uses for its cascade.

Confirmed empirically before the fix: both tests below failed (the lock was
observed still held via pg_locks, and a second writer blocked until
statement_timeout). Restore the pre-fix `sync_rate_table` (drop the inner
`transaction.atomic()`) to reproduce.
"""
import threading
import uuid
from unittest.mock import patch

import django.test
from django.db import connection
from django.db import DataError
from django_tenants.utils import schema_context

from api.iam.models import Customer
from api.provider.models import Provider
from cost_models.cost_model_manager import CostModelManager
from cost_models.models import CostModel
from cost_models.models import CostModelMap
from cost_models.models import PriceList
from cost_models.models import PriceListCostModelMap
from cost_models.models import Rate
from koku.test_provider_delete_cascade import create_test_provider


@patch("masu.celery.tasks.delete_archived_data.delay", lambda *a, **k: None)
class SyncRateTableLockLeakTest(django.test.TransactionTestCase):
    """Finding G: does an error inside sync_rate_table (called from an @transaction.atomic
    caller) leave the session-scoped advisory lock held forever on that connection?
    """

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
            name=f"spike-finding-g-{uuid.uuid4().hex[:8]}",
            type=Provider.PROVIDER_OCP,
            setup_complete=False,
            active=True,
            customer=self.customer,
        )
        self.provider.save()
        create_test_provider(self.schema, self.provider)

        with schema_context(self.schema):
            self.cost_model = CostModel.objects.create(
                name=f"spike-finding-g-cm-{uuid.uuid4().hex[:8]}",
                description="Finding G spike cost model",
                source_type=Provider.PROVIDER_OCP,
                rates=[],
            )
            CostModelMap.objects.create(cost_model=self.cost_model, provider_uuid=self.provider.uuid)

    def tearDown(self):
        # Release any advisory lock this connection may still be holding for this
        # provider (the whole point of these tests is that the buggy path leaks it) so
        # it doesn't bleed into later tests that reuse this same pooled connection.
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock_all()")
        with schema_context(self.schema):
            price_list_ids = list(
                PriceListCostModelMap.objects.filter(cost_model=self.cost_model).values_list(
                    "price_list_id", flat=True
                )
            )
            Rate.objects.filter(price_list_id__in=price_list_ids).delete()
            PriceListCostModelMap.objects.filter(cost_model=self.cost_model).delete()
            PriceList.objects.filter(uuid__in=price_list_ids).delete()
            CostModelMap.objects.filter(cost_model=self.cost_model).delete()
            CostModel.objects.filter(uuid=self.cost_model.uuid).delete()
        with patch("masu.celery.tasks.delete_archived_data.delay", lambda *a, **k: None):
            self.provider.delete()

    def _lock_key(self):
        return str(self.provider.uuid)

    def _is_lock_held(self):
        """Query pg_locks on the current (still-open) connection; pg_locks is global, so this
        reports the lock even when this backend is the holder. Do not open or close a connection
        here -- closing releases the lock and hides the bug.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
                "AND objid = hashtext(%s) AND granted = true",
                [self._lock_key()],
            )
            return cursor.fetchone()[0] > 0

    @staticmethod
    def _real_db_level_failure(*args, **kwargs):
        """Injects a genuine Postgres-level error (not just a Python-raised exception).

        A mocked side_effect=SomeError() never actually sends a failing statement to
        Postgres, so the real transaction is never marked aborted at the DB level --
        that would make this spike a false negative. Issuing a real bad statement on
        the live connection reproduces the actual abort condition sync_rate_table's
        callers hit in production (e.g. a real deadlock or constraint violation).
        """
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1/0")  # division by zero -- a genuine Postgres DataError

    def test_error_inside_atomic_caller_does_not_leak_the_lock(self):
        """Fix verification: an error inside sync_rate_table's protected body, even when
        called from an @transaction.atomic caller (as CostModelManager.create/update are),
        no longer leaves the session-scoped advisory lock held on that connection.
        """
        with schema_context(self.schema):
            manager = CostModelManager(cost_model_uuid=str(self.cost_model.uuid))

            # Force Rate.objects.bulk_create (called inside sync_rate_table, while the
            # advisory lock is held, inside CostModelManager.update()'s @transaction.atomic)
            # to raise a genuine DB-level error -- simulating a real deadlock or
            # constraint violation at the same point in the call stack.
            with patch(
                "cost_models.models.Rate.objects.bulk_create",
                side_effect=self._real_db_level_failure,
            ) as mock_bulk_create:
                with self.assertRaises(DataError):
                    manager.update(
                        rates=[
                            {
                                "metric": {"name": "cpu_core_usage_per_hour"},
                                "tiered_rates": [{"unit": "USD", "value": 0.01}],
                                "cost_type": "Supplementary",
                                "name": "spike-rate",
                            }
                        ]
                    )
            # Guard against a vacuous pass: if bulk_create were never reached (e.g. a
            # serializer error or fixture problem raised first), the DataError assertion
            # above could never fire either, but a looser assertRaises(Exception) would
            # have silently accepted that too.
            mock_bulk_create.assert_called_once()

            # The connection used by this thread is now back to a clean state at the
            # Django/ORM level (@transaction.atomic on update() rolled back on exception
            # exit) -- but the *advisory lock itself* is session-scoped, not
            # transaction-scoped, so a failed unlock during the aborted transaction
            # leaves it held on this connection's underlying Postgres backend.
            #
            # IMPORTANT: do NOT call connection.close() here before checking -- closing
            # the connection terminates the Postgres backend that's holding the lock,
            # which releases it as a side effect and would hide the very bug this test
            # exists to catch. pg_locks is a global system view, so querying it from
            # this same still-open connection correctly shows whether *any* backend
            # (including this one) still holds the lock.
            still_held = self._is_lock_held()

        if still_held:
            self.fail(
                "Advisory lock was still held after the error inside sync_rate_table's "
                "@transaction.atomic caller -- it leaked. See module docstring for the "
                "fix (inner transaction.atomic() inside sync_rate_table's lock)."
            )

    def test_concurrent_writer_does_not_block_after_error(self):
        """Fix verification: a second, completely unrelated caller trying to acquire the
        same provider's lock (e.g. any real RTU write step, or another sync_rate_table
        call) succeeds promptly after the first caller's error, instead of blocking
        forever on a leaked lock.
        """
        with schema_context(self.schema):
            manager = CostModelManager(cost_model_uuid=str(self.cost_model.uuid))
            with patch(
                "cost_models.models.Rate.objects.bulk_create",
                side_effect=self._real_db_level_failure,
            ) as mock_bulk_create:
                with self.assertRaises(DataError):
                    manager.update(
                        rates=[
                            {
                                "metric": {"name": "cpu_core_usage_per_hour"},
                                "tiered_rates": [{"unit": "USD", "value": 0.01}],
                                "cost_type": "Supplementary",
                                "name": "spike-rate",
                            }
                        ]
                    )
            mock_bulk_create.assert_called_once()
        # Deliberately keep this thread's connection open and in the pool (do not close it),
        # to mimic a real Celery worker's persistent DB connection after a task fails.

        results = {"second_call": None}

        def _second_writer():
            try:
                with schema_context(self.schema), connection.cursor() as cursor:
                    cursor.execute("SET statement_timeout = '3s'")
                    cursor.execute("SELECT pg_advisory_lock(hashtext(%s))", [self._lock_key()])
                    cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", [self._lock_key()])
                results["second_call"] = "ok"
            except Exception as exc:  # noqa: BLE001
                results["second_call"] = f"{type(exc).__name__}: {exc}"
            finally:
                connection.close()

        t = threading.Thread(target=_second_writer)
        t.start()
        t.join(timeout=10)

        if t.is_alive():
            self.fail(
                "Second writer never returned within 10s -- it is blocked indefinitely on " "a leaked advisory lock."
            )
        self.assertEqual(
            results["second_call"],
            "ok",
            "Expected the second writer to acquire and release the lock promptly, but it "
            f"did not: {results['second_call']}",
        )
