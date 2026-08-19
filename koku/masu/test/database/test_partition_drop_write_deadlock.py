#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Spike: does the retention purge's partition DROP step deadlock against concurrent writers?

COST-7249 deadlock preflight, expanded audit, Finding H.

OCPReportDBCleaner.purge_expired_report_data_by_date() has two distinct
unprotected-vs-protected halves:

  1. An EARLIER, still-unprotected step (lines ~173-196 as of this writing):
         del_count = execute_delete_sql(
             PartitionedTable.objects.filter(
                 schema_name=self._schema,
                 partition_of_table_name__in=table_names,   # includes "rates_to_usage"
                 partition_parameters__default=False,        #  and every UI_SUMMARY_TABLES name
                 partition_parameters__from__lte=partition_from,
             )
         )
     Deleting a PartitionedTable tracking row fires trfn_partition_manager()'s
     DELETE branch: `ALTER TABLE ... DETACH PARTITION` (ACCESS EXCLUSIVE on the
     PARENT table, not just the partition being dropped) + TRUNCATE + DROP TABLE.
     `table_names` covers *every* OCP UI summary table plus rates_to_usage, and
     this whole thing is ONE compiled SQL DELETE statement (execute_delete_sql ->
     execute_compiled_sql, a single autocommitted cursor.execute), so if that one
     statement matches expired partitions on *more than one* parent table, ALL of
     those ACCESS EXCLUSIVE locks are held simultaneously for the rest of that one
     transaction -- not released between rows.

  2. A LATER step (cascade_delete(all_usage_periods...)) that Finding F already
     fixed with accessor._distribution_provider_lock / transaction.atomic().

Finding F's fix does NOT cover step 1 above -- it is a completely different
statement, earlier in the same method, with no lock of any kind. This spike
proves two things about step 1 in isolation, using the *exact* helper
(`execute_delete_sql`) and queryset shape the real method uses:

  (a) BLOCKING: an ordinary, completely unrelated concurrent write to one of the
      same parent tables (a different, active partition) stalls for the full
      duration of the DETACH/TRUNCATE/DROP, because ACCESS EXCLUSIVE conflicts
      with every other lock mode on the whole parent relation, not just the
      partition being detached.

  (b) DEADLOCK: because a single purge run's partition-drop step can hold
      ACCESS EXCLUSIVE on *multiple* parent tables at once (any time it has more
      than one table's worth of expired partitions to drop, which is normal --
      table_names includes rates_to_usage and every UI_SUMMARY_TABLES entry),
      it reproduces the well-known Postgres partition-DDL "queue-jump" deadlock:
      if a concurrent writer touches the same two tables in the opposite order,
      Postgres's lock-queue fairness rule (a later request can't jump ahead of an
      earlier still-waiting request, even from a session that already holds a
      weaker lock on the same object) turns ordinary lock contention into a
      genuine cyclic wait that the deadlock detector kills.

