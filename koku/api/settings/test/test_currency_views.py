#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for currency settings views."""
from django.urls import reverse
from django_tenants.utils import tenant_context
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from cost_models.models import EnabledCurrency


class CurrencySettingsViewTest(IamTestCase):
    """Tests for GET settings/currency/."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()

    def test_list_returns_all_currencies_with_enabled_flag(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")

        url = reverse("currency-list") + "?limit=500"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertGreater(len(data), 100)
        codes_by_key = {c["code"]: c for c in data}
        usd = codes_by_key["USD"]
        gbp = codes_by_key["GBP"]
        self.assertTrue(usd["enabled"])
        self.assertFalse(gbp["enabled"])

    def test_list_filter_enabled_true(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")

        url = reverse("currency-list") + "?enabled=true&limit=500"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [c["code"] for c in response.data["data"]]
        self.assertEqual(codes, ["USD"])

    def test_list_filter_enabled_false(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")

        url = reverse("currency-list") + "?enabled=false&limit=500"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [c["code"] for c in response.data["data"]]
        self.assertNotIn("USD", codes)
        self.assertFalse(any(c["enabled"] for c in response.data["data"]))

    def test_list_search_by_code(self):
        url = reverse("currency-list") + "?search=USD"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [c["code"] for c in response.data["data"]]
        self.assertEqual(codes, ["USD"])


class EnabledCurrencyViewTest(IamTestCase):
    """Tests for POST/DELETE on settings/currency/enabled/<code>/."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()

    def _url(self, code):
        return reverse("currency-enabled-detail", kwargs={"code": code})

    def test_enable_currency(self):
        with tenant_context(self.tenant):
            response = self.client.post(self._url("USD"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="USD").exists())

    def test_disable_currency(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="EUR")

            response = self.client.delete(self._url("USD"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertFalse(EnabledCurrency.objects.filter(currency_code="USD").exists())
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="EUR").exists())

    def test_enable_is_idempotent(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            response = self.client.post(self._url("USD"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(EnabledCurrency.objects.filter(currency_code="USD").count(), 1)

    def test_disable_is_idempotent(self):
        with tenant_context(self.tenant):
            response = self.client.delete(self._url("USD"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertFalse(EnabledCurrency.objects.filter(currency_code="USD").exists())

    def test_post_invalid_currency_code(self):
        response = self.client.post(self._url("INVALID"), **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
