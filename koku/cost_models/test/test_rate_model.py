#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the Rate model."""
import logging
from datetime import date
from decimal import Decimal

from django.db import IntegrityError
from django_tenants.utils import tenant_context

from cost_models.models import CostModel
from cost_models.models import PriceList
from cost_models.models import PriceListCostModelMap
from cost_models.models import Rate
from masu.test import MasuTestCase


class RateModelTest(MasuTestCase):
    """Test cases for the Rate model."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        logging.disable(0)

    def setUp(self):
        super().setUp()
        with tenant_context(self.tenant):
            self.cost_model = CostModel.objects.create(
                name="Test CM",
                description="Test",
                source_type="OCP",
                rates=[
                    {
                        "metric": {"name": "cpu_core_usage_per_hour"},
                        "tiered_rates": [{"value": "0.22", "unit": "USD"}],
                        "cost_type": "Infrastructure",
                    }
                ],
            )
            self.price_list = PriceList.objects.create(
                name="Test PL",
                description="Test",
                currency="USD",
                effective_start_date=date(2026, 1, 1),
                effective_end_date=date(2026, 12, 31),
                rates=self.cost_model.rates,
            )
            PriceListCostModelMap.objects.create(
                price_list=self.price_list,
                cost_model=self.cost_model,
                priority=1,
            )

    def test_create_rate(self):
        """Test creating a Rate with all required fields."""
        with tenant_context(self.tenant):
            rate = Rate.objects.create(
                price_list=self.price_list,
                custom_name="cpu-usage-infra",
                metric="cpu_core_usage_per_hour",
                metric_type="cpu",
                cost_type="Infrastructure",
                default_rate=Decimal("0.22"),
            )
            self.assertIsNotNone(rate.uuid)
            self.assertEqual(rate.price_list, self.price_list)
            self.assertEqual(rate.custom_name, "cpu-usage-infra")
            self.assertEqual(rate.metric, "cpu_core_usage_per_hour")
            self.assertEqual(rate.metric_type, "cpu")
            self.assertEqual(rate.cost_type, "Infrastructure")
            self.assertEqual(rate.default_rate, Decimal("0.22"))
            self.assertEqual(rate.description, "")
            self.assertEqual(rate.tag_key, "")
            self.assertEqual(rate.tag_values, [])

    def test_uuid_primary_key_auto_generated(self):
        """Test that uuid is auto-generated as primary key."""
        with tenant_context(self.tenant):
            rate = Rate.objects.create(
                price_list=self.price_list,
                custom_name="auto-uuid-test",
                metric="cpu_core_usage_per_hour",
                metric_type="cpu",
                cost_type="Infrastructure",
                default_rate=Decimal("1.00"),
            )
            self.assertIsNotNone(rate.uuid)
            self.assertEqual(rate.pk, rate.uuid)

    def test_default_rate_allows_null(self):
        """Test that default_rate can be null for tag-only rates."""
        with tenant_context(self.tenant):
            rate = Rate.objects.create(
                price_list=self.price_list,
                custom_name="tag-rate-null-default",
                metric="cpu_core_usage_per_hour",
                metric_type="cpu",
                cost_type="Supplementary",
                default_rate=None,
                tag_key="app",
                tag_values=[{"tag_value": "web", "value": "0.5", "unit": "USD"}],
            )
            self.assertIsNone(rate.default_rate)
            self.assertEqual(rate.tag_key, "app")
            self.assertEqual(len(rate.tag_values), 1)

    def test_timestamps_auto_populated(self):
        """Test that created_timestamp and updated_timestamp are auto-populated."""
        with tenant_context(self.tenant):
            rate = Rate.objects.create(
                price_list=self.price_list,
                custom_name="timestamp-test",
                metric="cpu_core_usage_per_hour",
                metric_type="cpu",
                cost_type="Infrastructure",
                default_rate=Decimal("0.50"),
            )
            self.assertIsNotNone(rate.created_timestamp)
            self.assertIsNotNone(rate.updated_timestamp)

    def test_tag_values_defaults_to_list(self):
        """Test that tag_values defaults to an empty list, not dict."""
        with tenant_context(self.tenant):
            rate = Rate.objects.create(
                price_list=self.price_list,
                custom_name="tag-default-test",
                metric="memory_gb_usage_per_hour",
                metric_type="memory",
                cost_type="Supplementary",
                default_rate=Decimal("0.10"),
            )
            self.assertIsInstance(rate.tag_values, list)
            self.assertEqual(rate.tag_values, [])

    def test_unique_together_price_list_custom_name(self):
        """Test that (price_list, custom_name) enforces uniqueness."""
        with tenant_context(self.tenant):
            Rate.objects.create(
                price_list=self.price_list,
                custom_name="unique-test",
                metric="cpu_core_usage_per_hour",
                metric_type="cpu",
                cost_type="Infrastructure",
                default_rate=Decimal("0.22"),
            )
            with self.assertRaises(IntegrityError):
                Rate.objects.create(
                    price_list=self.price_list,
                    custom_name="unique-test",
                    metric="memory_gb_usage_per_hour",
                    metric_type="memory",
                    cost_type="Supplementary",
                    default_rate=Decimal("0.10"),
                )

    def test_cascade_delete_price_list(self):
        """Test that deleting a PriceList cascades to its Rate rows."""
        with tenant_context(self.tenant):
            Rate.objects.create(
                price_list=self.price_list,
                custom_name="cascade-test",
                metric="cpu_core_usage_per_hour",
                metric_type="cpu",
                cost_type="Infrastructure",
                default_rate=Decimal("0.22"),
            )
            pl_uuid = self.price_list.uuid
            self.price_list.delete()
            self.assertEqual(Rate.objects.filter(price_list__uuid=pl_uuid).count(), 0)

    def test_db_table_name(self):
        """Test that the db_table is cost_model_rate."""
        self.assertEqual(Rate._meta.db_table, "cost_model_rate")

    def test_indexes_exist(self):
        """Test that expected indexes are defined on Rate model."""
        index_names = {idx.name for idx in Rate._meta.indexes}
        self.assertIn("rate_price_list_idx", index_names)
        self.assertIn("rate_custom_name_idx", index_names)
        self.assertIn("rate_metric_idx", index_names)
