"""Tests for the PriceListManager."""
import logging
from datetime import date
from unittest.mock import patch

from django_tenants.utils import tenant_context

from cost_models.models import CostModel
from cost_models.models import PriceList
from cost_models.models import PriceListCostModelMap
from cost_models.price_list_manager import PriceListException
from cost_models.price_list_manager import PriceListManager
from masu.test import MasuTestCase


class PriceListManagerCreateTest(MasuTestCase):
    """Test cases for PriceListManager.create."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        logging.disable(0)

    def test_create_price_list(self):
        """Test creating a price list with rates."""
        with tenant_context(self.tenant):
            manager = PriceListManager()
            rates = [
                {
                    "metric": {"name": "cpu_core_usage_per_hour"},
                    "tiered_rates": [{"value": "1.00", "unit": "USD"}],
                    "cost_type": "Infrastructure",
                }
            ]
            pl = manager.create(
                name="Test PL",
                description="A test",
                currency="USD",
                effective_start_date=date(2026, 1, 1),
                effective_end_date=date(2026, 3, 31),
                rates=rates,
            )
            self.assertEqual(pl.name, "Test PL")
            self.assertEqual(pl.version, 1)
            self.assertEqual(manager.instance, pl)
            self.assertEqual(pl.rates, rates)

    def test_create_price_list_missing_required_fields(self):
        """Test that creating a price list without required fields raises."""
        with tenant_context(self.tenant):
            manager = PriceListManager()
            with self.assertRaises(Exception):
                manager.create(
                    name="Incomplete PL",
                    effective_start_date=date(2026, 1, 1),
                    effective_end_date=date(2026, 3, 31),
                )


class PriceListManagerUpdateTest(MasuTestCase):
    """Test cases for PriceListManager.update."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        logging.disable(0)

    def setUp(self):
        super().setUp()
        with tenant_context(self.tenant):
            self.rates_v1 = [
                {
                    "metric": {"name": "cpu_core_usage_per_hour"},
                    "tiered_rates": [{"value": "1.00", "unit": "USD"}],
                    "cost_type": "Infrastructure",
                }
            ]
            manager = PriceListManager()
            self.price_list = manager.create(
                name="Updatable PL",
                description="Test",
                currency="USD",
                effective_start_date=date(2026, 1, 1),
                effective_end_date=date(2026, 12, 31),
                rates=self.rates_v1,
            )

    def test_update_name_does_not_increment_version(self):
        """Test that updating name does not increment version."""
        with tenant_context(self.tenant):
            manager = PriceListManager(self.price_list.uuid)
            manager.update(name="Renamed PL")
            self.assertEqual(manager.instance.name, "Renamed PL")
            self.assertEqual(manager.instance.version, 1)

    def test_update_description_does_not_increment_version(self):
        """Test that updating description does not increment version."""
        with tenant_context(self.tenant):
            manager = PriceListManager(self.price_list.uuid)
            manager.update(description="New description")
            self.assertEqual(manager.instance.description, "New description")
            self.assertEqual(manager.instance.version, 1)

    def test_update_rates_increments_version(self):
        """Test that updating rates increments version."""
        with tenant_context(self.tenant):
            manager = PriceListManager(self.price_list.uuid)
            rates_v2 = [
                {
                    "metric": {"name": "cpu_core_usage_per_hour"},
                    "tiered_rates": [{"value": "2.00", "unit": "USD"}],
                    "cost_type": "Infrastructure",
                }
            ]
            manager.update(rates=rates_v2)
            self.assertEqual(manager.instance.version, 2)
            self.assertEqual(manager.instance.rates, rates_v2)

    def test_update_same_rates_does_not_increment_version(self):
        """Test that updating with identical rates does not increment version."""
        with tenant_context(self.tenant):
            manager = PriceListManager(self.price_list.uuid)
            manager.update(rates=self.rates_v1)
            self.assertEqual(manager.instance.version, 1)

    def test_update_currency_increments_version(self):
        """Test that updating currency increments version."""
        with tenant_context(self.tenant):
            manager = PriceListManager(self.price_list.uuid)
            manager.update(currency="EUR")
            self.assertEqual(manager.instance.version, 2)

    def test_update_validity_period_increments_version(self):
        """Test that updating validity period increments version."""
        with tenant_context(self.tenant):
            manager = PriceListManager(self.price_list.uuid)
            manager.update(effective_end_date=date(2027, 12, 31))
            self.assertEqual(manager.instance.version, 2)

    def test_update_same_dates_does_not_increment_version(self):
        """Test that updating with identical dates does not increment version."""
        with tenant_context(self.tenant):
            manager = PriceListManager(self.price_list.uuid)
            manager.update(
                effective_start_date=date(2026, 1, 1),
                effective_end_date=date(2026, 12, 31),
            )
            self.assertEqual(manager.instance.version, 1)

    def test_update_enabled_does_not_increment_version(self):
        """Test that toggling enabled/disabled does not increment version."""
        with tenant_context(self.tenant):
            manager = PriceListManager(self.price_list.uuid)
            manager.update(enabled=False)
            self.assertEqual(manager.instance.version, 1)
            manager.update(enabled=True)
            self.assertEqual(manager.instance.version, 1)

    def test_update_disabled_price_list_name_ok(self):
        """Test that name can be updated on a disabled price list."""
        with tenant_context(self.tenant):
            manager = PriceListManager(self.price_list.uuid)
            manager.update(enabled=False)
            manager.update(name="Disabled Renamed")
            self.assertEqual(manager.instance.name, "Disabled Renamed")

    def test_update_disabled_price_list_rates_rejected(self):
        """Test that rates cannot be updated on a disabled price list."""
        with tenant_context(self.tenant):
            manager = PriceListManager(self.price_list.uuid)
            manager.update(enabled=False)
            with self.assertRaises(PriceListException):
                manager.update(
                    rates=[
                        {
                            "metric": {"name": "cpu"},
                            "tiered_rates": [{"value": "5.00", "unit": "USD"}],
                            "cost_type": "Infrastructure",
                        }
                    ]
                )

    def test_update_disabled_price_list_validity_rejected(self):
        """Test that validity period cannot be updated on a disabled price list."""
        with tenant_context(self.tenant):
            manager = PriceListManager(self.price_list.uuid)
            manager.update(enabled=False)
            with self.assertRaises(PriceListException):
                manager.update(effective_start_date=date(2026, 4, 1))

    def test_update_no_model_raises(self):
        """Test that updating without a model raises an exception."""
        with tenant_context(self.tenant):
            manager = PriceListManager()
            with self.assertRaises(PriceListException):
                manager.update(name="No model")


