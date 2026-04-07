#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the data migration that normalizes PriceList JSON rates into Rate rows."""
from decimal import Decimal

from django.db import connection
from django_tenants.utils import tenant_context

from cost_models.models import CostModel
from cost_models.models import PriceList
from cost_models.models import PriceListCostModelMap
from cost_models.models import Rate
from masu.test import MasuTestCase

MIGRATE_FROM = ("cost_models", "0012_add_rate_model")
MIGRATE_TO = ("cost_models", "0013_normalize_rates_to_rate_table")


class NormalizeRatesToRateTableTest(MasuTestCase):
    """Test the data migration that populates Rate rows from PriceList JSON."""

    def _run_migration(self, target):
        """Run migration to target state within the tenant schema."""
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        executor.migrate([target])
        executor.loader.build_graph()

    def _create_cost_model_with_price_list(self, name, rates):
        """Helper to create a CostModel + PriceList + mapping."""
        cm = CostModel.objects.create(
            name=name,
            description="Test",
            source_type="OCP",
            rates=rates,
        )
        pl = PriceList.objects.create(
            name=f"{name} prices",
            description="Auto-created",
            currency="USD",
            effective_start_date="2026-03-01",
            effective_end_date="2099-12-31",
            enabled=True,
            version=1,
            rates=rates,
        )
        PriceListCostModelMap.objects.create(
            price_list=pl,
            cost_model=cm,
            priority=1,
        )
        return cm, pl

    def test_tiered_rate_creates_rate_row(self):
        """Test that a tiered rate in PriceList JSON produces a Rate row."""
        with tenant_context(self.tenant):
            self._run_migration(MIGRATE_FROM)
            _, pl = self._create_cost_model_with_price_list(
                "Tiered CM",
                [
                    {
                        "metric": {"name": "cpu_core_usage_per_hour"},
                        "tiered_rates": [{"value": "0.22", "unit": "USD"}],
                        "cost_type": "Infrastructure",
                    }
                ],
            )
            self._run_migration(MIGRATE_TO)
            rates = Rate.objects.filter(price_list=pl)
            self.assertEqual(rates.count(), 1)
            rate = rates.first()
            self.assertEqual(rate.metric, "cpu_core_usage_per_hour")
            self.assertEqual(rate.cost_type, "Infrastructure")
            self.assertEqual(rate.default_rate, Decimal("0.22"))

    def test_tag_rate_creates_rate_row(self):
        """Test that a tag rate produces a Rate row with tag_key and tag_values."""
        with tenant_context(self.tenant):
            self._run_migration(MIGRATE_FROM)
            tag_values = [
                {"tag_value": "web", "value": "0.5", "unit": "USD", "default": False},
                {"tag_value": "api", "value": "0.3", "unit": "USD", "default": False},
            ]
            _, pl = self._create_cost_model_with_price_list(
                "Tag CM",
                [
                    {
                        "metric": {"name": "cpu_core_usage_per_hour"},
                        "tag_rates": {
                            "tag_key": "app",
                            "tag_values": tag_values,
                        },
                        "cost_type": "Supplementary",
                    }
                ],
            )
            self._run_migration(MIGRATE_TO)
            rate = Rate.objects.get(price_list=pl)
            self.assertEqual(rate.tag_key, "app")
            self.assertEqual(rate.tag_values, tag_values)
            self.assertIsNone(rate.default_rate)

    def test_multiple_rates_create_multiple_rows(self):
        """Test that multiple rates produce multiple Rate rows."""
        with tenant_context(self.tenant):
            self._run_migration(MIGRATE_FROM)
            _, pl = self._create_cost_model_with_price_list(
                "Multi CM",
                [
                    {
                        "metric": {"name": "cpu_core_usage_per_hour"},
                        "tiered_rates": [{"value": "0.22", "unit": "USD"}],
                        "cost_type": "Infrastructure",
                    },
                    {
                        "metric": {"name": "memory_gb_usage_per_hour"},
                        "tiered_rates": [{"value": "0.10", "unit": "USD"}],
                        "cost_type": "Supplementary",
                    },
                ],
            )
            self._run_migration(MIGRATE_TO)
            self.assertEqual(Rate.objects.filter(price_list=pl).count(), 2)

    def test_empty_rates_creates_no_rows(self):
        """Test that a PriceList with empty rates produces no Rate rows."""
        with tenant_context(self.tenant):
            self._run_migration(MIGRATE_FROM)
            _, pl = self._create_cost_model_with_price_list("Empty CM", [])
            self._run_migration(MIGRATE_TO)
            self.assertEqual(Rate.objects.filter(price_list=pl).count(), 0)

    def test_metric_type_derived_correctly(self):
        """Test that metric_type is correctly derived from the metric name."""
        with tenant_context(self.tenant):
            self._run_migration(MIGRATE_FROM)
            _, pl = self._create_cost_model_with_price_list(
                "Type CM",
                [
                    {
                        "metric": {"name": "memory_gb_usage_per_hour"},
                        "tiered_rates": [{"value": "0.10", "unit": "USD"}],
                        "cost_type": "Supplementary",
                    }
                ],
            )
            self._run_migration(MIGRATE_TO)
            rate = Rate.objects.get(price_list=pl)
            self.assertEqual(rate.metric_type, "memory")

    def test_pvc_metric_type_is_pvc(self):
        """Test that pvc_cost_per_month maps to metric_type 'pvc', not 'persistent volume claims'."""
        with tenant_context(self.tenant):
            self._run_migration(MIGRATE_FROM)
            _, pl = self._create_cost_model_with_price_list(
                "PVC CM",
                [
                    {
                        "metric": {"name": "pvc_cost_per_month"},
                        "tiered_rates": [{"value": "5.00", "unit": "USD"}],
                        "cost_type": "Infrastructure",
                    }
                ],
            )
            self._run_migration(MIGRATE_TO)
            rate = Rate.objects.get(price_list=pl)
            self.assertEqual(rate.metric_type, "pvc")

    def test_custom_name_generated(self):
        """Test that custom_name is generated for each Rate row."""
        with tenant_context(self.tenant):
            self._run_migration(MIGRATE_FROM)
            _, pl = self._create_cost_model_with_price_list(
                "Name CM",
                [
                    {
                        "metric": {"name": "cpu_core_usage_per_hour"},
                        "tiered_rates": [{"value": "0.22", "unit": "USD"}],
                        "cost_type": "Infrastructure",
                    }
                ],
            )
            self._run_migration(MIGRATE_TO)
            rate = Rate.objects.get(price_list=pl)
            self.assertEqual(rate.custom_name, "cpu_core_usage_per_hour-Infrastructure")

    def test_duplicate_rates_get_deduplicated_names(self):
        """Test that duplicate metric+cost_type combinations get unique custom_names."""
        with tenant_context(self.tenant):
            self._run_migration(MIGRATE_FROM)
            _, pl = self._create_cost_model_with_price_list(
                "Dup CM",
                [
                    {
                        "metric": {"name": "cpu_core_usage_per_hour"},
                        "tiered_rates": [{"value": "0.22", "unit": "USD"}],
                        "cost_type": "Infrastructure",
                    },
                    {
                        "metric": {"name": "cpu_core_usage_per_hour"},
                        "tag_rates": {
                            "tag_key": "env",
                            "tag_values": [{"tag_value": "prod", "value": "1.0", "unit": "USD"}],
                        },
                        "cost_type": "Infrastructure",
                    },
                ],
            )
            self._run_migration(MIGRATE_TO)
            rates = Rate.objects.filter(price_list=pl).order_by("custom_name")
            names = [r.custom_name for r in rates]
            self.assertEqual(len(names), 2)
            self.assertEqual(len(set(names)), 2)

    def test_description_preserved(self):
        """Test that the description field is preserved from the rate dict."""
        with tenant_context(self.tenant):
            self._run_migration(MIGRATE_FROM)
            _, pl = self._create_cost_model_with_price_list(
                "Desc CM",
                [
                    {
                        "metric": {"name": "cpu_core_usage_per_hour"},
                        "tiered_rates": [{"value": "0.22", "unit": "USD"}],
                        "cost_type": "Infrastructure",
                        "description": "CPU infrastructure rate",
                    }
                ],
            )
            self._run_migration(MIGRATE_TO)
            rate = Rate.objects.get(price_list=pl)
            self.assertEqual(rate.description, "CPU infrastructure rate")

    def test_reverse_migration_deletes_rate_rows(self):
        """Test that reversing the migration removes Rate rows."""
        with tenant_context(self.tenant):
            self._run_migration(MIGRATE_FROM)
            _, pl = self._create_cost_model_with_price_list(
                "Reverse CM",
                [
                    {
                        "metric": {"name": "cpu_core_usage_per_hour"},
                        "tiered_rates": [{"value": "0.22", "unit": "USD"}],
                        "cost_type": "Infrastructure",
                    }
                ],
            )
            self._run_migration(MIGRATE_TO)
            self.assertEqual(Rate.objects.filter(price_list=pl).count(), 1)

            self._run_migration(MIGRATE_FROM)
            self.assertEqual(Rate.objects.filter(price_list=pl).count(), 0)

    def test_rate_linked_to_correct_price_list(self):
        """Test that Rate rows are linked to the correct PriceList."""
        with tenant_context(self.tenant):
            self._run_migration(MIGRATE_FROM)
            _, pl1 = self._create_cost_model_with_price_list(
                "CM One",
                [
                    {
                        "metric": {"name": "cpu_core_usage_per_hour"},
                        "tiered_rates": [{"value": "1.00", "unit": "USD"}],
                        "cost_type": "Infrastructure",
                    }
                ],
            )
            _, pl2 = self._create_cost_model_with_price_list(
                "CM Two",
                [
                    {
                        "metric": {"name": "memory_gb_usage_per_hour"},
                        "tiered_rates": [{"value": "2.00", "unit": "USD"}],
                        "cost_type": "Supplementary",
                    }
                ],
            )
            self._run_migration(MIGRATE_TO)
            self.assertEqual(Rate.objects.filter(price_list=pl1).first().metric, "cpu_core_usage_per_hour")
            self.assertEqual(Rate.objects.filter(price_list=pl2).first().metric, "memory_gb_usage_per_hour")

    def test_price_list_without_mapping_still_normalized(self):
        """Test that a PriceList without a CostModel mapping still gets Rate rows."""
        with tenant_context(self.tenant):
            self._run_migration(MIGRATE_FROM)
            pl = PriceList.objects.create(
                name="Standalone PL",
                description="No cost model",
                currency="USD",
                effective_start_date="2026-03-01",
                effective_end_date="2099-12-31",
                enabled=True,
                version=1,
                rates=[
                    {
                        "metric": {"name": "storage_gb_usage_per_month"},
                        "tiered_rates": [{"value": "0.50", "unit": "USD"}],
                        "cost_type": "Infrastructure",
                    }
                ],
            )
            self._run_migration(MIGRATE_TO)
            self.assertEqual(Rate.objects.filter(price_list=pl).count(), 1)

    def test_migration_idempotent_no_duplicates(self):
        """Test that running migration twice does not create duplicate Rate rows."""
        with tenant_context(self.tenant):
            self._run_migration(MIGRATE_FROM)
            _, pl = self._create_cost_model_with_price_list(
                "Idempotent CM",
                [
                    {
                        "metric": {"name": "cpu_core_usage_per_hour"},
                        "tiered_rates": [{"value": "0.22", "unit": "USD"}],
                        "cost_type": "Infrastructure",
                    }
                ],
            )
            self._run_migration(MIGRATE_TO)
            count_after_first = Rate.objects.filter(price_list=pl).count()

            self._run_migration(MIGRATE_FROM)
            self._run_migration(MIGRATE_TO)
            count_after_second = Rate.objects.filter(price_list=pl).count()
            self.assertEqual(count_after_first, count_after_second)
