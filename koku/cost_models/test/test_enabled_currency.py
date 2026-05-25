#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for EnabledCurrency views."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.urls import reverse
from django_tenants.utils import tenant_context
from rest_framework import status
from rest_framework.test import APIClient

from api.currency.models import ExchangeRates
from api.iam.test.iam_test_case import IamTestCase
from cost_models.models import EnabledCurrency
from cost_models.models import MonthlyExchangeRate
from cost_models.models import RateType


class EnabledCurrencyDetailViewTest(IamTestCase):
    """Tests for POST/DELETE on settings/currency/enabled-currencies/<code>/."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def _url(self, code):
        return reverse("enabled-currencies-detail", kwargs={"code": code})

    def _create_rate(self, target_currency):
        """Helper to create a MonthlyExchangeRate for the given target currency."""
        MonthlyExchangeRate.objects.create(
            effective_date=date(2026, 1, 1),
            base_currency="USD",
            target_currency=target_currency,
            exchange_rate=Decimal("1.000000000000000"),
            rate_type=RateType.STATIC,
        )

    def test_post_enables_currency(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            response = self.client.post(self._url("USD"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="USD").exists())

    def test_delete_disables_currency(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")
            response = self.client.delete(self._url("USD"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertFalse(EnabledCurrency.objects.filter(currency_code="USD").exists())

    def test_post_enable_is_idempotent(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")
            response = self.client.post(self._url("USD"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(EnabledCurrency.objects.filter(currency_code="USD").count(), 1)

    def test_delete_disable_is_idempotent(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            response = self.client.delete(self._url("USD"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertFalse(EnabledCurrency.objects.filter(currency_code="USD").exists())

    def test_post_does_not_affect_other_currencies(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="EUR")
            EnabledCurrency.objects.create(currency_code="GBP")
            response = self.client.post(self._url("USD"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="EUR").exists())
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="GBP").exists())
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="USD").exists())

    def test_post_invalid_currency_code(self):
        response = self.client.post(self._url("INVALID"), **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_normalizes_to_uppercase(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            response = self.client.post(self._url("usd"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="USD").exists())

    def test_get_on_detail_returns_405(self):
        """GET on the detail route (with a code) is not allowed."""
        response = self.client.get(self._url("USD"), **self.headers)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_post_warns_no_rate(self):
        """When no exchange rate exists for the currency, return a warning."""
        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.all().delete()
            EnabledCurrency.objects.all().delete()
            response = self.client.post(self._url("JPY"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertIsNotNone(response.data["warning"])
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="JPY").exists())

    def test_post_no_warning_when_rate_exists(self):
        """No warning when MonthlyExchangeRate has a row for the target currency."""
        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.all().delete()
            self._create_rate("EUR")
            EnabledCurrency.objects.all().delete()
            response = self.client.post(self._url("EUR"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertIsNone(response.data["warning"])


class EnabledCurrencyListViewTest(IamTestCase):
    """Tests for GET on settings/currency/enabled-currencies/."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.url = reverse("enabled-currencies-list")

    @patch(
        "api.settings.currency_views.get_currency_info",
        side_effect=lambda c: {
            "USD": {
                "code": "USD",
                "name": "US Dollar",
                "symbol": "$",
                "description": "USD ($) - US Dollar",
                "has_dynamic_rate": True,
            },
            "EUR": {
                "code": "EUR",
                "name": "Euro",
                "symbol": "\u20ac",
                "description": "EUR (\u20ac) - Euro",
                "has_dynamic_rate": False,
            },
        }[c],
    )
    def test_get_returns_enabled_currencies(self, _mock):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="EUR")
            response = self.client.get(self.url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.data["data"]
            codes = [c["code"] for c in data]
            self.assertEqual(codes, ["EUR", "USD"])
            self.assertEqual(data[0]["name"], "Euro")
            self.assertEqual(data[1]["symbol"], "$")

    def test_get_has_dynamic_rate_flag(self):
        """Test that has_dynamic_rate reflects ExchangeRates table."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="EUR")
            ExchangeRates.objects.all().delete()
            ExchangeRates.objects.create(currency_type="usd", exchange_rate=1.0)
            response = self.client.get(self.url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.data["data"]
            eur_entry = next(c for c in data if c["code"] == "EUR")
            usd_entry = next(c for c in data if c["code"] == "USD")
            self.assertTrue(usd_entry["has_dynamic_rate"])
            self.assertFalse(eur_entry["has_dynamic_rate"])

    def test_get_returns_empty_list_when_none_enabled(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            response = self.client.get(self.url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["data"], [])