class PriceListManagerDeleteTest(MasuTestCase):
    """Test cases for PriceListManager.delete."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        logging.disable(0)

    def test_delete_unassigned_price_list(self):
        """Test deleting a price list that is not assigned to any cost model."""
        with tenant_context(self.tenant):
            manager = PriceListManager()
            pl = manager.create(
                name="Deletable PL",
                description="Test",
                currency="USD",
                effective_start_date=date(2026, 1, 1),
                effective_end_date=date(2026, 12, 31),
                rates=[],
            )
            pl_uuid = pl.uuid
            manager.delete()
            self.assertIsNone(manager.instance)
            self.assertFalse(PriceList.objects.filter(uuid=pl_uuid).exists())

    def test_delete_assigned_price_list_raises(self):
        """Test that deleting a price list assigned to a cost model raises an exception."""
        with tenant_context(self.tenant):
            manager = PriceListManager()
            pl = manager.create(
                name="Assigned PL",
                description="Test",
                currency="USD",
                effective_start_date=date(2026, 1, 1),
                effective_end_date=date(2026, 12, 31),
                rates=[],
            )
            cost_model = CostModel.objects.first()
            PriceListCostModelMap.objects.create(
                price_list=pl,
                cost_model=cost_model,
                priority=1,
            )
            with self.assertRaises(PriceListException):
                manager.delete()
            # Price list should still exist
            self.assertTrue(PriceList.objects.filter(uuid=pl.uuid).exists())

    def test_delete_no_model_raises(self):
        """Test that deleting without a model raises an exception."""
        with tenant_context(self.tenant):
            manager = PriceListManager()
            with self.assertRaises(PriceListException):
                manager.delete()


class PriceListManagerAttachTest(MasuTestCase):
    """Test cases for PriceListManager.attach_price_lists_to_cost_model."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        logging.disable(0)

    def setUp(self):
        super().setUp()
        with tenant_context(self.tenant):
            self.cost_model = CostModel.objects.first()
            manager1 = PriceListManager()
            self.pl1 = manager1.create(
                name="PL1",
                description="Test",
                currency="USD",
                effective_start_date=date(2026, 1, 1),
                effective_end_date=date(2026, 3, 31),
                rates=[],
            )
            manager2 = PriceListManager()
            self.pl2 = manager2.create(
                name="PL2",
                description="Test",
                currency="USD",
                effective_start_date=date(2026, 4, 1),
                effective_end_date=date(2026, 12, 31),
                rates=[],
            )

    def test_attach_price_lists(self):
        """Test attaching price lists to a cost model with priorities."""
        with tenant_context(self.tenant):
            PriceListManager.attach_price_lists_to_cost_model(self.cost_model.uuid, [self.pl1.uuid, self.pl2.uuid])
            maps = PriceListCostModelMap.objects.filter(cost_model=self.cost_model).order_by("priority")
            self.assertEqual(maps.count(), 2)
            self.assertEqual(maps[0].price_list, self.pl1)
            self.assertEqual(maps[0].priority, 1)
            self.assertEqual(maps[1].price_list, self.pl2)
            self.assertEqual(maps[1].priority, 2)

    def test_reattach_replaces_existing(self):
        """Test that reattaching replaces existing mappings."""
        with tenant_context(self.tenant):
            PriceListManager.attach_price_lists_to_cost_model(self.cost_model.uuid, [self.pl1.uuid, self.pl2.uuid])
            # Reattach with reversed order
            PriceListManager.attach_price_lists_to_cost_model(self.cost_model.uuid, [self.pl2.uuid, self.pl1.uuid])
            maps = PriceListCostModelMap.objects.filter(cost_model=self.cost_model).order_by("priority")
            self.assertEqual(maps.count(), 2)
            self.assertEqual(maps[0].price_list, self.pl2)
            self.assertEqual(maps[0].priority, 1)

    def test_attach_empty_list_detaches_all(self):
        """Test that attaching an empty list removes all mappings."""
        with tenant_context(self.tenant):
            PriceListManager.attach_price_lists_to_cost_model(self.cost_model.uuid, [self.pl1.uuid])
            PriceListManager.attach_price_lists_to_cost_model(self.cost_model.uuid, [])
            maps = PriceListCostModelMap.objects.filter(cost_model=self.cost_model)
            self.assertEqual(maps.count(), 0)

    def test_attach_nonexistent_cost_model_raises(self):
        """Test that attaching to a nonexistent cost model raises."""
        with tenant_context(self.tenant):
            with self.assertRaises(PriceListException):
                PriceListManager.attach_price_lists_to_cost_model(
                    "00000000-0000-0000-0000-000000000000", [self.pl1.uuid]
                )

    def test_attach_nonexistent_price_list_raises(self):
        """Test that attaching a nonexistent price list raises."""
        with tenant_context(self.tenant):
            with self.assertRaises(PriceListException):
                PriceListManager.attach_price_lists_to_cost_model(
                    self.cost_model.uuid, ["00000000-0000-0000-0000-000000000000"]
                )

    def test_attach_disabled_price_list_raises(self):
        """Test that attaching a disabled price list raises."""
        with tenant_context(self.tenant):
            manager = PriceListManager(self.pl1.uuid)
            manager.update(enabled=False)
            with self.assertRaises(PriceListException):
                PriceListManager.attach_price_lists_to_cost_model(self.cost_model.uuid, [self.pl1.uuid])


