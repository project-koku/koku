#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the EnabledCurrency model."""
from django.db import IntegrityError
from django_tenants.utils import tenant_context

from cost_models.models import EnabledCurrency
from masu.test import MasuTestCase


class EnabledCurrencyTest(MasuTestCase):
    """Tests for EnabledCurrency model."""

    def test_create_enabled_currency(self):
        """Test creating an enabled currency entry."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            ec = EnabledCurrency.objects.create(currency_code="JPY")
            self.assertEqual(ec.currency_code, "JPY")

    def test_unique_currency_code(self):
        """Test that duplicate currency codes raise IntegrityError."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="CNY")
            with self.assertRaises(IntegrityError):
                EnabledCurrency.objects.create(currency_code="CNY")
