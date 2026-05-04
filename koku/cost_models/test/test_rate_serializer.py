#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for RateSerializer rate_id and custom_name output."""
from unittest import TestCase
from uuid import uuid4

from cost_models.serializers import RateSerializer


class RateSerializerToRepresentationTest(TestCase):
    """Tests for RateSerializer.to_representation with rate_id and custom_name."""

    def test_tiered_rate_includes_rate_id(self):
        """Test that rate_id is included in output when present on the rate dict."""
        rate_id = str(uuid4())
        rate_obj = {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "description": "",
            "tiered_rates": [{"value": "0.22", "unit": "USD"}],
            "cost_type": "Infrastructure",
            "rate_id": rate_id,
        }
        serializer = RateSerializer()
        result = serializer.to_representation(rate_obj)
        self.assertEqual(result["rate_id"], rate_id)

    def test_tiered_rate_includes_custom_name(self):
        """Test that custom_name is included in output when present on the rate dict."""
        rate_obj = {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "description": "",
            "tiered_rates": [{"value": "0.22", "unit": "USD"}],
            "cost_type": "Infrastructure",
            "custom_name": "cpu-usage-infra",
        }
        serializer = RateSerializer()
        result = serializer.to_representation(rate_obj)
        self.assertEqual(result["custom_name"], "cpu-usage-infra")

    def test_tag_rate_includes_rate_id(self):
        """Test that rate_id is included for tag-based rates."""
        rate_id = str(uuid4())
        rate_obj = {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "description": "",
            "tag_rates": {"tag_key": "app", "tag_values": []},
            "cost_type": "Supplementary",
            "rate_id": rate_id,
        }
        serializer = RateSerializer()
        result = serializer.to_representation(rate_obj)
        self.assertEqual(result["rate_id"], rate_id)

    def test_rate_without_rate_id_omits_field(self):
        """Test that rate_id is omitted when not present on the rate dict."""
        rate_obj = {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "description": "",
            "tiered_rates": [{"value": "0.22", "unit": "USD"}],
            "cost_type": "Infrastructure",
        }
        serializer = RateSerializer()
        result = serializer.to_representation(rate_obj)
        self.assertNotIn("rate_id", result)

    def test_rate_without_custom_name_omits_field(self):
        """Test that custom_name is omitted when not present on the rate dict."""
        rate_obj = {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "description": "",
            "tiered_rates": [{"value": "0.22", "unit": "USD"}],
            "cost_type": "Infrastructure",
        }
        serializer = RateSerializer()
        result = serializer.to_representation(rate_obj)
        self.assertNotIn("custom_name", result)

    def test_backward_compat_existing_rate_output_unchanged(self):
        """Test that existing rate output structure is preserved."""
        rate_obj = {
            "metric": {"name": "memory_gb_usage_per_hour"},
            "description": "A memory rate",
            "tiered_rates": [{"value": "0.10", "unit": "USD"}],
            "cost_type": "Supplementary",
        }
        serializer = RateSerializer()
        result = serializer.to_representation(rate_obj)
        self.assertEqual(result["metric"], {"name": "memory_gb_usage_per_hour"})
        self.assertEqual(result["description"], "A memory rate")
        self.assertEqual(result["cost_type"], "Supplementary")
        self.assertIn("tiered_rates", result)

    def test_to_internal_value_passes_rate_id_through(self):
        """Test that to_internal_value does not strip rate_id from data."""
        rate_id = str(uuid4())
        data = {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "cost_type": "Infrastructure",
            "tiered_rates": [{"value": "0.22", "unit": "USD"}],
            "rate_id": rate_id,
            "custom_name": "my-rate",
        }
        serializer = RateSerializer()
        result = serializer.to_internal_value(data)
        self.assertEqual(result["rate_id"], rate_id)
        self.assertEqual(result["custom_name"], "my-rate")

    def test_to_internal_value_passes_custom_name_through(self):
        """Test that to_internal_value does not strip custom_name from data."""
        data = {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "cost_type": "Infrastructure",
            "tiered_rates": [{"value": "0.22", "unit": "USD"}],
            "custom_name": "my-custom-name",
        }
        serializer = RateSerializer()
        result = serializer.to_internal_value(data)
        self.assertEqual(result["custom_name"], "my-custom-name")

    def test_to_representation_no_tiered_no_tag_rates(self):
        """Test output shape when neither tiered_rates nor tag_rates are present."""
        rate_id = str(uuid4())
        rate_obj = {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "description": "orphan rate",
            "cost_type": "Infrastructure",
            "rate_id": rate_id,
            "custom_name": "cpu-infra",
        }
        serializer = RateSerializer()
        result = serializer.to_representation(rate_obj)
        self.assertEqual(result["metric"], {"name": "cpu_core_usage_per_hour"})
        self.assertEqual(result["description"], "orphan rate")
        self.assertEqual(result["rate_id"], rate_id)
        self.assertEqual(result["custom_name"], "cpu-infra")
        self.assertNotIn("tiered_rates", result)
        self.assertNotIn("tag_rates", result)
        self.assertNotIn("cost_type", result)

    def test_is_valid_rejects_malformed_rate_id(self):
        """Test that a malformed rate_id string is rejected by field validation."""
        data = {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "cost_type": "Infrastructure",
            "tiered_rates": [{"value": "0.22", "unit": "USD"}],
            "rate_id": "not-a-uuid",
        }
        serializer = RateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("rate_id", serializer.errors)

    def test_is_valid_accepts_valid_rate_id(self):
        """Test that a valid UUID string passes field validation."""
        data = {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "cost_type": "Infrastructure",
            "tiered_rates": [{"value": "0.22", "unit": "USD"}],
            "rate_id": str(uuid4()),
        }
        serializer = RateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_is_valid_rejects_custom_name_over_50_chars(self):
        """Test that a custom_name exceeding 50 characters is rejected."""
        data = {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "cost_type": "Infrastructure",
            "tiered_rates": [{"value": "0.22", "unit": "USD"}],
            "custom_name": "x" * 51,
        }
        serializer = RateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("custom_name", serializer.errors)
