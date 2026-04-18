#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the TenantSettingsSerializer."""
from django.test import TestCase

from api.settings.serializers import TenantSettingsSerializer
from reporting.tenant_settings.models import TenantSettings


class TenantSettingsSerializerTest(TestCase):
    """Tests for the TenantSettingsSerializer."""

    def test_valid_min(self):
        """Minimum allowed value passes validation."""
        serializer = TenantSettingsSerializer(data={"data_retention_months": TenantSettings.MIN_RETENTION_MONTHS})
        self.assertTrue(serializer.is_valid())

    def test_valid_max(self):
        """Maximum allowed value passes validation."""
        serializer = TenantSettingsSerializer(data={"data_retention_months": TenantSettings.MAX_RETENTION_MONTHS})
        self.assertTrue(serializer.is_valid())

    def test_valid_mid_range(self):
        """A typical mid-range value passes."""
        serializer = TenantSettingsSerializer(data={"data_retention_months": 24})
        self.assertTrue(serializer.is_valid())

    def test_below_min_invalid(self):
        """Below-minimum value fails validation."""
        serializer = TenantSettingsSerializer(data={"data_retention_months": 2})
        self.assertFalse(serializer.is_valid())
        self.assertIn("data_retention_months", serializer.errors)

    def test_above_max_invalid(self):
        """Above-maximum value fails validation."""
        serializer = TenantSettingsSerializer(data={"data_retention_months": 121})
        self.assertFalse(serializer.is_valid())
        self.assertIn("data_retention_months", serializer.errors)

    def test_missing_field_invalid(self):
        """Empty payload fails validation."""
        serializer = TenantSettingsSerializer(data={})
        self.assertFalse(serializer.is_valid())
        self.assertIn("data_retention_months", serializer.errors)

    def test_non_integer_invalid(self):
        """Non-integer value fails validation."""
        serializer = TenantSettingsSerializer(data={"data_retention_months": "abc"})
        self.assertFalse(serializer.is_valid())

    def test_float_invalid(self):
        """Float value fails validation."""
        serializer = TenantSettingsSerializer(data={"data_retention_months": 6.5})
        self.assertFalse(serializer.is_valid())

    def test_negative_invalid(self):
        """Negative value fails validation."""
        serializer = TenantSettingsSerializer(data={"data_retention_months": -1})
        self.assertFalse(serializer.is_valid())

    def test_zero_invalid(self):
        """Zero fails validation (below min of 3)."""
        serializer = TenantSettingsSerializer(data={"data_retention_months": 0})
        self.assertFalse(serializer.is_valid())
