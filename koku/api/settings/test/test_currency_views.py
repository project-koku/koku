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
from cost_models.models import CostModel
from cost_models.models import EnabledCurrency
from cost_models.models import PriceList


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
            EnabledCurrency.objects.create(currency_code="CHF")
            EnabledCurrency.objects.create(currency_code="JPY")

            response = self.client.delete(self._url("CHF"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertFalse(EnabledCurrency.objects.filter(currency_code="CHF").exists())
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="JPY").exists())

    def test_enable_is_idempotent(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            response = self.client.post(self._url("USD"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(EnabledCurrency.objects.filter(currency_code="USD").count(), 1)

    def test_disable_is_idempotent(self):
        with tenant_context(self.tenant):
            response = self.client.delete(self._url("CHF"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertFalse(EnabledCurrency.objects.filter(currency_code="CHF").exists())

    def test_post_invalid_currency_code(self):
        response = self.client.post(self._url("INVALID"), **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_disable_last_currency_returns_400(self):
        """Deleting the only enabled currency should return 400."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            response = self.client.delete(self._url("USD"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="USD").exists())

    def test_disable_currency_in_use_by_cost_model_blocked(self):
        """Disabling a currency referenced by a CostModel must return 400."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="GBP")
            CostModel.objects.create(
                name="GBP Cost Model",
                description="test",
                source_type="OCP",
                rates={},
                markup={},
                currency="GBP",
            )

            response = self.client.delete(self._url("GBP"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="GBP").exists())
            error = response.data["errors"][0]
            self.assertIn("cost model", error["detail"])
            self.assertEqual(len(error["affected_cost_models"]), 1)
            self.assertEqual(error["affected_price_lists"], [])

    def test_disable_currency_in_use_by_price_list_blocked(self):
        """Disabling a currency referenced by a PriceList must return 400."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="EUR")
            PriceList.objects.create(
                name="EUR Price List",
                description="test",
                currency="EUR",
                effective_start_date="2026-01-01",
                effective_end_date="2026-12-31",
                rates=[],
            )

            response = self.client.delete(self._url("EUR"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="EUR").exists())
            error = response.data["errors"][0]
            self.assertIn("price list", error["detail"])
            self.assertEqual(error["affected_cost_models"], [])
            self.assertEqual(len(error["affected_price_lists"]), 1)

    def test_disable_default_currency_blocked(self):
        """Disabling the system default currency (USD) must return 400."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="GBP")

            response = self.client.delete(self._url("USD"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="USD").exists())
            error_detail = str(response.data["errors"][0]["detail"])
            self.assertIn("system default currency", error_detail)

    def test_disable_user_default_currency_blocked(self):
        """Disabling a currency set as a user's default display currency must return 400."""
        from reporting.user_settings.models import UserSettings

        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="GBP")
            UserSettings.objects.create(settings={"currency": "GBP"})

            response = self.client.delete(self._url("GBP"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="GBP").exists())
            error_detail = str(response.data["errors"][0]["detail"])
            self.assertIn("user's default display currency", error_detail)
