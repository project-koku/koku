#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for feature flags module."""
from unittest.mock import Mock

from django.test import TestCase

from koku.feature_flags import DisabledUnleashClient


class DisabledUnleashClientTest(TestCase):
    """Test DisabledUnleashClient for on-prem deployments."""

    def setUp(self):
        """Set up test client."""
        self.client = DisabledUnleashClient()

    def test_has_unleash_instance_id_attribute(self):
        """Test that client has the expected instance_id attribute."""
        self.assertEqual(self.client.unleash_instance_id, "disabled-unleash-client")

    def test_is_enabled_with_fallback_returning_true(self):
        """Test that is_enabled returns True when fallback returns True."""
        # Arrange
        fallback = Mock(return_value=True)
        
        # Act
        result = self.client.is_enabled("test-feature", fallback_function=fallback)
        
        # Assert
        self.assertTrue(result)
        fallback.assert_called_once_with("test-feature", {})

    def test_is_enabled_with_fallback_returning_false(self):
        """Test that is_enabled returns False when fallback returns False."""
        # Arrange
        fallback = Mock(return_value=False)
        
        # Act
        result = self.client.is_enabled("test-feature", fallback_function=fallback)
        
        # Assert
        self.assertFalse(result)
        fallback.assert_called_once_with("test-feature", {})

    def test_is_enabled_without_fallback_returns_false(self):
        """Test that is_enabled returns False (safe default) without fallback."""
        # Act
        result = self.client.is_enabled("test-feature")
        
        # Assert
        self.assertFalse(result, "Should return False when no fallback provided")

    def test_is_enabled_passes_context_to_fallback(self):
        """Test that is_enabled passes context dict to fallback function."""
        # Arrange
        fallback = Mock(return_value=True)
        context = {"enabled": True, "user": "test"}
        
        # Act
        result = self.client.is_enabled("test-feature", context=context, fallback_function=fallback)
        
        # Assert
        self.assertTrue(result)
        fallback.assert_called_once_with("test-feature", context)

    def test_is_enabled_converts_none_context_to_empty_dict(self):
        """Test that is_enabled converts None context to empty dict."""
        # Arrange
        fallback = Mock(return_value=True)
        
        # Act
        result = self.client.is_enabled("test-feature", context=None, fallback_function=fallback)
        
        # Assert
        self.assertTrue(result)
        fallback.assert_called_once_with("test-feature", {})

    def test_is_enabled_with_context_aware_fallback(self):
        """Test that fallback can access context data."""
        # Arrange
        def context_aware_fallback(feature_name, context):
            return context.get("enabled", False)
        
        # Act & Assert - context with enabled=True
        result = self.client.is_enabled(
            "test-feature",
            context={"enabled": True},
            fallback_function=context_aware_fallback
        )
        self.assertTrue(result)
        
    def test_is_enabled_with_context_aware_fallback_disabled(self):
        """Test that fallback respects context data when disabled."""
        # Arrange
        def context_aware_fallback(feature_name, context):
            return context.get("enabled", False)
        
        # Act & Assert - context with enabled=False
        result = self.client.is_enabled(
            "test-feature",
            context={"enabled": False},
            fallback_function=context_aware_fallback
        )
        self.assertFalse(result)

    def test_initialize_client_does_not_raise_exception(self):
        """Test that initialize_client is a no-op and doesn't raise."""
        # Act & Assert
        try:
            self.client.initialize_client()
        except Exception as e:
            self.fail(f"initialize_client() raised {type(e).__name__}: {e}")

    def test_destroy_does_not_raise_exception(self):
        """Test that destroy is a no-op and doesn't raise."""
        # Act & Assert
        try:
            self.client.destroy()
        except Exception as e:
            self.fail(f"destroy() raised {type(e).__name__}: {e}")

    def test_feature_name_passed_to_fallback(self):
        """Test that feature name is correctly passed to fallback."""
        # Arrange
        fallback = Mock(return_value=True)
        feature_name = "custom-feature-flag"
        
        # Act
        self.client.is_enabled(feature_name, fallback_function=fallback)
        
        # Assert
        fallback.assert_called_once()
        args = fallback.call_args[0]
        self.assertEqual(args[0], feature_name)
