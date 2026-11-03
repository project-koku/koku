#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests that deleting rates, price lists and cost models schedules the RTU cleanup task after commit."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.db import transaction
from django.urls import reverse
from django_tenants.utils import tenant_context
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.metrics import constants as metric_constants
from api.provider.models import Provider
from cost_models.cost_model_manager import CostModelManager
from cost_models.models import PriceList
from cost_models.models import Rate
from cost_models.price_list_manager import PriceListManager
from cost_models.rate_sync import sync_rate_table

TASK = "masu.processor.tasks.delete_rates_to_usage_rows"


class RatesToUsageCleanupScheduleTest(IamTestCase):
    """The API never deletes rates_to_usage rows itself; it schedules delete_rates_to_usage_rows."""

    def _price_list_with_rates(self, n=2):
        price_list = PriceList.objects.create(
            name="rtu-cleanup prices",
            currency="USD",
            effective_start_date=date(2026, 1, 1),
            effective_end_date=date(2099, 12, 31),
            rates=[],
        )
        rates = [
            Rate.objects.create(
                price_list=price_list,
                custom_name=f"rtu-cleanup rate {i}",
                metric=metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR,
                metric_type="cpu",
                cost_type="Infrastructure",
                default_rate=Decimal("0.01"),
            )
            for i in range(n)
        ]
        return price_list, rates

    def _kwargs(self, mock_task):
        mock_task.apply_async.assert_called_once()
        call = mock_task.apply_async.call_args
        self.assertEqual(call.kwargs["args"], [self.schema_name])
        return call.kwargs["kwargs"]

    @patch(TASK)
    def test_sync_rate_table_schedules_deleted_rates(self, mock_task):
        """Removing rates in sync_rate_table schedules exactly those rate IDs."""
        with tenant_context(self.tenant):
            price_list, rates = self._price_list_with_rates()
            kept = {"rate_id": str(rates[0].uuid), "metric": {"name": rates[0].metric}, "cost_type": "Infrastructure"}
            kept["tiered_rates"] = [{"unit": "USD", "value": 0.01}]
            with self.captureOnCommitCallbacks(execute=True):
                sync_rate_table(price_list, [kept])
        self.assertEqual(self._kwargs(mock_task), {"rate_ids": [str(rates[1].uuid)], "cost_model_ids": []})

    @patch(TASK)
    def test_sync_rate_table_without_deletes_schedules_nothing(self, mock_task):
        """Updating or adding rates never schedules a cleanup."""
        with tenant_context(self.tenant):
            price_list, _ = self._price_list_with_rates(n=0)
            new_rate = {
                "metric": {"name": metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR},
                "cost_type": "Infrastructure",
                "tiered_rates": [{"unit": "USD", "value": 0.01}],
            }
            with self.captureOnCommitCallbacks(execute=True):
                sync_rate_table(price_list, [new_rate])
        mock_task.apply_async.assert_not_called()

    @patch(TASK)
    def test_rolled_back_delete_schedules_nothing(self, mock_task):
        """A cleanup is scheduled only when the delete commits."""
        with tenant_context(self.tenant):
            price_list, _ = self._price_list_with_rates()
            with self.captureOnCommitCallbacks(execute=True):
                try:
                    with transaction.atomic():
                        sync_rate_table(price_list, [])
                        raise RuntimeError("roll back")
                except RuntimeError:
                    pass
        mock_task.apply_async.assert_not_called()

    @patch(TASK)
    def test_price_list_delete_schedules_its_rates(self, mock_task):
        """Deleting an unassigned price list schedules all of its rate IDs."""
        with tenant_context(self.tenant):
            price_list, rates = self._price_list_with_rates()
            with self.captureOnCommitCallbacks(execute=True):
                PriceListManager(price_list.uuid).delete()
        kwargs = self._kwargs(mock_task)
        self.assertEqual(sorted(kwargs["rate_ids"]), sorted(str(r.uuid) for r in rates))
        self.assertEqual(kwargs["cost_model_ids"], [])

    @patch(TASK)
    @patch("cost_models.cost_model_manager.delayed_update_cost_model_costs")
    def test_cost_model_delete_schedules_cost_model(self, _, mock_task):
        """DELETE /cost-models/<uuid>/ schedules that cost model's ID."""
        with tenant_context(self.tenant):
            cost_model = CostModelManager().create(
                name="rtu-cleanup cost model", description="", source_type=Provider.PROVIDER_OCP, rates=[]
            )
        url = reverse("cost-models-detail", kwargs={"uuid": cost_model.uuid})
        with self.captureOnCommitCallbacks(execute=True):
            response = APIClient().delete(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self._kwargs(mock_task), {"rate_ids": [], "cost_model_ids": [str(cost_model.uuid)]})
