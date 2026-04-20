#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the MonthlyExchangeRate and CurrencyConfig models."""
from datetime import date
from decimal import Decimal

from django.db import IntegrityError
from django_tenants.utils import tenant_context

from cost_models.models import CurrencyConfig
from cost_models.models import MonthlyExchangeRate
from cost_models.models import RateType
from masu.test import MasuTestCase


class MonthlyExchangeRateTest(MasuTestCase):
    """Tests for MonthlyExchangeRate model."""

    def test_create_dynamic_rate(self):
        """Test creating a dynamic exchange rate."""
        with tenant_context(self.tenant):
            rate = MonthlyExchangeRate.objects.create(
                effective_date=date(2026, 1, 1),
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.870000000000000"),
                rate_type=RateType.DYNAMIC,
            )
            self.assertEqual(rate.base_currency, "USD")
            self.assertEqual(rate.target_currency, "EUR")
            self.assertEqual(rate.rate_type, RateType.DYNAMIC)

    def test_create_static_rate(self):
        """Test creating a static exchange rate."""
        with tenant_context(self.tenant):
            rate = MonthlyExchangeRate.objects.create(
                effective_date=date(2026, 1, 1),
                base_currency="USD",
                target_currency="GBP",
                exchange_rate=Decimal("0.780000000000000"),
                rate_type=RateType.STATIC,
            )
            self.assertEqual(rate.rate_type, RateType.STATIC)

    def test_unique_together_constraint(self):
        """Test that duplicate (effective_date, base, target) raises IntegrityError."""
        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.create(
                effective_date=date(2026, 2, 1),
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.870000000000000"),
                rate_type=RateType.DYNAMIC,
            )
            with self.assertRaises(IntegrityError):
                MonthlyExchangeRate.objects.create(
                    effective_date=date(2026, 2, 1),
                    base_currency="USD",
                    target_currency="EUR",
                    exchange_rate=Decimal("0.890000000000000"),
                    rate_type=RateType.STATIC,
                )

    def test_update_or_create_overwrites_dynamic_with_static(self):
        """Test that static rate overwrites dynamic for the same triple."""
        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.create(
                effective_date=date(2026, 3, 1),
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.870000000000000"),
                rate_type=RateType.DYNAMIC,
            )
            MonthlyExchangeRate.objects.update_or_create(
                effective_date=date(2026, 3, 1),
                base_currency="USD",
                target_currency="EUR",
                defaults={
                    "exchange_rate": Decimal("0.920000000000000"),
                    "rate_type": RateType.STATIC,
                },
            )
            rate = MonthlyExchangeRate.objects.get(
                effective_date=date(2026, 3, 1),
                base_currency="USD",
                target_currency="EUR",
            )
            self.assertEqual(rate.rate_type, RateType.STATIC)
            self.assertEqual(rate.exchange_rate, Decimal("0.920000000000000"))


class CurrencyConfigTest(MasuTestCase):
    """Tests for CurrencyConfig model."""

    def test_create_disabled_currency(self):
        """Test creating a disabled currency entry."""
        with tenant_context(self.tenant):
            CurrencyConfig.objects.all().delete()
            ec = CurrencyConfig.objects.create(currency_code="JPY", enabled=False)
            self.assertEqual(ec.currency_code, "JPY")
            self.assertFalse(ec.enabled)

    def test_enable_currency(self):
        """Test enabling a currency."""
        with tenant_context(self.tenant):
            CurrencyConfig.objects.all().delete()
            ec = CurrencyConfig.objects.create(currency_code="GBP", enabled=False)
            ec.enabled = True
            ec.save()
            ec.refresh_from_db()
            self.assertTrue(ec.enabled)

    def test_unique_currency_code(self):
        """Test that duplicate currency codes raise IntegrityError."""
        with tenant_context(self.tenant):
            CurrencyConfig.objects.all().delete()
            CurrencyConfig.objects.create(currency_code="CNY", enabled=False)
            with self.assertRaises(IntegrityError):
                CurrencyConfig.objects.create(currency_code="CNY", enabled=True)
