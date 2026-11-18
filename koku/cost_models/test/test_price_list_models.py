"""Tests for the PriceList and PriceListCostModelMap models."""
import logging
from datetime import date

from django.db import IntegrityError
from django_tenants.utils import tenant_context

from cost_models.models import CostModel
from cost_models.models import PriceList
from cost_models.models import PriceListCostModelMap
from masu.test import MasuTestCase


class PriceListModelTest(MasuTestCase):
    """Test cases for the PriceList model."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        logging.disable(0)

    def setUp(self):
        super().setUp()
        with tenant_context(self.tenant):
            self.price_list = PriceList.objects.create(
                name="Test Price List",
                description="A test price list",
                currency="USD",
                effective_start_date=date(2026, 1, 1),
                effective_end_date=date(2026, 3, 31),
                rates=[
                    {
                        "metric": {"name": "cpu_core_usage_per_hour"},
                        "tiered_rates": [{"value": "1.00", "unit": "USD"}],
                        "cost_type": "Infrastructure",
                    }
                ],
            )

    def test_create_price_list(self):
        """Test creating a price list with all required fields."""
        with tenant_context(self.tenant):
            self.assertIsNotNone(self.price_list.uuid)
            self.assertEqual(self.price_list.name, "Test Price List")
            self.assertEqual(self.price_list.description, "A test price list")
            self.assertEqual(self.price_list.currency, "USD")
            self.assertEqual(self.price_list.effective_start_date, date(2026, 1, 1))
            self.assertEqual(self.price_list.effective_end_date, date(2026, 3, 31))
            self.assertTrue(self.price_list.enabled)
            self.assertEqual(self.price_list.version, 1)
            self.assertIsNotNone(self.price_list.created_timestamp)
            self.assertIsNotNone(self.price_list.updated_timestamp)

    def test_create_price_list_default_enabled(self):
        """Test that enabled defaults to True."""
        with tenant_context(self.tenant):
            pl = PriceList.objects.create(
                name="Enabled PL",
                description="Test",
                currency="USD",
                effective_start_date=date(2026, 4, 1),
                effective_end_date=date(2026, 6, 30),
                rates=[],
            )
            self.assertTrue(pl.enabled)

    def test_create_price_list_default_version(self):
        """Test that version defaults to 1."""
        with tenant_context(self.tenant):
            pl = PriceList.objects.create(
                name="Versioned PL",
                description="Test",
                currency="USD",
                effective_start_date=date(2026, 4, 1),
                effective_end_date=date(2026, 6, 30),
                rates=[],
            )
            self.assertEqual(pl.version, 1)

    def test_delete_price_list(self):
        """Test deleting a price list."""
        with tenant_context(self.tenant):
            uuid = self.price_list.uuid
            self.price_list.delete()
            self.assertFalse(PriceList.objects.filter(uuid=uuid).exists())


class PriceListCostModelMapModelTest(MasuTestCase):
    """Test cases for the PriceListCostModelMap model."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        logging.disable(0)

    def setUp(self):
        super().setUp()
        with tenant_context(self.tenant):
            self.cost_model = CostModel.objects.first()
            # Clean up any pre-existing maps (e.g. from data migration)
            PriceListCostModelMap.objects.filter(cost_model=self.cost_model).delete()
            self.price_list = PriceList.objects.create(
                name="Mapped PL",
                description="Test",
                currency="USD",
                effective_start_date=date(2026, 1, 1),
                effective_end_date=date(2026, 12, 31),
                rates=[],
            )

    def test_attach_price_list_to_cost_model(self):
        """Test attaching a price list to a cost model with a priority."""
        with tenant_context(self.tenant):
            mapping = PriceListCostModelMap.objects.create(
                price_list=self.price_list,
                cost_model=self.cost_model,
                priority=1,
            )
            self.assertEqual(mapping.priority, 1)
            self.assertEqual(mapping.price_list, self.price_list)
            self.assertEqual(mapping.cost_model, self.cost_model)

    def test_unique_price_list_cost_model_pair(self):
        """Test that the same price list cannot be attached to the same cost model twice."""
        with tenant_context(self.tenant):
            PriceListCostModelMap.objects.create(
                price_list=self.price_list,
                cost_model=self.cost_model,
                priority=1,
            )
            with self.assertRaises(IntegrityError):
                PriceListCostModelMap.objects.create(
                    price_list=self.price_list,
                    cost_model=self.cost_model,
                    priority=2,
                )

    def test_multiple_price_lists_per_cost_model(self):
        """Test attaching multiple price lists to one cost model with different priorities."""
        with tenant_context(self.tenant):
            pl2 = PriceList.objects.create(
                name="Second PL",
                description="Test",
                currency="USD",
                effective_start_date=date(2026, 4, 1),
                effective_end_date=date(2026, 6, 30),
                rates=[],
            )
            PriceListCostModelMap.objects.create(
                price_list=self.price_list,
                cost_model=self.cost_model,
                priority=1,
            )
            PriceListCostModelMap.objects.create(
                price_list=pl2,
                cost_model=self.cost_model,
                priority=2,
            )
            maps = PriceListCostModelMap.objects.filter(cost_model=self.cost_model)
            self.assertEqual(maps.count(), 2)
            # Ordering is by priority
            self.assertEqual(maps.first().priority, 1)
            self.assertEqual(maps.last().priority, 2)

    def test_cascade_delete_price_list(self):
        """Test that deleting a price list cascades to its cost model mappings."""
        with tenant_context(self.tenant):
            PriceListCostModelMap.objects.create(
                price_list=self.price_list,
                cost_model=self.cost_model,
                priority=1,
            )
            self.price_list.delete()
            self.assertEqual(PriceListCostModelMap.objects.filter(cost_model=self.cost_model).count(), 0)

    def test_cascade_delete_cost_model(self):
        """Test that deleting a cost model cascades to its price list mappings."""
        with tenant_context(self.tenant):
            PriceListCostModelMap.objects.create(
                price_list=self.price_list,
                cost_model=self.cost_model,
                priority=1,
            )
            self.cost_model.delete()
            self.assertEqual(PriceListCostModelMap.objects.filter(price_list=self.price_list).count(), 0)

    def test_price_list_different_priorities_in_different_cost_models(self):
        """Test that a price list can have different priorities in different cost models."""
        with tenant_context(self.tenant):
            cm2 = CostModel.objects.create(
                name="Second CM",
                description="Another cost model",
                source_type="OCP",
                rates={},
            )
            PriceListCostModelMap.objects.create(
                price_list=self.price_list,
                cost_model=self.cost_model,
                priority=1,
            )
            PriceListCostModelMap.objects.create(
                price_list=self.price_list,
                cost_model=cm2,
                priority=7,
            )
            map1 = PriceListCostModelMap.objects.get(price_list=self.price_list, cost_model=self.cost_model)
            map2 = PriceListCostModelMap.objects.get(price_list=self.price_list, cost_model=cm2)
            self.assertEqual(map1.priority, 1)
            self.assertEqual(map2.priority, 7)
