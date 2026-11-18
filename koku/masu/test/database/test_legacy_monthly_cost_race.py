#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Overlapping legacy (non-RTU) monthly-cost writes for one provider must not double rows (COST-8575).

populate_monthly_cost_sql deletes the window's monthly-cost rows from the daily summary and inserts
new ones as two separate, autocommitted statements. update_cost_model_costs runs for the same
provider with different, overlapping windows can run concurrently (WorkerCache keys on the dates).
If one run's insert lands after the other run's delete, both runs' rows survive: without a lock this
test leaves 6 Cluster rows instead of 3 and doubles the cost.

Both runs here go through the provider-month lock that update_cost_model_costs takes under the
single-flight flag. Run A pauses between its delete and its insert; run B, overlapping, cannot get
the lock and writes nothing (the task hands such a run to the delayed tasks).
"""
import threading
import uuid
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import django.test
from django.conf import settings
from django.db import connection
from django.db.models import Sum
from django_tenants.utils import schema_context

from api.iam.models import Customer
from api.provider.models import Provider
from koku.test_provider_delete_cascade import create_test_provider
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.processor.cost_model_run_lock import billing_months
from masu.processor.cost_model_run_lock import provider_month_locks
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OCPUsageReportPeriod

COST_TYPE = "Cluster"


class LegacyMonthlyCostRaceTest(django.test.TransactionTestCase):
    """populate_monthly_cost_sql (use_rtu=False) for overlapping windows of one provider."""

    def _fixture_teardown(self):
        """Skip the TRUNCATE flush: the django-tenants FK graph breaks it. tearDown cleans up."""

    def setUp(self):
        from koku.koku_test_runner import KokuTestRunner

        self.schema = KokuTestRunner.schema
        customer = Customer.objects.filter(schema_name=self.schema).first()
        self.assertIsNotNone(customer)
        self.provider = Provider(
            uuid=uuid.uuid4(),
            name=f"legacy-monthly-race-{uuid.uuid4().hex[:8]}",
            type=Provider.PROVIDER_OCP,
            setup_complete=False,
            active=True,
            customer=customer,
        )
        self.provider.save()
        create_test_provider(self.schema, self.provider)

        period_start = datetime(2026, 6, 1, tzinfo=settings.UTC)
        self.day = period_start.date()
        with schema_context(self.schema):
            self.report_period = OCPUsageReportPeriod.objects.create(
                cluster_id=f"legacy-monthly-race-{uuid.uuid4().hex[:8]}",
                report_period_start=period_start,
                report_period_end=datetime(2026, 7, 1, tzinfo=settings.UTC),
                provider_id=self.provider.uuid,
            )
            for offset in range(3):
                usage_day = self.day + timedelta(days=offset)
                OCPUsageLineItemDailySummary.objects.create(
                    uuid=uuid.uuid4(),
                    report_period=self.report_period,
                    cluster_id=self.report_period.cluster_id,
                    source_uuid=self.provider.uuid,
                    namespace="legacy-monthly-race-ns",
                    node="legacy-monthly-race-node",
                    resource_id="legacy-monthly-race-node-id",
                    data_source="Pod",
                    usage_start=usage_day,
                    usage_end=usage_day,
                    pod_effective_usage_cpu_core_hours=Decimal("4.0"),
                    pod_usage_cpu_core_hours=Decimal("4.0"),
                    pod_request_cpu_core_hours=Decimal("4.0"),
                    pod_effective_usage_memory_gigabyte_hours=Decimal("8.0"),
                    node_capacity_cpu_cores=Decimal("8"),
                    node_capacity_cpu_core_hours=Decimal("192"),
                    node_capacity_memory_gigabyte_hours=Decimal("384"),
                    cluster_capacity_cpu_core_hours=Decimal("192"),
                    cluster_capacity_memory_gigabyte_hours=Decimal("384"),
                )

    def tearDown(self):
        with schema_context(self.schema):
            OCPUsageLineItemDailySummary.objects.filter(report_period_id=self.report_period.id).delete()
            OCPUsageReportPeriod.objects.filter(pk=self.report_period.pk).delete()
        with patch("masu.celery.tasks.delete_archived_data.delay", lambda *args, **kwargs: None):
            self.provider.delete()

    def _write(self, start, end, accessor=None):
        with schema_context(self.schema):
            (accessor or OCPReportDBAccessor(self.schema)).populate_monthly_cost_sql(
                COST_TYPE,
                "cluster_cost_per_month",
                Decimal("1000"),
                start,
                end,
                "cpu",
                str(self.provider.uuid),
                use_rtu=False,
            )

    def _monthly_rows(self):
        """(rows, distinct days, total cost model cost) of the window's monthly-cost rows."""
        with schema_context(self.schema):
            rows = OCPUsageLineItemDailySummary.objects.filter(
                report_period_id=self.report_period.id, monthly_cost_type=COST_TYPE
            )
            totals = rows.aggregate(
                cpu=Sum("cost_model_cpu_cost"),
                memory=Sum("cost_model_memory_cost"),
                volume=Sum("cost_model_volume_cost"),
            )
            cost = sum((value or Decimal("0")) for value in totals.values())
            return rows.count(), rows.values_list("usage_start", flat=True).distinct().count(), round(cost, 6)

    def _locked_write(self, start, end, accessor=None, wait_seconds=0):
        """Write the window like update_cost_model_costs under single-flight; return whether it ran."""
        with provider_month_locks(
            str(self.provider.uuid), billing_months(start, end), wait_seconds=wait_seconds, poll_seconds=0.05
        ) as acquired:
            if acquired:
                self._write(start, end, accessor=accessor)
            return acquired

    def test_overlapping_windows_do_not_double_monthly_cost_rows(self):
        self._write(self.day, self.day + timedelta(days=2))
        single_run_rows = self._monthly_rows()
        self.assertGreater(single_run_rows[0], 0)

        a_deleted, release_a = threading.Event(), threading.Event()
        errors, ran = [], {}

        def run_a():
            try:
                with schema_context(self.schema):
                    accessor = OCPReportDBAccessor(self.schema)
                    delete = accessor._delete_monthly_cost_model_data

                    def delete_then_pause(*args, **kwargs):
                        delete(*args, **kwargs)
                        a_deleted.set()
                        release_a.wait(15)

                    with patch.object(accessor, "_delete_monthly_cost_model_data", side_effect=delete_then_pause):
                        ran["a"] = self._locked_write(self.day, self.day + timedelta(days=2), accessor=accessor)
            except Exception as error:  # surfaced through `errors` below
                errors.append(error)
            finally:
                a_deleted.set()
                connection.close()

        def run_b():
            try:
                ran["b"] = self._locked_write(
                    self.day + timedelta(days=1), self.day + timedelta(days=2), wait_seconds=1
                )
            except Exception as error:  # surfaced through `errors` below
                errors.append(error)
            finally:
                connection.close()

        thread_a = threading.Thread(target=run_a)
        thread_a.start()
        self.assertTrue(a_deleted.wait(15))
        thread_b = threading.Thread(target=run_b)
        thread_b.start()
        thread_b.join(5)
        release_a.set()
        thread_a.join(30)
        thread_b.join(30)

        self.assertEqual(errors, [])
        self.assertEqual(ran, {"a": True, "b": False}, "run B must not write while run A holds the provider month")
        self.assertEqual(self._monthly_rows(), single_run_rows, "overlapping runs left both runs' monthly-cost rows")

        # Once run A is done, the provider month is free again and a later run writes normally.
        self.assertTrue(self._locked_write(self.day, self.day + timedelta(days=2)))
        self.assertEqual(self._monthly_rows(), single_run_rows)
