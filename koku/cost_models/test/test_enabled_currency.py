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


class EnabledCurrencyDetailViewTest(IamTestCase):
    """Tests for POST/DELETE on settings/currency/enabled/<code>/."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def _url(self, code):
        return reverse("currency-enabled-detail", kwargs={"code": code})

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
            EnabledCurrency.objects.create(currency_code="EUR")

            response = self.client.delete(self._url("USD"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertFalse(EnabledCurrency.objects.filter(currency_code="USD").exists())
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="EUR").exists())

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


class CurrencyListViewTest(IamTestCase):
    """Tests for GET settings/currency/."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_list_returns_enabled_currencies(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="EUR")

        url = reverse("currency-list")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [c["code"] for c in response.data["data"]]
        self.assertEqual(codes, ["EUR", "USD"])

    def test_list_search_by_code(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="EUR")
            EnabledCurrency.objects.create(currency_code="GBP")

        url = reverse("currency-list") + "?search=usd"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [c["code"] for c in response.data["data"]]
        self.assertEqual(codes, ["USD"])

    def test_list_empty_when_none_enabled(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()

        url = reverse("currency-list")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"], [])
