#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for EnabledCurrency views."""
from django.urls import reverse
from django_tenants.utils import tenant_context
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from cost_models.models import EnabledCurrency


class EnabledCurrencyConfigViewTest(IamTestCase):
    """Tests for EnabledCurrencyConfigView (POST settings/currency/config/)."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.url = reverse("currency-config")

    def test_post_sets_enabled_currencies(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            data = {"currencies": ["USD", "EUR", "GBP"]}
            response = self.client.post(self.url, data=data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertEqual(EnabledCurrency.objects.count(), 3)
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="USD").exists())
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="EUR").exists())
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="GBP").exists())

    def test_post_replaces_existing(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="JPY")
            data = {"currencies": ["USD"]}
            response = self.client.post(self.url, data=data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertEqual(EnabledCurrency.objects.count(), 1)
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="USD").exists())
            self.assertFalse(EnabledCurrency.objects.filter(currency_code="JPY").exists())

    def test_post_empty_list_clears_all(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")
            data = {"currencies": []}
            response = self.client.post(self.url, data=data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertEqual(EnabledCurrency.objects.count(), 0)

    def test_post_invalid_currency_code(self):
        data = {"currencies": ["INVALID"]}
        response = self.client.post(self.url, data=data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_normalizes_to_uppercase(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            data = {"currencies": ["usd", "eur"]}
            response = self.client.post(self.url, data=data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="USD").exists())
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="EUR").exists())


class AllCurrencyViewTest(IamTestCase):
    """Tests for AllCurrencyView (GET settings/currency/)."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.url = reverse("all-currencies")

    def test_get_all_currencies_with_enabled_flag(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="EUR")

        response = self.client.get(self.url + "?limit=500", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertGreater(len(data), 100)

        usd = next(c for c in data if c["code"] == "USD")
        eur = next(c for c in data if c["code"] == "EUR")
        gbp = next(c for c in data if c["code"] == "GBP")
        self.assertTrue(usd["enabled"])
        self.assertTrue(eur["enabled"])
        self.assertFalse(gbp["enabled"])

    def test_get_all_currencies_none_enabled(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()

        response = self.client.get(self.url + "?limit=500", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertTrue(all(not c["enabled"] for c in data))
