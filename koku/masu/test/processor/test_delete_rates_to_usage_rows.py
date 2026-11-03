#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the delete_rates_to_usage_rows task (RTU cleanup after Rate / CostModel deletes)."""
from uuid import uuid4

from django_tenants.utils import tenant_context
from model_bakery import baker

from koku.pg_partition import PartitionHandlerMixin
from masu.processor.tasks import delete_rates_to_usage_rows
from masu.test import MasuTestCase
from reporting.provider.ocp.models import RatesToUsage


class DeleteRatesToUsageRowsTest(MasuTestCase):
    """rates_to_usage has no FK cascade to Rate or CostModel, so this task removes their rows."""

    def setUp(self):
        super().setUp()
        self.usage_starts = [self.dh.last_month_start.date(), self.dh.this_month_start.date()]
        with tenant_context(self.tenant):
            for usage_start in self.usage_starts:
                PartitionHandlerMixin()._handle_partitions(self.schema, ["rates_to_usage"], usage_start, usage_start)
        self.rate_a, self.rate_b = uuid4(), uuid4()
        self.cost_model_a, self.cost_model_b = uuid4(), uuid4()

    def _make_rows(self, rate_id, cost_model_id):
        with tenant_context(self.tenant):
            return [
                baker.make(
                    RatesToUsage,
                    rate_id=rate_id,
                    cost_model_id=cost_model_id,
                    source_uuid_id=self.ocp_provider_uuid,
                    usage_start=usage_start,
                    usage_end=usage_start,
                    cluster_id=self.ocp_cluster_id,
                    custom_name="rtu-cleanup-test",
                    metric_type="cpu",
                ).uuid
                for usage_start in self.usage_starts
            ]

    def _remaining(self, uuids):
        with tenant_context(self.tenant):
            return set(RatesToUsage.objects.filter(uuid__in=uuids).values_list("uuid", flat=True))

    def tearDown(self):
        with tenant_context(self.tenant):
            RatesToUsage.objects.filter(custom_name="rtu-cleanup-test").delete()
        super().tearDown()

    def test_deletes_rows_of_deleted_rates_in_every_month(self):
        """Rows of the given rates go in all months; rows of other rates stay."""
        rows_a = self._make_rows(self.rate_a, self.cost_model_a)
        rows_b = self._make_rows(self.rate_b, self.cost_model_a)

        deleted = delete_rates_to_usage_rows(self.schema, rate_ids=[str(self.rate_a)])

        self.assertEqual(deleted, len(rows_a))
        self.assertEqual(self._remaining(rows_a), set())
        self.assertEqual(self._remaining(rows_b), set(rows_b))

    def test_deletes_rows_of_deleted_cost_models(self):
        """Rows of the given cost model go, including rows of rates still present."""
        rows_a = self._make_rows(self.rate_a, self.cost_model_a)
        rows_b = self._make_rows(self.rate_b, self.cost_model_b)

        deleted = delete_rates_to_usage_rows(self.schema, cost_model_ids=[str(self.cost_model_a)])

        self.assertEqual(deleted, len(rows_a))
        self.assertEqual(self._remaining(rows_a), set())
        self.assertEqual(self._remaining(rows_b), set(rows_b))

    def test_no_ids_deletes_nothing(self):
        """Without IDs the task is a no-op and never runs an unscoped DELETE."""
        rows = self._make_rows(self.rate_a, self.cost_model_a)

        self.assertEqual(delete_rates_to_usage_rows(self.schema), 0)
        self.assertEqual(self._remaining(rows), set(rows))
