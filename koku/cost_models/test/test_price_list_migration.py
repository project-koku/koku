#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the data migration that copies CostModel rates to PriceList entities."""
import logging

from django.db import connection
from django_tenants.utils import tenant_context

from cost_models.models import CostModel
from cost_models.models import PriceList
from cost_models.models import PriceListCostModelMap
from masu.test import MasuTestCase

MIGRATE_FROM = ("cost_models", "0010_add_price_list_models")
MIGRATE_TO = ("cost_models", "0011_migrate_cost_model_rates_to_price_lists")


class MigrateRatesToPriceListsTest(MasuTestCase):
    """Test the data migration using MigrationExecutor."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        logging.disable(0)

    def _run_migration(self, target):
        """Run migration to target state within the tenant schema."""
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        executor.migrate([target])
        executor.loader.build_graph()

    def test_cost_model_with_rates_gets_price_list(self):
        """Test that the migration creates a price list for a cost model with rates."""
        with tenant_context(self.tenant):
            # Roll back to before the data migration
            self._run_migration(MIGRATE_FROM)

            # Create a cost model with rates at the pre-migration state
            cm = CostModel.objects.create(
                name="Migration Test CM",
                description="Test",
                source_type="OCP",
                rates=[
                    {
                        "metric": {"name": "cpu_core_usage_per_hour"},
                        "tiered_rates": [{"value": "1.00", "unit": "USD"}],
                        "cost_type": "Infrastructure",
                    }
                ],
            )

            # Run the data migration forward
            self._run_migration(MIGRATE_TO)

            # Verify a price list was created and linked
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            self.assertEqual(mapping.price_list.name, "Migration Test CM prices")
            self.assertEqual(mapping.price_list.rates, cm.rates)
            self.assertEqual(mapping.price_list.currency, cm.currency)
            self.assertEqual(mapping.priority, 1)
            self.assertTrue(mapping.price_list.enabled)
            self.assertEqual(mapping.price_list.version, 1)

    def test_cost_model_without_rates_skipped(self):
        """Test that the migration skips cost models without rates."""
        with tenant_context(self.tenant):
            self._run_migration(MIGRATE_FROM)

            cm = CostModel.objects.create(
                name="No Rates Model",
                description="Test model with no rates",
                source_type="OCP",
                rates={},
            )

            self._run_migration(MIGRATE_TO)

            maps = PriceListCostModelMap.objects.filter(cost_model=cm)
            self.assertEqual(maps.count(), 0)

    def test_reverse_migration_deletes_auto_migrated(self):
        """Test that reversing the migration removes auto-migrated price lists."""
        with tenant_context(self.tenant):
            self._run_migration(MIGRATE_FROM)

            CostModel.objects.create(
                name="Reversible CM",
                description="Test",
                source_type="OCP",
                rates=[
                    {
                        "metric": {"name": "cpu_core_usage_per_hour"},
                        "tiered_rates": [{"value": "2.00", "unit": "USD"}],
                        "cost_type": "Infrastructure",
                    }
                ],
            )

            # Migrate forward
            self._run_migration(MIGRATE_TO)
            self.assertTrue(PriceList.objects.filter(name="Reversible CM prices").exists())

            # Migrate backward
            self._run_migration(MIGRATE_FROM)
            self.assertFalse(PriceList.objects.filter(name="Reversible CM prices").exists())

    def test_migration_skips_already_mapped_cost_model(self):
        """Test that the migration skips cost models that already have a PriceList mapping."""
        with tenant_context(self.tenant):
            self._run_migration(MIGRATE_FROM)

            cm = CostModel.objects.create(
                name="Already Mapped CM",
                description="Test",
                source_type="OCP",
                rates=[
                    {
                        "metric": {"name": "cpu_core_usage_per_hour"},
                        "tiered_rates": [{"value": "3.00", "unit": "USD"}],
                        "cost_type": "Infrastructure",
                    }
                ],
            )

            # Simulate dual-write having already created a PriceList for this cost model
            existing_pl = PriceList.objects.create(
                name="Pre-existing PL",
                description="Created by dual-write",
                currency="USD",
                effective_start_date="2026-03-01",
                effective_end_date="2099-12-31",
                enabled=True,
                version=1,
                rates=cm.rates,
            )
            PriceListCostModelMap.objects.create(
                price_list=existing_pl,
                cost_model=cm,
                priority=1,
            )

            # Run migration forward — should skip this cost model
            self._run_migration(MIGRATE_TO)
            self.assertEqual(PriceListCostModelMap.objects.filter(cost_model=cm).count(), 1)
            # Verify it's still the pre-existing one, not a new auto-migrated one
            mapping = PriceListCostModelMap.objects.get(cost_model=cm)
            self.assertEqual(mapping.price_list.name, "Pre-existing PL")
