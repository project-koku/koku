#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for EnabledCurrency and AvailableCurrency views."""
from django.urls import reverse
from django_tenants.utils import tenant_context
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from cost_models.models import EnabledCurrency
from cost_models.models import StaticExchangeRate


class EnabledCurrencyViewTest(IamTestCase):
    """Tests for EnabledCurrencyView."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(user=self.request_context["request"].user)
        self.url = reverse("enabled-currencies")

    def test_get_enabled_currencies_empty(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_enabled_currencies(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD", enabled=True)
            EnabledCurrency.objects.create(currency_code="EUR", enabled=False)
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_put_enable_currencies(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="GBP", enabled=False)
            data = {"currencies": [{"currency_code": "GBP", "enabled": True}]}
            response = self.client.put(self.url, data=data, format="json")
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertTrue(EnabledCurrency.objects.get(currency_code="GBP").enabled)

    def test_put_creates_new_currency(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            data = {"currencies": [{"currency_code": "JPY", "enabled": True}]}
            response = self.client.put(self.url, data=data, format="json")
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="JPY", enabled=True).exists())


class AvailableCurrencyViewTest(IamTestCase):
    """Tests for AvailableCurrencyView."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(user=self.request_context["request"].user)
        self.url = reverse("available-currencies")

    def test_get_available_currencies_dynamic_only(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            StaticExchangeRate.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD", enabled=True)
            EnabledCurrency.objects.create(currency_code="EUR", enabled=True)
            EnabledCurrency.objects.create(currency_code="GBP", enabled=False)
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            codes = [c["currency_code"] for c in response.data["data"]]
            self.assertIn("USD", codes)
            self.assertIn("EUR", codes)
            self.assertNotIn("GBP", codes)

    def test_get_available_currencies_static_included(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            StaticExchangeRate.objects.all().delete()
            StaticExchangeRate.objects.create(
                base_currency="EUR",
                target_currency="CHF",
                exchange_rate="1.080000000000000",
                start_date="2026-01-01",
                end_date="2026-01-31",
            )
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            codes = [c["currency_code"] for c in response.data["data"]]
            self.assertIn("EUR", codes)
            self.assertIn("CHF", codes)

    def test_get_available_currencies_empty(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            StaticExchangeRate.objects.all().delete()
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(response.data["data"]), 0)
