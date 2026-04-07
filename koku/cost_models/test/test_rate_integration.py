#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Integration tests for the Rate table round-trip through the full cost model stack."""
from decimal import Decimal
from unittest.mock import patch

from django_tenants.utils import tenant_context

from api.iam.models import Customer
from api.iam.models import User
from api.iam.test.iam_test_case import IamTestCase
from api.metrics import constants as metric_constants
from api.provider.models import Provider
from cost_models.cost_model_manager import CostModelManager
from cost_models.models import PriceListCostModelMap
from cost_models.models import Rate
from cost_models.serializers import CostModelSerializer


class RateIntegrationTest(IamTestCase):
    """Integration tests for the Rate table round-trip."""

    def setUp(self):
        super().setUp()
        self.customer = Customer.objects.get(
            account_id=self.customer_data["account_id"]
        )
        self.user = User.objects.get(username=self.user_data["username"])
        self.ocp_metric = metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR

    def _build_cost_model_data(self, rates=None):
        """Build valid cost model data."""
        if rates is None:
            rates = [
                {
                    "metric": {"name": self.ocp_metric},
                    "tiered_rates": [{"unit": "USD", "value": 0.22}],
                    "cost_type": "Infrastructure",
                }
            ]
        return {
            "name": "Integration Test CM",
            "description": "Test",
            "source_type": Provider.PROVIDER_OCP,
            "rates": rates,
            "currency": "USD",
        }

    @patch("cost_models.serializers.is_cost_model_writes_disabled", return_value=False)
    @patch("cost_models.cost_model_manager.update_cost_model_costs")
    def test_create_via_serializer_round_trip(self, mock_task, mock_flag):
        """Test full create round-trip: serializer -> manager -> Rate table -> API output."""
        with tenant_context(self.tenant):
            data = self._build_cost_model_data()
            serializer = CostModelSerializer(data=data, context=self.request_context)
            serializer.is_valid(raise_exception=True)
            cost_model = serializer.save()

            mapping = PriceListCostModelMap.objects.get(cost_model=cost_model)
            rate_rows = Rate.objects.filter(price_list=mapping.price_list)
            self.assertEqual(rate_rows.count(), 1)
            rate = rate_rows.first()
            self.assertEqual(rate.metric, self.ocp_metric)
            self.assertEqual(rate.metric_type, "cpu")
            self.assertEqual(rate.default_rate, Decimal("0.22"))

            cost_model.refresh_from_db()
            self.assertIn("rate_id", cost_model.rates[0])
            self.assertEqual(cost_model.rates[0]["rate_id"], str(rate.uuid))

    @patch("cost_models.serializers.is_cost_model_writes_disabled", return_value=False)
    @patch("cost_models.cost_model_manager.update_cost_model_costs")
    def test_update_via_serializer_preserves_uuid(self, mock_task, mock_flag):
        """Test that updating via serializer preserves Rate UUID stability."""
        with tenant_context(self.tenant):
            data = self._build_cost_model_data()
            serializer = CostModelSerializer(data=data, context=self.request_context)
            serializer.is_valid(raise_exception=True)
            cost_model = serializer.save()

            mapping = PriceListCostModelMap.objects.get(cost_model=cost_model)
            original_uuid = Rate.objects.get(price_list=mapping.price_list).uuid
            cost_model.refresh_from_db()

            update_data = self._build_cost_model_data(
                rates=[
                    {
                        "metric": {"name": self.ocp_metric},
                        "tiered_rates": [{"unit": "USD", "value": 0.50}],
                        "cost_type": "Infrastructure",
                        "rate_id": str(original_uuid),
                        "custom_name": "cpu_core_usage_per_hour-Infrastructure",
                    }
                ]
            )
            serializer = CostModelSerializer(
                instance=cost_model, data=update_data, context=self.request_context
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()

            rate = Rate.objects.get(price_list=mapping.price_list)
            self.assertEqual(rate.uuid, original_uuid)
            self.assertEqual(rate.default_rate, Decimal("0.50"))

    @patch("cost_models.serializers.is_cost_model_writes_disabled", return_value=False)
    @patch("cost_models.cost_model_manager.update_cost_model_costs")
    def test_to_representation_includes_rate_fields(self, mock_task, mock_flag):
        """Test that API output includes rate_id and custom_name."""
        with tenant_context(self.tenant):
            data = self._build_cost_model_data()
            serializer = CostModelSerializer(data=data, context=self.request_context)
            serializer.is_valid(raise_exception=True)
            cost_model = serializer.save()

            read_serializer = CostModelSerializer(
                instance=cost_model, context=self.request_context
            )
            output = read_serializer.data
            rates = output.get("rates", [])
            self.assertTrue(len(rates) > 0)
            self.assertIn("rate_id", rates[0])
            self.assertIn("custom_name", rates[0])

    @patch("cost_models.serializers.is_cost_model_writes_disabled", return_value=False)
    @patch("cost_models.cost_model_manager.update_cost_model_costs")
    def test_create_with_tag_rate_round_trip(self, mock_task, mock_flag):
        """Test full round-trip for tag-based rates."""
        with tenant_context(self.tenant):
            tag_values = [
                {
                    "tag_value": "web",
                    "value": "0.5",
                    "unit": "USD",
                    "default": False,
                    "description": "web tier",
                }
            ]
            data = self._build_cost_model_data(
                rates=[
                    {
                        "metric": {"name": self.ocp_metric},
                        "tag_rates": {"tag_key": "app", "tag_values": tag_values},
                        "cost_type": "Supplementary",
                    }
                ]
            )
            serializer = CostModelSerializer(data=data, context=self.request_context)
            serializer.is_valid(raise_exception=True)
            cost_model = serializer.save()

            mapping = PriceListCostModelMap.objects.get(cost_model=cost_model)
            rate = Rate.objects.get(price_list=mapping.price_list)
            self.assertEqual(rate.tag_key, "app")
            self.assertIsNone(rate.default_rate)

    @patch("cost_models.serializers.is_cost_model_writes_disabled", return_value=False)
    @patch("cost_models.cost_model_manager.update_cost_model_costs")
    def test_price_list_json_synced_with_rate_table(self, mock_task, mock_flag):
        """Test that PriceList.rates JSON and Rate table stay in sync."""
        with tenant_context(self.tenant):
            data = self._build_cost_model_data()
            serializer = CostModelSerializer(data=data, context=self.request_context)
            serializer.is_valid(raise_exception=True)
            cost_model = serializer.save()

            mapping = PriceListCostModelMap.objects.get(cost_model=cost_model)
            pl = mapping.price_list
            pl.refresh_from_db()

            rate = Rate.objects.get(price_list=pl)
            self.assertEqual(pl.rates[0]["rate_id"], str(rate.uuid))
            self.assertEqual(pl.rates[0]["custom_name"], rate.custom_name)

    @patch("cost_models.serializers.is_cost_model_writes_disabled", return_value=False)
    @patch("cost_models.cost_model_manager.update_cost_model_costs")
    def test_manager_create_update_delete_cycle(self, mock_task, mock_flag):
        """Test create -> add rate -> remove rate cycle at the manager level."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.ocp_metric},
                    "tiered_rates": [{"unit": "USD", "value": 0.22}],
                    "cost_type": "Infrastructure",
                }
            ]
            manager = CostModelManager()
            cm = manager.create(
                name="Cycle Test",
                description="Test",
                source_type=Provider.PROVIDER_OCP,
                rates=rates,
            )
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            self.assertEqual(
                Rate.objects.filter(price_list=mapping.price_list).count(), 1
            )

            manager2 = CostModelManager(cost_model_uuid=cm.uuid)
            manager2.update(
                rates=rates
                + [
                    {
                        "metric": {"name": "memory_gb_usage_per_hour"},
                        "tiered_rates": [{"unit": "USD", "value": 0.10}],
                        "cost_type": "Supplementary",
                    }
                ]
            )
            self.assertEqual(
                Rate.objects.filter(price_list=mapping.price_list).count(), 2
            )

            manager3 = CostModelManager(cost_model_uuid=cm.uuid)
            manager3.update(rates=[])
            self.assertEqual(
                Rate.objects.filter(price_list=mapping.price_list).count(), 0
            )
