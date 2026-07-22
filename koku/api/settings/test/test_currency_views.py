#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for currency settings views."""
from uuid import uuid4

from django.core.cache import caches
from django.test.utils import override_settings
from django.urls import reverse
from django_tenants.utils import tenant_context
from rest_framework import status
from rest_framework.test import APIClient

from api.currency.currencies import get_enabled_currency_codes
from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from cost_models.models import CostModel
from cost_models.models import EnabledCurrency
from cost_models.models import PriceList
from koku.cache import build_enabled_currency_codes_key
from koku.cache import CacheEnum
from koku.cache import get_value_from_cache
from reporting.provider.aws.models import AWSCostSummaryP
from reporting.provider.azure.models import AzureCostSummaryP
from reporting.provider.gcp.models import GCPCostSummaryP
from reporting.provider.models import TenantAPIProvider


CACHE_OVERRIDE = {
    CacheEnum.default: {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake-currency-views-default",
        "KEY_FUNCTION": "django_tenants.cache.make_key",
        "REVERSE_KEY_FUNCTION": "django_tenants.cache.reverse_key",
    },
    CacheEnum.api: {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake-currency-views-api",
        "KEY_FUNCTION": "django_tenants.cache.make_key",
        "REVERSE_KEY_FUNCTION": "django_tenants.cache.reverse_key",
    },
    # rbac/worker are untouched by this test but must stay defined so middleware
    # that reads them (e.g. RBAC lookups) doesn't blow up when CACHES is overridden.
    CacheEnum.rbac: {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
        "LOCATION": "unique-snowflake",
    },
    CacheEnum.worker: {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",
    },
}


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

    @override_settings(CACHES=CACHE_OVERRIDE)
    def test_enable_currency_invalidates_enabled_codes_cache(self):
        """Enabling a currency should invalidate the cached enabled-codes set."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            get_enabled_currency_codes()
            cache_key = build_enabled_currency_codes_key(self.schema_name)
            self.assertEqual(set(get_value_from_cache(cache_key)), {"USD"})

            response = self.client.post(self._url("CHF"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.assertIsNone(get_value_from_cache(cache_key))
            self.assertEqual(get_enabled_currency_codes(), {"USD", "CHF"})

        caches[CacheEnum.default].clear()
        caches[CacheEnum.api].clear()

    @override_settings(CACHES=CACHE_OVERRIDE)
    def test_disable_currency_invalidates_enabled_codes_cache(self):
        """Disabling a currency should invalidate the cached enabled-codes set."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="CHF")
            get_enabled_currency_codes()
            cache_key = build_enabled_currency_codes_key(self.schema_name)
            self.assertEqual(set(get_value_from_cache(cache_key)), {"USD", "CHF"})

            response = self.client.delete(self._url("CHF"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

            self.assertIsNone(get_value_from_cache(cache_key))
            self.assertEqual(get_enabled_currency_codes(), {"USD"})

        caches[CacheEnum.default].clear()
        caches[CacheEnum.api].clear()

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

    def test_disable_currency_in_use_by_cloud_provider_blocked(self):
        """Disabling a currency used by AWS, Azure, or GCP providers must return 400."""
        cloud_providers = [
            (Provider.PROVIDER_AWS, AWSCostSummaryP, "currency_code", "AUD"),
            (Provider.PROVIDER_AZURE, AzureCostSummaryP, "currency", "CAD"),
            (Provider.PROVIDER_GCP, GCPCostSummaryP, "currency", "EUR"),
        ]
        with tenant_context(self.tenant):
            for provider_type, summary_model, currency_field, code in cloud_providers:
                provider = Provider.objects.create(
                    name=f"{provider_type} {code} Source",
                    type=provider_type,
                    customer=self.customer,
                )
                tenant_provider = TenantAPIProvider.objects.create(
                    uuid=provider.uuid, name=provider.name, type=provider.type, provider=provider
                )
                summary_model.objects.create(
                    id=uuid4(),
                    usage_start="2026-01-01",
                    usage_end="2026-01-01",
                    source_uuid=tenant_provider,
                    **{currency_field: code},
                )

            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="AUD")
            EnabledCurrency.objects.create(currency_code="CAD")
            EnabledCurrency.objects.create(currency_code="EUR")

            for _, _, _, code in cloud_providers:
                with self.subTest(code=code):
                    response = self.client.delete(self._url(code), **self.headers)
                    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                    self.assertTrue(EnabledCurrency.objects.filter(currency_code=code).exists())

    def test_disable_default_currency_blocked(self):
        """Disabling the system default currency (USD) must return 400."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="GBP")

            response = self.client.delete(self._url("USD"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="USD").exists())

    def test_disable_account_default_currency_blocked(self):
        """Disabling the account default currency must return 400."""
        from reporting.user_settings.models import UserSettings

        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="GBP")
            UserSettings.objects.all().delete()
            UserSettings.objects.create(settings={"currency": "GBP"})

            response = self.client.delete(self._url("GBP"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="GBP").exists())