class PriceListManagerQueryTest(MasuTestCase):
    """Test cases for PriceListManager query methods."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        logging.disable(0)

    def setUp(self):
        super().setUp()
        with tenant_context(self.tenant):
            self.cost_model = CostModel.objects.first()
            manager1 = PriceListManager()
            self.pl_q1 = manager1.create(
                name="Q1 Prices",
                description="Test",
                currency="USD",
                effective_start_date=date(2026, 1, 1),
                effective_end_date=date(2026, 3, 31),
                rates=[],
            )
            manager2 = PriceListManager()
            self.pl_year = manager2.create(
                name="Year Fallback",
                description="Test",
                currency="USD",
                effective_start_date=date(2026, 1, 1),
                effective_end_date=date(2026, 12, 31),
                rates=[],
            )
            PriceListManager.attach_price_lists_to_cost_model(
                self.cost_model.uuid, [self.pl_q1.uuid, self.pl_year.uuid]
            )

    def test_get_cost_model_price_lists(self):
        """Test getting price lists for a cost model."""
        with tenant_context(self.tenant):
            result = PriceListManager.get_cost_model_price_lists(self.cost_model.uuid)
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]["price_list"], self.pl_q1)
            self.assertEqual(result[0]["priority"], 1)
            self.assertEqual(result[1]["price_list"], self.pl_year)
            self.assertEqual(result[1]["priority"], 2)

    def test_get_effective_price_list_priority_wins(self):
        """Test that the highest priority (lowest number) price list is returned for overlapping dates."""
        with tenant_context(self.tenant):
            # Feb 15 is within both Q1 (Jan-Mar) and Year (Jan-Dec)
            # Q1 is priority 1, Year is priority 2 — Q1 should win
            result = PriceListManager.get_effective_price_list(self.cost_model.uuid, date(2026, 2, 15))
            self.assertEqual(result, self.pl_q1)

    def test_get_effective_price_list_fallback(self):
        """Test that the fallback price list is used when the primary is out of range."""
        with tenant_context(self.tenant):
            # Jul 15 is outside Q1 (Jan-Mar) but within Year (Jan-Dec)
            result = PriceListManager.get_effective_price_list(self.cost_model.uuid, date(2026, 7, 15))
            self.assertEqual(result, self.pl_year)

    def test_get_effective_price_list_none(self):
        """Test that None is returned when no price list covers the date."""
        with tenant_context(self.tenant):
            # 2027 is outside both price lists
            result = PriceListManager.get_effective_price_list(self.cost_model.uuid, date(2027, 1, 15))
            self.assertIsNone(result)

    def test_get_effective_price_list_disabled_still_used(self):
        """Test that disabled price lists still participate in calculation."""
        with tenant_context(self.tenant):
            # Disable Q1 price list
            manager = PriceListManager(self.pl_q1.uuid)
            manager.update(enabled=False)
            # Feb 15 should still resolve to Q1 (priority 1) even though it's disabled
            result = PriceListManager.get_effective_price_list(self.cost_model.uuid, date(2026, 2, 15))
            self.assertEqual(result, self.pl_q1)


class PriceListManagerRecalcTest(MasuTestCase):
    """Test cases for recalculation triggers."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        logging.disable(0)

    def setUp(self):
        super().setUp()
        with tenant_context(self.tenant):
            self.cost_model = CostModel.objects.first()
            self.rates = [
                {
                    "metric": {"name": "cpu_core_usage_per_hour"},
                    "tiered_rates": [{"value": "1.00", "unit": "USD"}],
                    "cost_type": "Infrastructure",
                }
            ]
            manager = PriceListManager()
            self.price_list = manager.create(
                name="Recalc PL",
                description="Test",
                currency="USD",
                effective_start_date=date(2026, 1, 1),
                effective_end_date=date(2026, 12, 31),
                rates=self.rates,
            )
            PriceListManager.attach_price_lists_to_cost_model(self.cost_model.uuid, [self.price_list.uuid])

    @patch("masu.processor.tasks.update_cost_model_costs")
    def test_rate_change_triggers_recalculation(self, mock_task):
        """Test that changing rates triggers recalculation."""
        with tenant_context(self.tenant):
            manager = PriceListManager(self.price_list.uuid)
            new_rates = [
                {
                    "metric": {"name": "cpu_core_usage_per_hour"},
                    "tiered_rates": [{"value": "2.00", "unit": "USD"}],
                    "cost_type": "Infrastructure",
                }
            ]
            manager.update(rates=new_rates)
            mock_task.s.assert_called()

    @patch("masu.processor.tasks.update_cost_model_costs")
    def test_disable_does_not_trigger_recalculation(self, mock_task):
        """Test that disabling a price list does not trigger recalculation."""
        with tenant_context(self.tenant):
            manager = PriceListManager(self.price_list.uuid)
            manager.update(enabled=False)
            mock_task.s.assert_not_called()

    @patch("masu.processor.tasks.update_cost_model_costs")
    def test_name_change_does_not_trigger_recalculation(self, mock_task):
        """Test that changing only the name does not trigger recalculation."""
        with tenant_context(self.tenant):
            manager = PriceListManager(self.price_list.uuid)
            manager.update(name="Renamed PL")
            mock_task.s.assert_not_called()

    @patch("masu.processor.tasks.update_cost_model_costs")
    def test_no_recalc_if_price_list_outside_current_month(self, mock_task):
        """Test that recalculation is not triggered if the price list doesn't cover today."""
        with tenant_context(self.tenant):
            manager = PriceListManager()
            future_pl = manager.create(
                name="Future PL",
                description="Test",
                currency="USD",
                effective_start_date=date(2099, 1, 1),
                effective_end_date=date(2099, 12, 31),
                rates=self.rates,
            )
            PriceListManager.attach_price_lists_to_cost_model(
                self.cost_model.uuid, [self.price_list.uuid, future_pl.uuid]
            )
            manager2 = PriceListManager(future_pl.uuid)
            new_rates = [
                {
                    "metric": {"name": "cpu_core_usage_per_hour"},
                    "tiered_rates": [{"value": "5.00", "unit": "USD"}],
                    "cost_type": "Infrastructure",
                }
            ]
            manager2.update(rates=new_rates)
            mock_task.s.assert_not_called()
