#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for RateSerializer output and input behavior."""
from unittest import TestCase
from uuid import uuid4

from cost_models.serializers import RateSerializer


class RateSerializerToRepresentationTest(TestCase):
    """Tests for RateSerializer.to_representation business field output."""

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

    def test_to_representation_no_tiered_no_tag_rates(self):
        """Test output shape when neither tiered_rates nor tag_rates are present."""
        rate_obj = {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "description": "orphan rate",
            "cost_type": "Infrastructure",
            "rate_id": str(uuid4()),
            "custom_name": "cpu-infra",
        }
        serializer = RateSerializer()
        result = serializer.to_representation(rate_obj)
        self.assertEqual(result["metric"], {"name": "cpu_core_usage_per_hour"})
        self.assertEqual(result["description"], "orphan rate")
        self.assertNotIn("rate_id", result)
        self.assertNotIn("custom_name", result)
        self.assertNotIn("tiered_rates", result)
        self.assertNotIn("tag_rates", result)
        self.assertNotIn("cost_type", result)


class RateSerializerInternalFieldExclusionTest(TestCase):
    """SC-8/SC-28: Internal identifiers must not leak through the public API.

    SI-11: Round-tripping an API response must not fail due to server-injected fields.
    CM-7: API surface must only expose fields that consumers need.
    """

    def test_to_representation_excludes_rate_id(self):
        """SC-8: rate_id (internal DB PK) must not appear in API output."""
        rate_obj = {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "description": "",
            "tiered_rates": [{"value": "0.22", "unit": "USD"}],
            "cost_type": "Infrastructure",
            "rate_id": str(uuid4()),
        }
        serializer = RateSerializer()
        result = serializer.to_representation(rate_obj)
        self.assertNotIn("rate_id", result)

    def test_to_representation_excludes_custom_name(self):
        """SC-8: custom_name (internal enrichment field) must not appear in API output."""
        rate_obj = {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "description": "",
            "tiered_rates": [{"value": "0.22", "unit": "USD"}],
            "cost_type": "Infrastructure",
            "custom_name": "cpu-usage-infra",
        }
        serializer = RateSerializer()
        result = serializer.to_representation(rate_obj)
        self.assertNotIn("custom_name", result)

    def test_to_internal_value_strips_rate_id(self):
        """SI-11: rate_id in input must be silently stripped, not validated."""
        data = {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "cost_type": "Infrastructure",
            "tiered_rates": [{"value": "0.22", "unit": "USD"}],
            "rate_id": str(uuid4()),
        }
        serializer = RateSerializer()
        result = serializer.to_internal_value(data)
        self.assertNotIn("rate_id", result)

    def test_to_internal_value_passes_custom_name_through(self):
        """custom_name is preserved for PriceList API consumers."""
        data = {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "cost_type": "Infrastructure",
            "tiered_rates": [{"value": "0.22", "unit": "USD"}],
            "custom_name": "my-rate",
        }
        serializer = RateSerializer()
        result = serializer.to_internal_value(data)
        self.assertEqual(result["custom_name"], "my-rate")

    def test_to_internal_value_tolerates_malformed_rate_id(self):
        """SI-11: Malformed rate_id must be silently stripped, not cause a 400 error."""
        data = {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "cost_type": "Infrastructure",
            "tiered_rates": [{"value": "0.22", "unit": "USD"}],
            "rate_id": "garbage-not-a-uuid",
        }
        serializer = RateSerializer()
        result = serializer.to_internal_value(data)
        self.assertNotIn("rate_id", result)

    def test_to_representation_preserves_only_business_fields(self):
        """CM-7: API output must not contain internal identifiers like rate_id."""
        rate_obj = {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "description": "A CPU rate",
            "tiered_rates": [{"value": "0.22", "unit": "USD"}],
            "cost_type": "Infrastructure",
            "rate_id": str(uuid4()),
            "custom_name": "cpu-infra",
        }
        serializer = RateSerializer()
        result = serializer.to_representation(rate_obj)
        self.assertNotIn("rate_id", result)
        self.assertIn("metric", result)
        self.assertIn("tiered_rates", result)
        self.assertIn("cost_type", result)