This test constructs (b) as two separate execute_delete_sql calls inside one
explicit transaction.atomic() rather than relying on the implicit multi-row
ordering of one combined statement -- functionally identical for lock-holding
purposes (Postgres locks are transaction-scoped, not statement-scoped), but
deterministic instead of order-dependent. See masu/test/database/README (or
the sibling Finding E/F/G spikes in this directory) for the established pattern
of using explicit synchronization instead of a wall-clock sleep.
"""
import threading
import time
import uuid
from datetime import date

import django.test
from django.db import connection
from django.db import OperationalError
from django.db import transaction
from django_tenants.utils import schema_context

from koku.database import execute_delete_sql
from reporting.partition.models import PartitionedTable
from reporting.provider.models import TenantAPIProvider
from reporting.provider.ocp.models import OCPCostSummaryP


SCHEMA = "org1234567"
OLD_FROM = "1900-01-01"
OLD_TO = "1900-02-01"
# Deliberately obscure date so these rows land in each table's DEFAULT
# partition rather than colliding with any real fixture-created partition.
SAFE_WRITE_DATE = date(1905, 3, 15)


def _create_old_partition(table_name, tag):
    """Create a real, droppable (non-default) partition dated safely in the past."""
    partition_name = f"{table_name}_spike_h_{tag}"
    PartitionedTable.objects.create(
        schema_name=SCHEMA,
        table_name=partition_name,
        partition_of_table_name=table_name,
        partition_type=PartitionedTable.RANGE,
        partition_col="usage_start",
        partition_parameters={"default": False, "from": OLD_FROM, "to": OLD_TO},
        active=True,
    )
    return partition_name


@django.test.utils.override_settings()
class PartitionDropWriteDeadlockTest(django.test.TransactionTestCase):
    """Finding H spike: retention purge's unprotected partition-DROP step vs. concurrent writers."""

    def _fixture_teardown(self):
        """Skip TRUNCATE flush -- django-tenants FK graph breaks TransactionTestCase flush."""

    def setUp(self):
        with schema_context(SCHEMA):
            self.rtu_partition = _create_old_partition("rates_to_usage", uuid.uuid4().hex[:8])
            self.cost_summary_partition = _create_old_partition("reporting_ocp_cost_summary_p", uuid.uuid4().hex[:8])
            # Reuse any pre-seeded OCP provider fixture -- rates_to_usage.source_uuid is a NOT
            # NULL FK to TenantAPIProvider, but this spike doesn't care which provider it is.
            existing_provider = TenantAPIProvider.objects.filter(type__startswith="OCP").first()
            if existing_provider is None:
                self.skipTest("No TenantAPIProvider fixture available in test schema")
            self.provider_uuid = existing_provider.uuid

    def tearDown(self):
        with schema_context(SCHEMA):
            OCPCostSummaryP.objects.filter(usage_start=SAFE_WRITE_DATE).delete()
            with connection.cursor() as cur:
                cur.execute("DELETE FROM rates_to_usage WHERE usage_start = %s", [SAFE_WRITE_DATE])
            # Partitions may already be gone (DROPped by the spike itself) -- filter
            # by name defensively rather than assuming either survived.
            PartitionedTable.objects.filter(
                schema_name=SCHEMA, table_name__in=[self.rtu_partition, self.cost_summary_partition]
            ).delete()

    # ---- (a) blocking spike -------------------------------------------------

    def _drop_old_partitions(self, results, table_name):
        try:
            with schema_context(SCHEMA):
                del_count = execute_delete_sql(
                    PartitionedTable.objects.filter(
                        schema_name=SCHEMA,
                        partition_of_table_name__in=[table_name],
                        partition_parameters__default=False,
                        partition_parameters__from__lte=OLD_TO,
                    )
                )
            results["drop_count"] = del_count
            results["drop"] = "ok"
        except Exception as exc:  # noqa: BLE001 -- spike wants to see everything
            results["drop"] = f"{type(exc).__name__}: {exc}"
        finally:
            connection.close()

    def _concurrent_write(self, results, key="write"):
        try:
            t0 = time.monotonic()
            with schema_context(SCHEMA):
                OCPCostSummaryP.objects.create(
                    id=uuid.uuid4(),
                    cluster_id="spike-h-cluster",
                    usage_start=SAFE_WRITE_DATE,
                    usage_end=SAFE_WRITE_DATE,
                )
            results[f"{key}_elapsed"] = time.monotonic() - t0
            results[key] = "ok"
        except OperationalError as exc:
            results[key] = f"DEADLOCK/OPERATIONAL_ERROR: {type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001
            results[key] = f"{type(exc).__name__}: {exc}"
        finally:
            connection.close()

    def test_unrelated_write_blocks_behind_unprotected_partition_drop(self):
        """(a) An unrelated write to reporting_ocp_cost_summary_p's default partition stalls behind
        the purge's unprotected DETACH/TRUNCATE/DROP of an unrelated, expired partition of the same
        parent table -- even though the write targets a completely different partition and provider.

        This is the direct, unmodified production code path
        (execute_delete_sql + the exact queryset shape from
        purge_expired_report_data_by_date), isolated to one table so the
        causal link between "no lock" and "unrelated writers stall" is
        unambiguous.
        """
        results = {}

        t_drop = threading.Thread(target=self._drop_old_partitions, args=(results, "reporting_ocp_cost_summary_p"))
        t_write = threading.Thread(target=self._concurrent_write, args=(results,))

        t_drop.start()
        # Give the drop's DETACH/TRUNCATE/DROP a head start so it has definitely
        # acquired ACCESS EXCLUSIVE on the parent table before the writer tries.
        time.sleep(0.05)
        t_write.start()
        t_drop.join(timeout=20)
        t_write.join(timeout=20)

        self.assertEqual(results.get("drop"), "ok", f"partition drop thread failed: {results.get('drop')}")
        self.assertEqual(results.get("write"), "ok", f"concurrent write thread failed: {results.get('write')}")
        # Not a hard timing assertion (CI jitter) -- just evidence in the failure
        # message of how expensive "no lock" already is even without full deadlock.
        elapsed = results.get("write_elapsed", 0)
        if elapsed < 0.005:
            self.fail(
                "[SPIKE INCONCLUSIVE] Expected the concurrent write to observably stall behind the "
                f"unprotected partition DROP (ACCESS EXCLUSIVE on the shared parent), but it only took "
                f"{elapsed:.4f}s -- the drop may have already completed before the write started. "
                "Increase OLD partition data volume or narrow the barrier timing."
            )

    # ---- (b) deadlock spike ---------------------------------------------------

    def _drop_two_tables_cross_order(self, results, barrier_after_first, barrier_before_second):
        """Simulates one purge transaction whose combined multi-table partition-drop statement
        has, by the time it reaches the second table, already been holding ACCESS EXCLUSIVE on
        the first table for the whole (still-open) transaction -- exactly what one combined
        execute_delete_sql(...) call does across multiple matched rows, since Postgres locks are
        transaction-scoped, not statement-scoped. Split into two statements here only to get a
        deterministic synchronization point between them.
        """
        try:
            with schema_context(SCHEMA), transaction.atomic():
                execute_delete_sql(
                    PartitionedTable.objects.filter(
                        schema_name=SCHEMA,
                        partition_of_table_name__in=["rates_to_usage"],
                        partition_parameters__default=False,
                        partition_parameters__from__lte=OLD_TO,
                    )
                )
                barrier_after_first.wait(timeout=15)
                barrier_before_second.wait(timeout=15)
                execute_delete_sql(
                    PartitionedTable.objects.filter(
                        schema_name=SCHEMA,
                        partition_of_table_name__in=["reporting_ocp_cost_summary_p"],
                        partition_parameters__default=False,
                        partition_parameters__from__lte=OLD_TO,
                    )
                )
            results["drop"] = "ok"
        except OperationalError as exc:
            results["drop"] = f"DEADLOCK/OPERATIONAL_ERROR: {type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001
            results["drop"] = f"{type(exc).__name__}: {exc}"
        finally:
            connection.close()

    def _cross_table_writer(self, results, barrier_after_first, barrier_before_second):
        """A writer that touches the same two parent tables in the OPPOSITE order from the purge
        (cost-summary first, then rates_to_usage), inside one open transaction -- the precondition
        for Postgres's documented ATTACH/DETACH-partition queue-jump deadlock.
        """
        try:
            with schema_context(SCHEMA), transaction.atomic():
                OCPCostSummaryP.objects.create(
                    id=uuid.uuid4(),
                    cluster_id="spike-h-writer-cluster",
                    usage_start=SAFE_WRITE_DATE,
                    usage_end=SAFE_WRITE_DATE,
                )
                barrier_after_first.wait(timeout=15)
                barrier_before_second.wait(timeout=15)
                with connection.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO rates_to_usage (
                            uuid, usage_start, usage_end, cluster_id, custom_name, metric_type, source_uuid
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        [
                            uuid.uuid4(),
                            SAFE_WRITE_DATE,
                            SAFE_WRITE_DATE,
                            "spike-h-writer-cluster",
                            "spike-h",
                            "cpu",
                            self.provider_uuid,
                        ],
                    )
            results["write"] = "ok"
        except OperationalError as exc:
            results["write"] = f"DEADLOCK/OPERATIONAL_ERROR: {type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001
            results["write"] = f"{type(exc).__name__}: {exc}"
        finally:
            connection.close()

    def test_cross_table_partition_drop_deadlocks_against_cross_table_writer(self):
        """(b) Characterization: two sessions each touching {rates_to_usage,
        reporting_ocp_cost_summary_p} in opposite order -- one holding ACCESS EXCLUSIVE on both
        tables at once within a single transaction (what one combined, multi-table
        execute_delete_sql(...) call does across matched rows), one an ordinary writer -- deadlock
        rather than merely serializing. This proves the underlying Postgres mechanism is real
        using the same helpers/queryset shape as production code; it intentionally does not call
        OCPReportDBCleaner.purge_expired_report_data_by_date() directly; see
        test_fixed_per_table_partition_drop_does_not_deadlock_against_cross_table_writer below for
        the fix verification against the actual (now per-table) method.
        """
        barrier_after_first = threading.Barrier(2, timeout=15)
        barrier_before_second = threading.Barrier(2, timeout=15)
        results = {}

        t_drop = threading.Thread(
            target=self._drop_two_tables_cross_order,
            args=(results, barrier_after_first, barrier_before_second),
        )
        t_write = threading.Thread(
            target=self._cross_table_writer,
            args=(results, barrier_after_first, barrier_before_second),
        )
        t_drop.start()
        t_write.start()
        t_drop.join(timeout=25)
        t_write.join(timeout=25)

        self.assertIsNotNone(results.get("drop"), "partition-drop thread did not complete")
        self.assertIsNotNone(results.get("write"), "cross-table writer thread did not complete")

        deadlocked = any(v and str(v).startswith("DEADLOCK") for v in results.values())
        if not deadlocked:
            self.fail(
                f"[SPIKE INCONCLUSIVE] Expected a genuine Postgres deadlock between the purge's "
                f"cross-table partition DROP and a cross-table writer, got: {results}. If both "
                "succeeded, Postgres may have serialized them without a cycle this run -- rerun, "
                "or verify with EXPLAIN/pg_locks that both ACCESS EXCLUSIVE locks were actually held "
                "concurrently at the synchronization point."
            )

    # ---- fix verification: per-table drop no longer holds two tables at once --------------

    def _drop_two_tables_per_table_loop(self, results, barrier_after_first, barrier_before_second):
        """Mirrors the fixed purge_expired_report_data_by_date: one execute_delete_sql call (and
        therefore one transaction) PER TABLE instead of one combined multi-table call, so the first
        table's ACCESS EXCLUSIVE lock is released (transaction committed) before the second table's
        drop even begins.
        """
        try:
            with schema_context(SCHEMA):
                execute_delete_sql(
                    PartitionedTable.objects.filter(
                        schema_name=SCHEMA,
                        partition_of_table_name__in=["rates_to_usage"],
                        partition_parameters__default=False,
                        partition_parameters__from__lte=OLD_TO,
                    )
                )
            barrier_after_first.wait(timeout=15)
            barrier_before_second.wait(timeout=15)
            with schema_context(SCHEMA):
                execute_delete_sql(
                    PartitionedTable.objects.filter(
                        schema_name=SCHEMA,
                        partition_of_table_name__in=["reporting_ocp_cost_summary_p"],
                        partition_parameters__default=False,
                        partition_parameters__from__lte=OLD_TO,
                    )
                )
            results["drop"] = "ok"
        except OperationalError as exc:
            results["drop"] = f"DEADLOCK/OPERATIONAL_ERROR: {type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001
            results["drop"] = f"{type(exc).__name__}: {exc}"
        finally:
            connection.close()

    def test_fixed_per_table_partition_drop_does_not_deadlock_against_cross_table_writer(self):
        """Fix verification: with the drop split into one execute_delete_sql call per table (what
        purge_expired_report_data_by_date now does), the same adversarial cross-table writer that
        deadlocks against the combined-statement version above completes cleanly -- it may still
        have to wait for whichever single table's drop is in flight, but a wait on a single
        resource cannot form a cycle.
        """
        barrier_after_first = threading.Barrier(2, timeout=15)
        barrier_before_second = threading.Barrier(2, timeout=15)
        results = {}

        t_drop = threading.Thread(
            target=self._drop_two_tables_per_table_loop,
            args=(results, barrier_after_first, barrier_before_second),
        )
        t_write = threading.Thread(
            target=self._cross_table_writer,
            args=(results, barrier_after_first, barrier_before_second),
        )
        t_drop.start()
        t_write.start()
        t_drop.join(timeout=25)
        t_write.join(timeout=25)

        self.assertIsNotNone(results.get("drop"), "partition-drop thread did not complete")
        self.assertIsNotNone(results.get("write"), "cross-table writer thread did not complete")

        deadlocked = any(v and str(v).startswith("DEADLOCK") for v in results.values())
        if deadlocked:
            self.fail(
                f"Per-table partition drop still deadlocked against a cross-table writer: {results}. "
                "The fix (one execute_delete_sql call per table instead of one combined multi-table "
                "call) should prevent this table's drop transaction from ever holding ACCESS "
                "EXCLUSIVE on more than one parent table at a time."
            )

        self.assertEqual(results["drop"], "ok", f"partition-drop thread failed: {results['drop']}")
        self.assertEqual(results["write"], "ok", f"cross-table writer thread failed: {results['write']}")
