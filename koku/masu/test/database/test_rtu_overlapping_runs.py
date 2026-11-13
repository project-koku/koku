#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Overlapping RTU writes for one provider must not double rows (work log item 4, COST-8575).

Each rates_to_usage writer deletes its window, then inserts. WorkerCache's key includes the dates,
so update_cost_model_costs runs for the same provider with different, overlapping windows can run
concurrently. Under READ COMMITTED, run B's DELETE does not see run A's uncommitted inserts, so
both runs' rows survive for the overlapping days and the aggregation into the daily summary counts
them twice.

update_cost_model_costs holds the provider-month lock for the whole run (single-flight), so the
writers take no lock of their own. Both runs here go through that lock: run A keeps its write in
flight; run B, overlapping, cannot get the lock and writes nothing (the task hands such a run to
the delayed tasks).
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
from django.db import transaction
from django_tenants.utils import schema_context

from api.iam.models import Customer
from api.provider.models import Provider
from cost_models.models import CostModelMap
from koku.test_provider_delete_cascade import create_test_provider
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.processor.cost_model_run_lock import billing_months
from masu.processor.cost_model_run_lock import provider_month_locks
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting.provider.ocp.models import RatesToUsage


class RatesToUsageOverlappingRunsTest(django.test.TransactionTestCase):
    """populate_usage_rates_to_usage runs of overlapping windows of one provider run one at a time."""

    def _fixture_teardown(self):
        """Skip the TRUNCATE flush: the django-tenants FK graph breaks it. tearDown cleans up."""

    def setUp(self):
        from koku.koku_test_runner import KokuTestRunner

        self.schema = KokuTestRunner.schema
        customer = Customer.objects.filter(schema_name=self.schema).first()
        self.assertIsNotNone(customer)
        self.provider = Provider(
            uuid=uuid.uuid4(),
            name=f"rtu-overlap-{uuid.uuid4().hex[:8]}",
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
                cluster_id=f"rtu-overlap-{uuid.uuid4().hex[:8]}",
                report_period_start=period_start,
                report_period_end=datetime(2026, 7, 1, tzinfo=settings.UTC),
                provider_id=self.provider.uuid,
            )
            cost_model_map = CostModelMap.objects.exclude(cost_model__isnull=True).first()
            self.assertIsNotNone(cost_model_map)
            self.cost_model_id = cost_model_map.cost_model_id
            OCPUsageLineItemDailySummary.objects.create(
                uuid=uuid.uuid4(),
                report_period=self.report_period,
                cluster_id=self.report_period.cluster_id,
                source_uuid=self.provider.uuid,
                namespace="rtu-overlap-ns",
                node="rtu-overlap-node",
                data_source="Pod",
                usage_start=self.day,
                usage_end=self.day,
                pod_effective_usage_cpu_core_hours=Decimal("4.0"),
                pod_usage_cpu_core_hours=Decimal("4.0"),
                pod_request_cpu_core_hours=Decimal("4.0"),
                node_capacity_cpu_cores=Decimal("8"),
                node_capacity_cpu_core_hours=Decimal("192"),
                cluster_capacity_cpu_core_hours=Decimal("768"),
            )

    def tearDown(self):
        with schema_context(self.schema):
            RatesToUsage.objects.filter(report_period_id=self.report_period.id).delete()
            OCPUsageLineItemDailySummary.objects.filter(report_period_id=self.report_period.id).delete()
            OCPUsageReportPeriod.objects.filter(pk=self.report_period.pk).delete()
        with patch("masu.celery.tasks.delete_archived_data.delay", lambda *args, **kwargs: None):
            self.provider.delete()

    def _write(self, start, end, accessor=None):
        with schema_context(self.schema):
            (accessor or OCPReportDBAccessor(self.schema)).populate_usage_rates_to_usage(
                start, end, self.provider.uuid, self.report_period.id, self.cost_model_id
            )

    def _locked_write(self, start, end, accessor=None, wait_seconds=0):
        """Write the window as update_cost_model_costs does, under the provider-month lock; return whether it ran."""
        with provider_month_locks(
            str(self.provider.uuid), billing_months(start, end), wait_seconds=wait_seconds, poll_seconds=0.05
        ) as acquired:
            if acquired:
                self._write(start, end, accessor=accessor)
            return acquired

    def _rows(self):
        with schema_context(self.schema):
            return RatesToUsage.objects.filter(report_period_id=self.report_period.id).count()

    def test_overlapping_windows_do_not_double_rows(self):
        self._write(self.day, self.day + timedelta(days=2))
        single_run_rows = self._rows()
        self.assertGreater(single_run_rows, 0)

        a_written, release_a = threading.Event(), threading.Event()
        errors, ran = [], {}

        def run_a():
            try:
                with schema_context(self.schema):
                    accessor = OCPReportDBAccessor(self.schema)
                    execute = accessor._prepare_and_execute_raw_sql_query

                    def in_flight(*args, **kwargs):
                        with transaction.atomic():
                            result = execute(*args, **kwargs)
                            a_written.set()
                            release_a.wait(15)
                        return result

                    with patch.object(accessor, "_prepare_and_execute_raw_sql_query", side_effect=in_flight):
                        ran["a"] = self._locked_write(self.day, self.day, accessor=accessor)
            except Exception as error:  # surfaced through `errors` below
                errors.append(error)
            finally:
                a_written.set()
                connection.close()

        def run_b():
            try:
                ran["b"] = self._locked_write(self.day, self.day + timedelta(days=2), wait_seconds=1)
            except Exception as error:  # surfaced through `errors` below
                errors.append(error)
            finally:
                connection.close()

        thread_a = threading.Thread(target=run_a)
        thread_a.start()
        self.assertTrue(a_written.wait(15))
        thread_b = threading.Thread(target=run_b)
        thread_b.start()
        thread_b.join(5)
        release_a.set()
        thread_a.join(30)
        thread_b.join(30)

        self.assertEqual(errors, [])
        self.assertEqual(ran, {"a": True, "b": False}, "run B must not write while run A holds the provider month")
        self.assertEqual(self._rows(), single_run_rows, "overlapping runs left both runs' rows")

        # Once run A is done, the provider month is free again and a later run writes normally.
        self.assertTrue(self._locked_write(self.day, self.day + timedelta(days=2)))
        self.assertEqual(self._rows(), single_run_rows)
