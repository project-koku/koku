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
    """Tests for EnabledCurrencyView (PUT settings/currency/<code>/)."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def _url(self, code):
        return reverse("currency-config", kwargs={"code": code})

    def test_put_enables_currency(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            response = self.client.put(self._url("USD"), data={"enabled": True}, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="USD").exists())

    def test_put_disables_currency(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")
            response = self.client.put(self._url("USD"), data={"enabled": False}, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertFalse(EnabledCurrency.objects.filter(currency_code="USD").exists())

    def test_put_enable_is_idempotent(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")
            response = self.client.put(self._url("USD"), data={"enabled": True}, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertEqual(EnabledCurrency.objects.filter(currency_code="USD").count(), 1)

    def test_put_disable_is_idempotent(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            response = self.client.put(self._url("USD"), data={"enabled": False}, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertFalse(EnabledCurrency.objects.filter(currency_code="USD").exists())

    def test_put_does_not_affect_other_currencies(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="EUR")
            EnabledCurrency.objects.create(currency_code="GBP")
            response = self.client.put(self._url("USD"), data={"enabled": True}, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="EUR").exists())
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="GBP").exists())
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="USD").exists())

    def test_put_invalid_currency_code(self):
        response = self.client.put(self._url("INVALID"), data={"enabled": True}, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_normalizes_to_uppercase(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            response = self.client.put(self._url("usd"), data={"enabled": True}, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="USD").exists())


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
