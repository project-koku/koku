#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for _sync_rate_table in CostModelManager."""
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django_tenants.utils import tenant_context

from api.iam.models import Customer
from api.iam.models import User
from api.iam.test.iam_test_case import IamTestCase
from api.metrics import constants as metric_constants
from api.provider.models import Provider
from cost_models.cost_model_manager import CostModelManager
from cost_models.models import PriceListCostModelMap
from cost_models.models import Rate


class SyncRateTableTest(IamTestCase):
    """Tests for _sync_rate_table in CostModelManager."""

    def setUp(self):
        super().setUp()
        self.customer = Customer.objects.get(account_id=self.customer_data["account_id"])
        self.user = User.objects.get(username=self.user_data["username"])
        self.metric = metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR
        self.tiered_rates = [{"unit": "USD", "value": 0.22}]

    def _create_cost_model(self, rates):
        """Helper to create a cost model via manager."""
        data = {
            "name": "Test CM",
            "description": "Test",
            "source_type": Provider.PROVIDER_OCP,
            "rates": rates,
        }
        manager = CostModelManager()
        with patch("cost_models.cost_model_manager.update_cost_model_costs"):
            return manager.create(**data)

    def test_create_populates_rate_rows(self):
        """Test that create() with rates populates Rate table."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            pl = mapping.price_list
            rate_rows = Rate.objects.filter(price_list=pl)
            self.assertEqual(rate_rows.count(), 1)
            self.assertEqual(rate_rows.first().metric, self.metric)

    def test_create_sets_correct_metric_type(self):
        """Test that Rate rows get correct metric_type from derive_metric_type."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            rate = Rate.objects.get(price_list=mapping.price_list)
            self.assertEqual(rate.metric_type, "cpu")

    def test_create_sets_default_rate(self):
        """Test that Rate rows get correct default_rate from extract_default_rate."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            rate = Rate.objects.get(price_list=mapping.price_list)
            self.assertEqual(rate.default_rate, Decimal("0.22"))

    def test_create_sets_custom_name(self):
        """Test that Rate rows get a generated custom_name."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            rate = Rate.objects.get(price_list=mapping.price_list)
            self.assertEqual(rate.custom_name, "cpu_core_usage_per_hour-Infrastructure")

    def test_create_injects_rate_id_into_json(self):
        """Test that create() injects rate_id back into CostModel.rates JSON."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            cm.refresh_from_db()
            self.assertIn("rate_id", cm.rates[0])
            self.assertIn("custom_name", cm.rates[0])

    def test_create_injects_rate_id_into_price_list_json(self):
        """Test that create() also injects rate_id into PriceList.rates JSON."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            pl = mapping.price_list
            pl.refresh_from_db()
            self.assertIn("rate_id", pl.rates[0])

    def test_create_multiple_rates(self):
        """Test creating with multiple rates produces multiple Rate rows."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                },
                {
                    "metric": {"name": "memory_gb_usage_per_hour"},
                    "tiered_rates": [{"unit": "USD", "value": 0.10}],
                    "cost_type": "Supplementary",
                },
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            self.assertEqual(Rate.objects.filter(price_list=mapping.price_list).count(), 2)

    def test_create_tag_rate(self):
        """Test creating a tag-based rate populates Rate with tag_key and tag_values."""
        with tenant_context(self.tenant):
            tag_values = [{"tag_value": "web", "value": "0.5", "unit": "USD"}]
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tag_rates": {"tag_key": "app", "tag_values": tag_values},
                    "cost_type": "Supplementary",
                }
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            rate = Rate.objects.get(price_list=mapping.price_list)
            self.assertEqual(rate.tag_key, "app")
            self.assertEqual(rate.tag_values, tag_values)
            self.assertIsNone(rate.default_rate)

    def test_update_adds_new_rate_rows(self):
        """Test that updating rates adds new Rate rows."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            manager = CostModelManager(cost_model_uuid=cm.uuid)
            new_rates = rates + [
                {
                    "metric": {"name": "memory_gb_usage_per_hour"},
                    "tiered_rates": [{"unit": "USD", "value": 0.10}],
                    "cost_type": "Supplementary",
                }
            ]
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                manager.update(rates=new_rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            self.assertEqual(Rate.objects.filter(price_list=mapping.price_list).count(), 2)

    def test_update_removes_deleted_rate_rows(self):
        """Test that updating with fewer rates removes old Rate rows."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                },
                {
                    "metric": {"name": "memory_gb_usage_per_hour"},
                    "tiered_rates": [{"unit": "USD", "value": 0.10}],
                    "cost_type": "Supplementary",
                },
            ]
            cm = self._create_cost_model(rates)
            manager = CostModelManager(cost_model_uuid=cm.uuid)
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                manager.update(rates=[rates[0]])
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            self.assertEqual(Rate.objects.filter(price_list=mapping.price_list).count(), 1)

    def test_update_preserves_uuid_for_matching_rate(self):
        """Test that updating a rate that matches by custom_name preserves its UUID."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            original_uuid = Rate.objects.get(price_list=mapping.price_list).uuid

            cm.refresh_from_db()
            updated_rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": [{"unit": "USD", "value": 0.50}],
                    "cost_type": "Infrastructure",
                    "rate_id": str(original_uuid),
                    "custom_name": "cpu_core_usage_per_hour-Infrastructure",
                }
            ]
            manager = CostModelManager(cost_model_uuid=cm.uuid)
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                manager.update(rates=updated_rates)
            rate = Rate.objects.get(price_list=mapping.price_list)
            self.assertEqual(rate.uuid, original_uuid)
            self.assertEqual(rate.default_rate, Decimal("0.50"))

    def test_update_injects_rate_id_into_json(self):
        """Test that update() injects rate_id into CostModel.rates JSON."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            manager = CostModelManager(cost_model_uuid=cm.uuid)
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                manager.update(
                    rates=[
                        {
                            "metric": {"name": self.metric},
                            "tiered_rates": self.tiered_rates,
                            "cost_type": "Infrastructure",
                        }
                    ]
                )
            cm.refresh_from_db()
            self.assertIn("rate_id", cm.rates[0])

    def test_create_without_rates_creates_no_rate_rows(self):
        """Test that create() without rates does not create Rate rows."""
        with tenant_context(self.tenant):
            data = {
                "name": "Markup Only",
                "description": "Test",
                "source_type": Provider.PROVIDER_OCP,
                "rates": [],
            }
            manager = CostModelManager()
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                cm = manager.create(**data)
            self.assertFalse(PriceListCostModelMap.objects.filter(cost_model=cm).exists())

    def test_update_empty_rates_clears_rate_rows(self):
        """Test that updating with empty rates clears existing Rate rows."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            self.assertEqual(Rate.objects.filter(price_list=mapping.price_list).count(), 1)

            manager = CostModelManager(cost_model_uuid=cm.uuid)
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                manager.update(rates=[])
            self.assertEqual(Rate.objects.filter(price_list=mapping.price_list).count(), 0)

    def test_create_with_invalid_rate_id_raises_exception(self):
        """Test that an invalid rate_id string raises CostModelException."""
        from cost_models.cost_model_manager import CostModelException

        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                    "rate_id": "not-a-valid-uuid",
                }
            ]
            with self.assertRaises(CostModelException):
                self._create_cost_model(rates)

    def test_update_with_nonexistent_rate_id_raises_exception(self):
        """Test that a valid UUID not belonging to this price list raises CostModelException."""
        from cost_models.cost_model_manager import CostModelException

        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            manager = CostModelManager(cost_model_uuid=cm.uuid)
            fake_uuid = str(uuid4())
            updated_rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                    "rate_id": fake_uuid,
                }
            ]
            with self.assertRaises(CostModelException):
                with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                    manager.update(rates=updated_rates)

    def test_update_by_rate_id_preserves_uuid_across_rename(self):
        """Test that matching by rate_id preserves UUID even when custom_name changes."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                }
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            original_rate = Rate.objects.get(price_list=mapping.price_list)
            original_uuid = original_rate.uuid

            manager = CostModelManager(cost_model_uuid=cm.uuid)
            updated_rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": [{"unit": "USD", "value": 0.50}],
                    "cost_type": "Infrastructure",
                    "rate_id": str(original_uuid),
                    "custom_name": "renamed-rate",
                }
            ]
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                manager.update(rates=updated_rates)
            rate = Rate.objects.get(price_list=mapping.price_list)
            self.assertEqual(rate.uuid, original_uuid)
            self.assertEqual(rate.custom_name, "renamed-rate")
            self.assertEqual(rate.default_rate, Decimal("0.50"))

    def test_rate_id_takes_precedence_over_custom_name(self):
        """Test that rate_id matching wins over custom_name when both are provided."""
        with tenant_context(self.tenant):
            rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": self.tiered_rates,
                    "cost_type": "Infrastructure",
                },
                {
                    "metric": {"name": "memory_gb_usage_per_hour"},
                    "tiered_rates": [{"unit": "USD", "value": 0.10}],
                    "cost_type": "Supplementary",
                },
            ]
            cm = self._create_cost_model(rates)
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            rate_objs = list(Rate.objects.filter(price_list=mapping.price_list).order_by("custom_name"))
            cpu_rate = next(r for r in rate_objs if r.metric == self.metric)

            manager = CostModelManager(cost_model_uuid=cm.uuid)
            updated_rates = [
                {
                    "metric": {"name": self.metric},
                    "tiered_rates": [{"unit": "USD", "value": 0.99}],
                    "cost_type": "Infrastructure",
                    "rate_id": str(cpu_rate.uuid),
                    "custom_name": "wrong-name-but-rate-id-wins",
                },
                {
                    "metric": {"name": "memory_gb_usage_per_hour"},
                    "tiered_rates": [{"unit": "USD", "value": 0.10}],
                    "cost_type": "Supplementary",
                },
            ]
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                manager.update(rates=updated_rates)
            rate = Rate.objects.get(uuid=cpu_rate.uuid)
            self.assertEqual(rate.uuid, cpu_rate.uuid)
            self.assertEqual(rate.custom_name, "wrong-name-but-rate-id-wins")
