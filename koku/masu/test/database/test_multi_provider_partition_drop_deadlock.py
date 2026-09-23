#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Spike: does AWS/Azure/GCP's retention-purge partition-drop step share OCP's Finding H deadlock?

COST-7249 deadlock preflight, expanded audit, Finding I.

AWSReportDBCleaner / AzureReportDBCleaner / GCPReportDBCleaner.purge_expired_report_data_by_date
all drop expired partitions across multiple parent tables (their own line-item daily summary
table, the OCP-on-cloud cross-reference tables, and every UI_SUMMARY_TABLES entry) via the exact
same anti-pattern already fixed for OCP under COST-8115 (Finding H): one combined
`execute_delete_sql(PartitionedTable.objects.filter(partition_of_table_name__in=table_names, ...))`
call spanning every table at once.

Deleting a PartitionedTable row fires trfn_partition_manager()'s DELETE branch -- ACCESS EXCLUSIVE
DETACH/TRUNCATE/DROP on the *parent* table -- and because the combined call is one SQL statement /
one transaction, it can hold ACCESS EXCLUSIVE on several different parent tables simultaneously.
That is the precondition for Postgres's documented ATTACH/DETACH-partition "queue-jump" deadlock
against any concurrent writer touching the same tables in the opposite order.

This is the identical, provider-agnostic Postgres mechanism already proven deterministically for
OCP in masu/test/database/test_partition_drop_write_deadlock.py. Rather than re-deriving the
mechanism from scratch, this test confirms it reproduces against AWS's real
table_names/queryset shape (representative of all three -- AWS/Azure/GCP's
purge_expired_report_data_by_date bodies are structurally identical), then verifies the same
per-table-loop fix (already applied to OCP) resolves it here too.
"""
import threading
import uuid
from datetime import date

import django.test
from django.db import connection
from django.db import OperationalError
from django.db import transaction
from django_tenants.utils import schema_context

from koku.database import execute_delete_sql
from reporting.partition.models import PartitionedTable
from reporting.provider.aws.models import AWSCostEntryLineItemDailySummary
from reporting.provider.aws.models import AWSCostSummaryP


SCHEMA = "org1234567"
OLD_FROM = "1900-01-01"
OLD_TO = "1900-02-01"
SAFE_WRITE_DATE = date(1906, 4, 10)
TABLE_A = "reporting_awscostentrylineitem_daily_summary"
TABLE_B = "reporting_aws_cost_summary_p"


def _create_old_partition(table_name, tag):
    partition_name = f"{table_name}_spike_i_{tag}"
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


class MultiProviderPartitionDropDeadlockTest(django.test.TransactionTestCase):
    """Finding I spike: AWS's (representative of AWS/Azure/GCP) partition-DROP step vs. concurrent writers."""

    def _fixture_teardown(self):
        """Skip TRUNCATE flush -- django-tenants FK graph breaks TransactionTestCase flush."""

    def setUp(self):
        with schema_context(SCHEMA):
            self.partition_a = _create_old_partition(TABLE_A, uuid.uuid4().hex[:8])
            self.partition_b = _create_old_partition(TABLE_B, uuid.uuid4().hex[:8])

    def tearDown(self):
        with schema_context(SCHEMA):
            AWSCostSummaryP.objects.filter(usage_start=SAFE_WRITE_DATE).delete()
            AWSCostEntryLineItemDailySummary.objects.filter(usage_start=SAFE_WRITE_DATE).delete()
            PartitionedTable.objects.filter(
                schema_name=SCHEMA, table_name__in=[self.partition_a, self.partition_b]
            ).delete()

    def _drop_table(self, table_name):
        with schema_context(SCHEMA):
            return execute_delete_sql(
                PartitionedTable.objects.filter(
                    schema_name=SCHEMA,
                    partition_of_table_name__in=[table_name],
                    partition_parameters__default=False,
                    partition_parameters__from__lte=OLD_TO,
                )
            )

    # ---- (a) characterization: combined multi-table call deadlocks -----------------------

    def _drop_combined_cross_order(self, results, barrier_after_first, barrier_before_second):
        """Mirrors the pre-fix AWS/Azure/GCP code: one transaction touching both tables."""
        try:
            with schema_context(SCHEMA), transaction.atomic():
                execute_delete_sql(
                    PartitionedTable.objects.filter(
                        schema_name=SCHEMA,
                        partition_of_table_name__in=[TABLE_A],
                        partition_parameters__default=False,
                        partition_parameters__from__lte=OLD_TO,
                    )
                )
                barrier_after_first.wait(timeout=15)
                barrier_before_second.wait(timeout=15)
                execute_delete_sql(
                    PartitionedTable.objects.filter(
                        schema_name=SCHEMA,
                        partition_of_table_name__in=[TABLE_B],
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
        try:
            with schema_context(SCHEMA), transaction.atomic():
                AWSCostSummaryP.objects.create(id=uuid.uuid4(), usage_start=SAFE_WRITE_DATE, usage_end=SAFE_WRITE_DATE)
                barrier_after_first.wait(timeout=15)
                barrier_before_second.wait(timeout=15)
                AWSCostEntryLineItemDailySummary.objects.create(
                    uuid=uuid.uuid4(),
                    usage_start=SAFE_WRITE_DATE,
                    usage_account_id="999999999999",
                    product_code="AmazonSpikeI",
                )
            results["write"] = "ok"
        except OperationalError as exc:
            results["write"] = f"DEADLOCK/OPERATIONAL_ERROR: {type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001
            results["write"] = f"{type(exc).__name__}: {exc}"
        finally:
            connection.close()

    def test_combined_multi_table_drop_deadlocks_against_cross_table_writer(self):
        """(a) Characterization: same Finding H mechanism, AWS's table shape."""
        barrier_after_first = threading.Barrier(2, timeout=15)
        barrier_before_second = threading.Barrier(2, timeout=15)
        results = {}

        t_drop = threading.Thread(
            target=self._drop_combined_cross_order, args=(results, barrier_after_first, barrier_before_second)
        )
        t_write = threading.Thread(
            target=self._cross_table_writer, args=(results, barrier_after_first, barrier_before_second)
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
                f"[SPIKE INCONCLUSIVE] Expected a genuine Postgres deadlock, got: {results}. Rerun, "
                "or verify with pg_locks that both ACCESS EXCLUSIVE locks were held concurrently."
            )

    # ---- (b) fix verification: per-table loop does not deadlock --------------------------

    def _drop_per_table_loop(self, results, barrier_after_first, barrier_before_second):
        """Mirrors the fixed AWS/Azure/GCP code: one execute_delete_sql call (and therefore one
        transaction) per table, matching the loop now in purge_expired_report_data_by_date.
        """
        try:
            self._drop_table(TABLE_A)
            barrier_after_first.wait(timeout=15)
            barrier_before_second.wait(timeout=15)
            self._drop_table(TABLE_B)
            results["drop"] = "ok"
        except OperationalError as exc:
            results["drop"] = f"DEADLOCK/OPERATIONAL_ERROR: {type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001
            results["drop"] = f"{type(exc).__name__}: {exc}"
        finally:
            connection.close()

    def test_fixed_per_table_drop_does_not_deadlock_against_cross_table_writer(self):
        """(b) Fix verification: with the drop split per table, the same adversarial writer
        completes cleanly (it may still wait briefly on a single table, but that cannot cycle).
        """
        barrier_after_first = threading.Barrier(2, timeout=15)
        barrier_before_second = threading.Barrier(2, timeout=15)
        results = {}

        t_drop = threading.Thread(
            target=self._drop_per_table_loop, args=(results, barrier_after_first, barrier_before_second)
        )
        t_write = threading.Thread(
            target=self._cross_table_writer, args=(results, barrier_after_first, barrier_before_second)
        )
        t_drop.start()
        t_write.start()
        t_drop.join(timeout=25)
        t_write.join(timeout=25)

        self.assertIsNotNone(results.get("drop"), "partition-drop thread did not complete")
        self.assertIsNotNone(results.get("write"), "cross-table writer thread did not complete")

        deadlocked = any(v and str(v).startswith("DEADLOCK") for v in results.values())
        if deadlocked:
            self.fail(f"Per-table partition drop still deadlocked against a cross-table writer: {results}.")

        self.assertEqual(results["drop"], "ok", f"partition-drop thread failed: {results['drop']}")
        self.assertEqual(results["write"], "ok", f"cross-table writer thread failed: {results['write']}")
