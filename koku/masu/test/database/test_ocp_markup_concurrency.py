#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test concurrent populate_markup_cost does not deadlock (COST-7995)."""
import threading
import uuid
from datetime import date
from decimal import Decimal

import django.test
from django.db import connection
from django_tenants.utils import tenant_context

from api.iam.models import Customer
from api.iam.models import User
from api.models import Tenant
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary


class PopulateMarkupCostConcurrencyTest(django.test.TransactionTestCase):
    """Verify that concurrent populate_markup_cost calls serialize via advisory lock."""

    def _fixture_teardown(self):
        """Skip TRUNCATE flush — django-tenants FK graph breaks TransactionTestCase flush."""

    def setUp(self):
        from koku.koku_test_runner import KokuTestRunner

        self.schema = KokuTestRunner.schema
        self.tenant = Tenant.objects.get(schema_name=self.schema)
        self.cluster_id = f"deadlock-test-{uuid.uuid4().hex[:8]}"
        self.start_date = date(2026, 6, 1)
        self.end_date = date(2026, 6, 30)

        with tenant_context(self.tenant):
            for day in range(1, 11):
                OCPUsageLineItemDailySummary.objects.create(
                    uuid=uuid.uuid4(),
                    cluster_id=self.cluster_id,
                    usage_start=date(2026, 6, day),
                    usage_end=date(2026, 6, day),
                    infrastructure_raw_cost=Decimal("100.00"),
                    infrastructure_project_raw_cost=Decimal("50.00"),
                    data_source="Pod",
                )

    def tearDown(self):
        with tenant_context(self.tenant):
            OCPUsageLineItemDailySummary.objects.filter(cluster_id=self.cluster_id).delete()

    def test_concurrent_markup_no_deadlock(self):
        """Two threads updating markup for the same cluster serialize without deadlock."""
        barrier = threading.Barrier(2, timeout=10)
        results = [None, None]

        def run_markup(index, markup_value):
            try:
                barrier.wait()
                with tenant_context(self.tenant):
                    accessor = OCPReportDBAccessor(schema=self.schema)
                    accessor.populate_markup_cost(
                        Decimal(markup_value), self.start_date, self.end_date, self.cluster_id
                    )
                results[index] = "ok"
            except Exception as exc:
                results[index] = f"{type(exc).__name__}: {exc}"
            finally:
                connection.close()

        t1 = threading.Thread(target=run_markup, args=(0, "0.10"))
        t2 = threading.Thread(target=run_markup, args=(1, "0.20"))
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        self.assertEqual(results[0], "ok", f"Thread 1 failed: {results[0]}")
        self.assertEqual(results[1], "ok", f"Thread 2 failed: {results[1]}")

        with tenant_context(self.tenant):
            rows = OCPUsageLineItemDailySummary.objects.filter(cluster_id=self.cluster_id)
            for row in rows:
                self.assertIsNotNone(row.infrastructure_markup_cost)
