#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for EnabledCurrency views."""
from decimal import Decimal
from unittest.mock import patch

from django.urls import reverse
from django_tenants.utils import tenant_context
from rest_framework import status
from rest_framework.test import APIClient

from api.currency.models import ExchangeRateDictionary
from api.iam.test.iam_test_case import IamTestCase
from cost_models.models import EnabledCurrency


class EnabledCurrencyDetailViewTest(IamTestCase):
    """Tests for POST/DELETE on settings/currency/enabled-currencies/<code>/."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def _url(self, code):
        return reverse("enabled-currencies-detail", kwargs={"code": code})

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

    @patch("api.currency.utils.settings")
    def test_post_returns_warning_when_no_dynamic_rate(self, mock_settings):
        """When CURRENCY_URL is set but the currency has no dynamic rate, return a warning."""
        mock_settings.CURRENCY_URL = "https://example.com/rates"
        ExchangeRateDictionary.objects.all().delete()
        ExchangeRateDictionary.objects.create(
            currency_exchange_dictionary={
                "USD": {"USD": Decimal(1), "EUR": Decimal("0.92")},
                "EUR": {"USD": Decimal("1.087"), "EUR": Decimal(1)},
            }
        )
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            response = self.client.post(self._url("JPY"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertIn("warning", response.data)
            self.assertIn("JPY", response.data["warning"])
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="JPY").exists())

    @patch("api.currency.utils.settings")
    def test_post_returns_warning_when_no_exchange_data(self, mock_settings):
        """When CURRENCY_URL is set but ExchangeRateDictionary is empty, return a warning."""
        mock_settings.CURRENCY_URL = "https://example.com/rates"
        ExchangeRateDictionary.objects.all().delete()
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            response = self.client.post(self._url("EUR"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertIn("warning", response.data)
            self.assertIn("static rate", response.data["warning"])

    @patch("api.currency.utils.settings")
    def test_post_no_warning_when_dynamic_rate_exists(self, mock_settings):
        """When CURRENCY_URL is set and the currency has a dynamic rate, no warning."""
        mock_settings.CURRENCY_URL = "https://example.com/rates"
        ExchangeRateDictionary.objects.all().delete()
        ExchangeRateDictionary.objects.create(
            currency_exchange_dictionary={
                "USD": {"USD": Decimal(1), "EUR": Decimal("0.92")},
                "EUR": {"USD": Decimal("1.087"), "EUR": Decimal(1)},
            }
        )
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            response = self.client.post(self._url("EUR"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertIsNone(response.data["warning"])

    @patch("api.currency.utils.settings")
    def test_post_no_warning_when_currency_url_not_configured(self, mock_settings):
        """When CURRENCY_URL is None (on-prem default), no warning."""
        mock_settings.CURRENCY_URL = None
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            response = self.client.post(self._url("JPY"), **self.headers)
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
            "USD": {"code": "USD", "name": "US Dollar", "symbol": "$", "description": "USD ($) - US Dollar"},
            "EUR": {"code": "EUR", "name": "Euro", "symbol": "\u20ac", "description": "EUR (\u20ac) - Euro"},
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

    def test_get_returns_empty_list_when_none_enabled(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            response = self.client.get(self.url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["data"], [])
