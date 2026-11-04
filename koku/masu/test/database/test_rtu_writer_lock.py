#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Overlapping RTU writes for the same provider must not double rows (work log item 4).

Each rates_to_usage writer deletes its window, then inserts. WorkerCache's single-flight key
includes start_date/end_date, so update_cost_model_costs runs for the same provider with
different, overlapping windows run concurrently. Under READ COMMITTED, run B's DELETE does not
see run A's uncommitted inserts, so both runs' rows survive for the overlapping days and the
aggregation into the daily summary counts them twice. _distribution_provider_lock already
serializes the distribution, markup and aggregation writers for this reason (#6162); every RTU
writer has to take it.

Run A executes the writer's SQL in a transaction that stays open (an in-flight statement),
inside the region the lock covers. Run B writes an overlapping window meanwhile.
"""
import inspect
import threading
import uuid
from contextlib import contextmanager
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
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting.provider.ocp.models import RatesToUsage


class RatesToUsageWriterLockTest(django.test.TransactionTestCase):
    """populate_usage_rates_to_usage runs overlapping windows of one provider one after the other."""

    def _fixture_teardown(self):
        """Skip the TRUNCATE flush: the django-tenants FK graph breaks it. tearDown cleans up."""

    def setUp(self):
        from koku.koku_test_runner import KokuTestRunner

        self.schema = KokuTestRunner.schema
        customer = Customer.objects.filter(schema_name=self.schema).first()
        self.assertIsNotNone(customer)
        self.provider = Provider(
            uuid=uuid.uuid4(),
            name=f"rtu-writer-lock-{uuid.uuid4().hex[:8]}",
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
                cluster_id=f"rtu-writer-lock-{uuid.uuid4().hex[:8]}",
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
                namespace="rtu-writer-lock-ns",
                node="rtu-writer-lock-node",
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

    def _write(self, start, end):
        with schema_context(self.schema):
            OCPReportDBAccessor(self.schema).populate_usage_rates_to_usage(
                start, end, self.provider.uuid, self.report_period.id, self.cost_model_id
            )

    def _rows(self):
        with schema_context(self.schema):
            return RatesToUsage.objects.filter(report_period_id=self.report_period.id).count()

    def test_overlapping_windows_do_not_double_rows(self):
        self._write(self.day, self.day + timedelta(days=2))
        single_run_rows = self._rows()
        self.assertGreater(single_run_rows, 0)
        with schema_context(self.schema):
            RatesToUsage.objects.filter(report_period_id=self.report_period.id).delete()

        a_written, release_a, b_done = threading.Event(), threading.Event(), threading.Event()
        errors = []

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
                        accessor.populate_usage_rates_to_usage(
                            self.day, self.day, self.provider.uuid, self.report_period.id, self.cost_model_id
                        )
            except Exception as error:  # surfaced through `errors` below
                errors.append(error)
            finally:
                a_written.set()
                connection.close()

        def run_b():
            try:
                self._write(self.day, self.day + timedelta(days=2))
            except Exception as error:  # surfaced through `errors` below
                errors.append(error)
            finally:
                b_done.set()
                connection.close()

        thread_a = threading.Thread(target=run_a)
        thread_a.start()
        self.assertTrue(a_written.wait(15))
        thread_b = threading.Thread(target=run_b)
        thread_b.start()
        b_finished_while_a_in_flight = b_done.wait(2)
        release_a.set()
        thread_a.join(30)
        thread_b.join(30)

        self.assertEqual(errors, [])
        self.assertEqual(self._rows(), single_run_rows, "overlapping runs left both runs' rows")
        self.assertFalse(b_finished_while_a_in_flight, "run B wrote while run A's write was still in flight")


class RatesToUsageWriterLockDecoratorTest(django.test.SimpleTestCase):
    """The decorator locks RTU writes only, keyed by the provider argument."""

    WRITERS = {
        "populate_monthly_cost_sql": "provider_uuid",
        "populate_tag_cost_sql": "provider_uuid",
        "populate_vm_usage_costs": "provider_uuid",
        "populate_usage_rates_to_usage": "provider_uuid",
        "populate_tag_usage_costs": "source_uuid",
        "populate_tag_usage_default_costs": "source_uuid",
        "populate_tag_based_costs": "provider_uuid",
    }

    @staticmethod
    def _writer():
        from masu.database.ocp_report_db_accessor import _rtu_writer_provider_lock

        class Writer:
            def __init__(self):
                self.locked_for = []

            @contextmanager
            def _distribution_provider_lock(self, provider):
                self.locked_for.append(provider)
                yield

            @_rtu_writer_provider_lock("provider_uuid")
            def write(self, start, provider_uuid, use_rtu=False):
                return (start, provider_uuid, use_rtu, list(self.locked_for))

        return Writer()

    def test_rtu_write_runs_under_the_provider_lock(self):
        self.assertEqual(self._writer().write("2026-06-01", "p1", use_rtu=True), ("2026-06-01", "p1", True, ["p1"]))

    def test_legacy_write_takes_no_lock(self):
        self.assertEqual(self._writer().write("2026-06-01", provider_uuid="p1"), ("2026-06-01", "p1", False, []))

    def test_every_rtu_writer_is_wrapped(self):
        for name, provider_param in self.WRITERS.items():
            with self.subTest(writer=name):
                method = getattr(OCPReportDBAccessor, name)
                self.assertTrue(hasattr(method, "__wrapped__"))
                self.assertIn(provider_param, inspect.signature(method.__wrapped__).parameters)
