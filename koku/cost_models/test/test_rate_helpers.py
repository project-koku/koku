#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for Rate helper functions in cost_model_manager."""
from decimal import Decimal
from unittest import TestCase

from api.metrics import constants as metric_constants
from cost_models.cost_model_manager import derive_metric_type
from cost_models.cost_model_manager import extract_default_rate
from cost_models.cost_model_manager import generate_custom_name


class DeriveMetricTypeTest(TestCase):
    """Tests for derive_metric_type helper."""

    def test_cpu_metrics(self):
        """Test CPU metrics map to 'cpu'."""
        self.assertEqual(derive_metric_type("cpu_core_usage_per_hour"), "cpu")
        self.assertEqual(derive_metric_type("cpu_core_request_per_hour"), "cpu")
        self.assertEqual(derive_metric_type("cpu_core_effective_usage_per_hour"), "cpu")

    def test_memory_metrics(self):
        """Test memory metrics map to 'memory'."""
        self.assertEqual(derive_metric_type("memory_gb_usage_per_hour"), "memory")
        self.assertEqual(derive_metric_type("memory_gb_request_per_hour"), "memory")
        self.assertEqual(derive_metric_type("memory_gb_effective_usage_per_hour"), "memory")

    def test_storage_metrics(self):
        """Test storage metrics map to 'storage'."""
        self.assertEqual(derive_metric_type("storage_gb_usage_per_month"), "storage")
        self.assertEqual(derive_metric_type("storage_gb_request_per_month"), "storage")

    def test_node_metrics(self):
        """Test node metrics map to 'node'."""
        self.assertEqual(derive_metric_type("node_cost_per_month"), "node")
        self.assertEqual(derive_metric_type("node_core_cost_per_hour"), "node")
        self.assertEqual(derive_metric_type("node_core_cost_per_month"), "node")

    def test_cluster_metrics(self):
        """Test cluster metrics map to 'cluster'."""
        self.assertEqual(derive_metric_type("cluster_cost_per_month"), "cluster")
        self.assertEqual(derive_metric_type("cluster_cost_per_hour"), "cluster")
        self.assertEqual(derive_metric_type("cluster_core_cost_per_hour"), "cluster")

    def test_pvc_metric(self):
        """Test PVC metric maps to 'pvc' (not 'persistent volume claims')."""
        self.assertEqual(derive_metric_type("pvc_cost_per_month"), "pvc")

    def test_vm_metrics(self):
        """Test VM metrics map to 'vm'."""
        self.assertEqual(derive_metric_type("vm_cost_per_month"), "vm")
        self.assertEqual(derive_metric_type("vm_cost_per_hour"), "vm")
        self.assertEqual(derive_metric_type("vm_core_cost_per_month"), "vm")
        self.assertEqual(derive_metric_type("vm_core_cost_per_hour"), "vm")

    def test_project_metric(self):
        """Test project metric maps to 'project'."""
        self.assertEqual(derive_metric_type("project_per_month"), "project")

    def test_gpu_metric(self):
        """Test GPU metric (behind Unleash flag) maps to 'gpu'."""
        self.assertEqual(derive_metric_type("gpu_cost_per_month"), "gpu")

    def test_unknown_metric_returns_other(self):
        """Test that an unknown metric returns 'other'."""
        self.assertEqual(derive_metric_type("totally_bogus_metric"), "other")

    def test_all_metric_choices_mapped(self):
        """Test that every metric in METRIC_CHOICES produces a non-'other' type."""
        for metric_name in metric_constants.METRIC_CHOICES:
            result = derive_metric_type(metric_name)
            self.assertNotEqual(
                result,
                "other",
                f"{metric_name} mapped to 'other' — missing from LABEL_METRIC_TO_TYPE or COST_MODEL_METRIC_MAP",
            )


