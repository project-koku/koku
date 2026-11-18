#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""A failing rate sync must roll back the whole price list or cost model update (work log item 2)."""
from datetime import date
from unittest.mock import patch

from django.urls import reverse
from django_tenants.utils import tenant_context
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.metrics import constants as metric_constants
from api.provider.models import Provider
from api.provider.serializers import ProviderSerializer
from cost_models.models import CostModel
from cost_models.models import CostModelMap
from cost_models.models import PriceList
from cost_models.models import PriceListCostModelMap
from cost_models.price_list_manager import PriceListManager
from cost_models.serializers import CostModelSerializer


def rate(value, cost_type="Infrastructure"):
    return {
        "metric": {"name": metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR},
        "cost_type": cost_type,
        "tiered_rates": [{"unit": "USD", "value": value}],
    }


class PriceListUpdateAtomicTest(IamTestCase):
    """PriceListManager.update saves the price list and syncs its Rate rows in one transaction."""

    def test_failed_sync_rolls_back_price_list_changes(self):
        with tenant_context(self.tenant):
            price_list = PriceListManager().create(
                name="atomic price list",
                currency="USD",
                effective_start_date=date(2026, 1, 1),
                effective_end_date=date(2099, 12, 31),
                rates=[rate(0.1)],
            )
            before = PriceList.objects.get(uuid=price_list.uuid)

            with patch("cost_models.price_list_manager.sync_rate_table", side_effect=RuntimeError("sync failed")):
                with self.assertRaises(RuntimeError):
                    PriceListManager(price_list.uuid).update(name="renamed", rates=[rate(0.5)])

            after = PriceList.objects.get(uuid=price_list.uuid)
            self.assertEqual(after.name, before.name)
            self.assertEqual(after.version, before.version)
            self.assertEqual(after.rates, before.rates)


class CostModelUpdateAtomicTest(IamTestCase):
    """A cost model PUT changes sources and rates together, or not at all."""

    def _provider(self, name):
        serializer = ProviderSerializer(
            data={
                "name": name,
                "type": Provider.PROVIDER_OCP.lower(),
                "authentication": {"credentials": {"cluster_id": self.fake.word()}},
                "billing_source": {},
            },
            context=self.request_context,
        )
        serializer.is_valid(raise_exception=True)
        return serializer.save()

    @patch("cost_models.cost_model_manager.delayed_update_cost_model_costs")
    def test_failed_rate_update_rolls_back_source_changes(self, mock_dispatch):
        old_provider = self._provider("atomic old source")
        new_provider = self._provider("atomic new source")
        data = {
            "name": "atomic cost model",
            "description": "",
            "source_type": Provider.PROVIDER_OCP,
            "source_uuids": [old_provider.uuid],
            "rates": [rate(0.1)],
            "currency": "USD",
        }
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=data, context=self.request_context)
            serializer.is_valid(raise_exception=True)
            cost_model = serializer.save()
        mock_dispatch.reset_mock()

        with tenant_context(self.tenant):
            rates_before = self._rates_of(cost_model)

        url = reverse("cost-models-detail", kwargs={"uuid": cost_model.uuid})
        body = {**data, "source_uuids": [new_provider.uuid], "rates": [rate(0.5)]}
        with patch("cost_models.cost_model_manager.sync_rate_table", side_effect=ValueError("sync failed")):
            with self.captureOnCommitCallbacks(execute=True):
                response = APIClient().put(url, body, format="json", **self.headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        with tenant_context(self.tenant):
            mapped = set(CostModelMap.objects.filter(cost_model=cost_model).values_list("provider_uuid", flat=True))
            self.assertEqual(self._rates_of(cost_model), rates_before)
        self.assertEqual(mapped, {old_provider.uuid})
        mock_dispatch.assert_not_called()

    @staticmethod
    def _rates_of(cost_model):
        """The cost model's rates JSON and the rates JSON of each price list linked to it."""
        cost_model = CostModel.objects.get(uuid=cost_model.uuid)
        linked = PriceListCostModelMap.objects.filter(cost_model=cost_model).order_by("priority")
        return cost_model.rates, [link.price_list.rates for link in linked]

    def _disabled_price_list(self):
        with tenant_context(self.tenant):
            return PriceListManager().create(
                name="atomic disabled price list",
                currency="USD",
                effective_start_date=date(2026, 1, 1),
                effective_end_date=date(2099, 12, 31),
                enabled=False,
                rates=[rate(0.1)],
            )

    @patch("cost_models.cost_model_manager.delayed_update_cost_model_costs")
    def test_failed_price_list_attachment_rolls_back_put(self, mock_dispatch):
        """A PUT whose price list cannot be attached leaves sources unchanged and recalculates nothing."""
        old_provider = self._provider("attach old source")
        new_provider = self._provider("attach new source")
        data = {
            "name": "attach cost model",
            "description": "",
            "source_type": Provider.PROVIDER_OCP,
            "source_uuids": [old_provider.uuid],
            "rates": [rate(0.1)],
            "currency": "USD",
        }
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=data, context=self.request_context)
            serializer.is_valid(raise_exception=True)
            cost_model = serializer.save()
        mock_dispatch.reset_mock()
        disabled = self._disabled_price_list()

        url = reverse("cost-models-detail", kwargs={"uuid": cost_model.uuid})
        body = {**data, "source_uuids": [new_provider.uuid], "price_list_uuids": [str(disabled.uuid)]}
        with self.captureOnCommitCallbacks(execute=True):
            response = APIClient().put(url, body, format="json", **self.headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        with tenant_context(self.tenant):
            mapped = set(CostModelMap.objects.filter(cost_model=cost_model).values_list("provider_uuid", flat=True))
        self.assertEqual(mapped, {old_provider.uuid})
        mock_dispatch.assert_not_called()

    @patch("cost_models.cost_model_manager.delayed_update_cost_model_costs")
    def test_failed_price_list_attachment_rolls_back_create(self, mock_dispatch):
        """A POST whose price list cannot be attached creates no cost model."""
        provider = self._provider("attach create source")
        disabled = self._disabled_price_list()
        body = {
            "name": "attach created cost model",
            "description": "",
            "source_type": Provider.PROVIDER_OCP,
            "source_uuids": [str(provider.uuid)],
            "price_list_uuids": [str(disabled.uuid)],
            "currency": "USD",
        }
        with self.captureOnCommitCallbacks(execute=True):
            response = APIClient().post(reverse("cost-models-list"), body, format="json", **self.headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        with tenant_context(self.tenant):
            self.assertFalse(CostModel.objects.filter(name="attach created cost model").exists())
        mock_dispatch.assert_not_called()
