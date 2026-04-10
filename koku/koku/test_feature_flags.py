#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for MockUnleashClient ONPREM flag defaults."""
from unittest import TestCase

from koku.feature_flags import fallback_development_true
from koku.feature_flags import MockUnleashClient


class MockUnleashClientTest(TestCase):
    """Test MockUnleashClient behavior."""

    def setUp(self):
        self.client = MockUnleashClient(
            app_name="Cost Management",
            environment="development",
            instance_id="test-instance",
        )

    def test_onprem_gpu_flag_returns_true(self):
        """Override map returns True for ocp_gpu_cost_model regardless of fallback."""
        result = self.client.is_enabled("cost-management.backend.ocp_gpu_cost_model")
        self.assertTrue(result)

    def test_onprem_ingress_rate_limit_flag_returns_true(self):
        """Override map returns True for disable-ingress-rate-limit."""
        result = self.client.is_enabled("cost-management.backend.disable-ingress-rate-limit")
        self.assertTrue(result)

    def test_onprem_group_by_limit_flag_returns_true(self):
        """Override map returns True for override_customer_group_by_limit."""
        result = self.client.is_enabled("cost-management.backend.override_customer_group_by_limit")
        self.assertTrue(result)

    def test_override_takes_precedence_over_fallback(self):
        """Override map is checked before the fallback function."""

        def always_false(name, ctx):
            return False

        result = self.client.is_enabled(
            "cost-management.backend.ocp_gpu_cost_model",
            fallback_function=always_false,
        )
        self.assertTrue(result)

    def test_unlisted_flag_with_fallback_uses_fallback(self):
        """Flags not in the override map still delegate to fallback_function."""
        result = self.client.is_enabled(
            "cost-management.backend.some-other-flag",
            fallback_function=fallback_development_true,
        )
        self.assertTrue(result)

    def test_unlisted_flag_without_fallback_returns_false(self):
        """Flags not in the override map and with no fallback return False."""
        result = self.client.is_enabled("cost-management.backend.some-other-flag")
        self.assertFalse(result)

    def test_unlisted_flag_non_development_fallback_returns_false(self):
        """fallback_development_true returns False when environment is not development."""
        client = MockUnleashClient(
            app_name="Cost Management",
            environment="production",
            instance_id="test-instance",
        )
        result = client.is_enabled(
            "cost-management.backend.some-other-flag",
            fallback_function=fallback_development_true,
        )
        self.assertFalse(result)

    def test_context_merging_preserved_for_unlisted_flags(self):
        """Runtime context is merged with static context for unlisted flags."""
        captured = {}

        def capture_fallback(name, ctx):
            captured.update(ctx)
            return True

        self.client.is_enabled(
            "cost-management.backend.some-other-flag",
            context={"schema": "org1234567"},
            fallback_function=capture_fallback,
        )
        self.assertEqual(captured["appName"], "Cost Management")
        self.assertEqual(captured["environment"], "development")
        self.assertEqual(captured["schema"], "org1234567")

    def test_initialize_client_is_noop(self):
        """initialize_client does not raise."""
        self.client.initialize_client()

    def test_destroy_is_noop(self):
        """destroy does not raise."""
        self.client.destroy()