class GenerateCustomNameTest(TestCase):
    """Tests for generate_custom_name helper."""

    def test_tiered_rate_name(self):
        """Test custom name for a tiered rate."""
        rate = {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "cost_type": "Infrastructure",
            "tiered_rates": [{"value": "0.22", "unit": "USD"}],
        }
        name = generate_custom_name(rate, existing_names=set())
        self.assertEqual(name, "cpu_core_usage_per_hour-Infrastructure")

    def test_tag_rate_name_includes_tag_key(self):
        """Test custom name for a tag rate includes tag_key."""
        rate = {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "cost_type": "Supplementary",
            "tag_rates": {"tag_key": "app", "tag_values": []},
        }
        name = generate_custom_name(rate, existing_names=set())
        self.assertEqual(name, "cpu_core_usage_per_hour-Supplementary-app")

    def test_deduplication_appends_suffix(self):
        """Test that duplicate names get a numeric suffix."""
        rate = {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "cost_type": "Infrastructure",
            "tiered_rates": [{"value": "0.22", "unit": "USD"}],
        }
        existing = {"cpu_core_usage_per_hour-Infrastructure"}
        name = generate_custom_name(rate, existing_names=existing)
        self.assertEqual(name, "cpu_core_usage_per_hour-Infrastructure-2")

    def test_deduplication_increments(self):
        """Test that suffixes increment correctly."""
        rate = {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "cost_type": "Infrastructure",
            "tiered_rates": [{"value": "0.22", "unit": "USD"}],
        }
        existing = {
            "cpu_core_usage_per_hour-Infrastructure",
            "cpu_core_usage_per_hour-Infrastructure-2",
        }
        name = generate_custom_name(rate, existing_names=existing)
        self.assertEqual(name, "cpu_core_usage_per_hour-Infrastructure-3")

    def test_name_truncated_to_max_length(self):
        """Test that generated name is truncated to 50 chars."""
        rate = {
            "metric": {"name": "cpu_core_effective_usage_per_hour"},
            "cost_type": "Supplementary",
            "tag_rates": {"tag_key": "very_long_tag_key_name_here", "tag_values": []},
        }
        name = generate_custom_name(rate, existing_names=set())
        self.assertLessEqual(len(name), 50)


class ExtractDefaultRateTest(TestCase):
    """Tests for extract_default_rate helper."""

    def test_tiered_rate_extracts_value(self):
        """Test extraction of first tier value."""
        rate = {
            "tiered_rates": [{"value": "0.22", "unit": "USD"}],
        }
        result = extract_default_rate(rate)
        self.assertEqual(result, Decimal("0.22"))

    def test_tiered_rate_with_decimal_value(self):
        """Test extraction with an already-Decimal value."""
        rate = {
            "tiered_rates": [{"value": Decimal("1.50"), "unit": "USD"}],
        }
        result = extract_default_rate(rate)
        self.assertEqual(result, Decimal("1.50"))

    def test_tag_rate_returns_none(self):
        """Test that tag-only rate returns None."""
        rate = {
            "tag_rates": {
                "tag_key": "app",
                "tag_values": [{"tag_value": "web", "value": "0.5", "unit": "USD"}],
            },
        }
        result = extract_default_rate(rate)
        self.assertIsNone(result)

    def test_empty_tiered_rates_returns_none(self):
        """Test that empty tiered_rates list returns None."""
        rate = {"tiered_rates": []}
        result = extract_default_rate(rate)
        self.assertIsNone(result)

    def test_no_rates_at_all_returns_none(self):
        """Test that a rate with neither tiered nor tag returns None."""
        rate = {"metric": {"name": "cpu_core_usage_per_hour"}}
        result = extract_default_rate(rate)
        self.assertIsNone(result)

    def test_nan_value_returns_none(self):
        """Test that NaN value is rejected and returns None."""
        rate = {"tiered_rates": [{"value": "NaN", "unit": "USD"}]}
        result = extract_default_rate(rate)
        self.assertIsNone(result)

    def test_infinity_value_returns_none(self):
        """Test that Infinity value is rejected and returns None."""
        rate = {"tiered_rates": [{"value": "Infinity", "unit": "USD"}]}
        result = extract_default_rate(rate)
        self.assertIsNone(result)

    def test_negative_infinity_value_returns_none(self):
        """Test that -Infinity value is rejected and returns None."""
        rate = {"tiered_rates": [{"value": "-Infinity", "unit": "USD"}]}
        result = extract_default_rate(rate)
        self.assertIsNone(result)
