#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for currency settings views."""
import calendar
import csv
import io
from datetime import date
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.core.cache import caches
from django.test import SimpleTestCase
from django.test.utils import override_settings
from django.urls import reverse
from django_tenants.utils import tenant_context
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_csv.renderers import CSVRenderer

from api.currency.currencies import get_enabled_currency_codes
from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.settings.currency_views import ACTIVE_RATE_TYPE_DYNAMIC
from api.settings.currency_views import ACTIVE_RATE_TYPE_NONE
from api.settings.currency_views import ACTIVE_RATE_TYPE_STATIC
from api.settings.currency_views import compute_active_rate_type
from api.settings.currency_views import CSV_STATIC_RATE_FIELDS
from cost_models.models import CostModel
from cost_models.models import EnabledCurrency
from cost_models.models import PriceList
from cost_models.models import StaticExchangeRate
from koku.cache import build_enabled_currency_codes_key
from koku.cache import CacheEnum
from koku.cache import get_value_from_cache
from reporting.provider.aws.models import AWSCostSummaryP
from reporting.provider.azure.models import AzureCostSummaryP
from reporting.provider.gcp.models import GCPCostSummaryP
from reporting.provider.models import TenantAPIProvider
from reporting.user_settings.models import UserSettings


def _month_end(d):
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


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


class ActiveRateTypeHelperTest(SimpleTestCase):
    """Unit tests for compute_active_rate_type vs a fixed UTC month."""

    def test_disabled_is_none_even_with_static_and_dynamic(self):
        self.assertEqual(
            compute_active_rate_type(
                enabled=False,
                has_dynamic_rate=True,
                static_rates=[{"start_date": date(2026, 10, 1), "end_date": date(2026, 10, 31)}],
                month_start=date(2026, 10, 1),
                month_end=date(2026, 10, 31),
            ),
            ACTIVE_RATE_TYPE_NONE,
        )

    def test_static_wins_over_dynamic_when_window_overlaps_month(self):
        self.assertEqual(
            compute_active_rate_type(
                enabled=True,
                has_dynamic_rate=True,
                static_rates=[{"start_date": "2026-09-01", "end_date": "2026-12-31"}],
                month_start=date(2026, 10, 1),
                month_end=date(2026, 10, 31),
            ),
            ACTIVE_RATE_TYPE_STATIC,
        )

    def test_dynamic_when_enabled_without_covering_static(self):
        self.assertEqual(
            compute_active_rate_type(
                enabled=True,
                has_dynamic_rate=True,
                static_rates=[{"start_date": date(2026, 8, 1), "end_date": date(2026, 8, 31)}],
                month_start=date(2026, 10, 1),
                month_end=date(2026, 10, 31),
            ),
            ACTIVE_RATE_TYPE_DYNAMIC,
        )

    def test_none_when_enabled_without_static_or_dynamic(self):
        self.assertEqual(
            compute_active_rate_type(
                enabled=True,
                has_dynamic_rate=False,
                static_rates=[],
                month_start=date(2026, 10, 1),
                month_end=date(2026, 10, 31),
            ),
            ACTIVE_RATE_TYPE_NONE,
        )


class CurrencySettingsViewTest(IamTestCase):
    """Tests for GET settings/currency/."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()

    def _assert_codes_match_filter_terms(self, codes, terms):
        terms_upper = [term.upper() for term in terms]
        for code in codes:
            self.assertTrue(
                any(term in code for term in terms_upper),
                msg=f"{code} does not match any filter term in {terms_upper}",
            )

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

    def test_list_excludes_xxx_and_withdrawn_currencies(self):
        """Settings catalog omits XXX and withdrawn codes like FRF when not enabled."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")

        url = reverse("currency-list") + "?limit=500"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [c["code"] for c in response.data["data"]]
        self.assertNotIn("XXX", codes)
        self.assertNotIn("FRF", codes)
        self.assertIn("USD", codes)
        self.assertIn("EUR", codes)

    def test_list_includes_already_enabled_inactive_currency(self):
        """Legacy enabled withdrawn currencies still appear with enabled=true."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="FRF")

        url = reverse("currency-list") + "?filter[enabled]=true&limit=500"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes_by_key = {c["code"]: c for c in response.data["data"]}
        self.assertIn("FRF", codes_by_key)
        self.assertTrue(codes_by_key["FRF"]["enabled"])

    def test_list_filter_enabled_true(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")

        url = reverse("currency-list") + "?filter[enabled]=true&limit=500"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [c["code"] for c in response.data["data"]]
        self.assertEqual(codes, ["USD"])

    def test_list_filter_enabled_false(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")

        url = reverse("currency-list") + "?filter[enabled]=false&limit=500"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [c["code"] for c in response.data["data"]]
        self.assertNotIn("USD", codes)
        self.assertFalse(any(c["enabled"] for c in response.data["data"]))

    def test_list_filter_by_currency_substring_match(self):
        url = reverse("currency-list") + "?filter[currency]=USD&limit=500"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [c["code"] for c in response.data["data"]]
        self.assertIn("USD", codes)
        self._assert_codes_match_filter_terms(codes, ["USD"])

        partial_url = reverse("currency-list") + "?filter[currency]=US&limit=500"
        partial_response = self.client.get(partial_url, **self.headers)
        self.assertEqual(partial_response.status_code, status.HTTP_200_OK)
        partial_codes = [c["code"] for c in partial_response.data["data"]]
        self.assertIn("USD", partial_codes)

    def test_list_filter_by_currency_no_match_returns_empty(self):
        url = reverse("currency-list") + "?filter[currency]=ZZZ"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"], [])

    def test_list_filter_by_multiple_currencies_csv(self):
        url = reverse("currency-list") + "?filter[currency]=USD,EUR&limit=500"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [c["code"] for c in response.data["data"]]
        self.assertIn("USD", codes)
        self.assertIn("EUR", codes)
        self._assert_codes_match_filter_terms(codes, ["USD", "EUR"])

    def test_list_filter_by_multiple_currencies_repeated(self):
        url = reverse("currency-list") + "?filter[currency]=USD&filter[currency]=EUR&limit=500"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [c["code"] for c in response.data["data"]]
        self.assertIn("USD", codes)
        self.assertIn("EUR", codes)
        self._assert_codes_match_filter_terms(codes, ["USD", "EUR"])

    def test_list_filter_by_multiple_currencies_partial_or(self):
        url = reverse("currency-list") + "?filter[currency]=US&filter[currency]=GB&limit=500"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [c["code"] for c in response.data["data"]]
        self.assertIn("USD", codes)
        self.assertIn("GBP", codes)
        self._assert_codes_match_filter_terms(codes, ["US", "GB"])

    def test_list_filter_by_currency_case_insensitive(self):
        url = reverse("currency-list") + "?filter[currency]=usd&limit=500"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [c["code"] for c in response.data["data"]]
        self.assertIn("USD", codes)
        self._assert_codes_match_filter_terms(codes, ["USD"])

    def test_list_filter_enabled_and_currency_combined(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="EUR")

        url = reverse("currency-list") + "?filter[enabled]=true&filter[currency]=USD&filter[currency]=GBP&limit=500"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [c["code"] for c in response.data["data"]]
        self.assertEqual(codes, ["USD"])

    def test_list_legacy_enabled_param_rejected(self):
        url = reverse("currency-list") + "?enabled=true"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_legacy_search_param_rejected(self):
        url = reverse("currency-list") + "?search=USD"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_invalid_filter_key_rejected(self):
        url = reverse("currency-list") + "?filter[invalid_field]=USD"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_invalid_filter_enabled_value_rejected(self):
        url = reverse("currency-list") + "?filter[enabled]=maybe"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_csv_export_returns_flat_static_rates(self):
        """Accept: text/csv returns flat static rates, not nested currency catalog."""
        month_start = date.today().replace(day=1)
        month_end = _month_end(month_start)
        with tenant_context(self.tenant):
            rate = StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.920000000000000"),
                start_date=month_start,
                end_date=month_end,
            )

        client = APIClient(HTTP_ACCEPT="text/csv")
        url = reverse("currency-list")
        response = client.get(url, content_type="text/csv", **self.headers)
        response.render()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.accepted_media_type, "text/csv")
        self.assertIsInstance(response.accepted_renderer, CSVRenderer)

        rows = list(csv.DictReader(io.StringIO(response.content.decode())))
        self.assertEqual(len(rows), 1)
        self.assertEqual(list(rows[0].keys()), list(CSV_STATIC_RATE_FIELDS))
        row = rows[0]
        self.assertEqual(row["base_currency"], "USD")
        self.assertEqual(row["target_currency"], "EUR")
        # CSV stringifies the Decimal representation from the serializer.
        self.assertEqual(Decimal(row["exchange_rate"]), Decimal("0.92"))
        self.assertEqual(row["start_date"], month_start.isoformat())
        self.assertEqual(row["end_date"], month_end.isoformat())
        self.assertEqual(row["uuid"], str(rate.uuid))
        self.assertEqual(row["name"], "USD-EUR")

    def test_list_csv_export_ignores_pagination(self):
        """CSV export returns all matching rates even when limit would truncate JSON."""
        month_start = date.today().replace(day=1)
        month_end = _month_end(month_start)
        targets = ("EUR", "GBP", "JPY")
        with tenant_context(self.tenant):
            for target in targets:
                StaticExchangeRate.objects.create(
                    base_currency="USD",
                    target_currency=target,
                    exchange_rate=Decimal("1.000000000000000"),
                    start_date=month_start,
                    end_date=month_end,
                )

        client = APIClient(HTTP_ACCEPT="text/csv")
        url = reverse("currency-list") + "?limit=1"
        response = client.get(url, content_type="text/csv", **self.headers)
        response.render()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = list(csv.DictReader(io.StringIO(response.content.decode())))
        self.assertEqual(len(rows), 3)
        self.assertEqual({row["target_currency"] for row in rows}, set(targets))

    def test_list_csv_export_empty_when_no_static_rates(self):
        """CSV with no static rates still returns 200, text/csv, and column headers."""
        client = APIClient(HTTP_ACCEPT="text/csv")
        url = reverse("currency-list")
        response = client.get(url, content_type="text/csv", **self.headers)
        response.render()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.accepted_media_type, "text/csv")
        reader = csv.reader(io.StringIO(response.content.decode()))
        header = next(reader)
        self.assertEqual(header, list(CSV_STATIC_RATE_FIELDS))
        self.assertEqual(list(reader), [])

    def test_list_json_preferred_when_accept_lists_json_before_csv(self):
        """Mixed Accept with JSON first keeps the nested currency catalog shape."""
        month_start = date.today().replace(day=1)
        month_end = _month_end(month_start)
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.920000000000000"),
                start_date=month_start,
                end_date=month_end,
            )

        client = APIClient(HTTP_ACCEPT="application/json, text/csv")
        url = reverse("currency-list") + "?filter[currency]=USD&limit=500"
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("application/json", response.accepted_media_type)
        data = response.data["data"]
        self.assertEqual(data[0]["code"], "USD")
        self.assertIn("static_rates", data[0])
        self.assertEqual(data[0]["static_rates"][0]["target_currency"], "EUR")

    def test_list_csv_export_filter_enabled_true(self):
        """CSV filter[enabled]=true keeps rates whose base currency is enabled."""
        month_start = date.today().replace(day=1)
        month_end = _month_end(month_start)
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.920000000000000"),
                start_date=month_start,
                end_date=month_end,
            )
            StaticExchangeRate.objects.create(
                base_currency="GBP",
                target_currency="EUR",
                exchange_rate=Decimal("1.100000000000000"),
                start_date=month_start,
                end_date=month_end,
            )

        client = APIClient(HTTP_ACCEPT="text/csv")
        url = reverse("currency-list") + "?filter[enabled]=true"
        response = client.get(url, content_type="text/csv", **self.headers)
        response.render()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = response.content.decode()
        self.assertIn("USD", content)
        self.assertIn("EUR", content)
        self.assertNotIn("GBP", content)

    def test_list_csv_export_filter_enabled_false(self):
        """CSV filter[enabled]=false keeps rates whose base currency is disabled."""
        month_start = date.today().replace(day=1)
        month_end = _month_end(month_start)
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.920000000000000"),
                start_date=month_start,
                end_date=month_end,
            )
            StaticExchangeRate.objects.create(
                base_currency="GBP",
                target_currency="EUR",
                exchange_rate=Decimal("1.100000000000000"),
                start_date=month_start,
                end_date=month_end,
            )

        client = APIClient(HTTP_ACCEPT="text/csv")
        url = reverse("currency-list") + "?filter[enabled]=false"
        response = client.get(url, content_type="text/csv", **self.headers)
        response.render()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = response.content.decode()
        self.assertIn("GBP", content)
        self.assertNotIn("USD", content)

    def test_list_csv_export_filter_by_currency(self):
        """CSV filter[currency] matches base or target currency codes."""
        month_start = date.today().replace(day=1)
        month_end = _month_end(month_start)
        with tenant_context(self.tenant):
            StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.920000000000000"),
                start_date=month_start,
                end_date=month_end,
            )
            StaticExchangeRate.objects.create(
                base_currency="GBP",
                target_currency="JPY",
                exchange_rate=Decimal("180.000000000000"),
                start_date=month_start,
                end_date=month_end,
            )

        client = APIClient(HTTP_ACCEPT="text/csv")
        url = reverse("currency-list") + "?filter[currency]=GBP"
        response = client.get(url, content_type="text/csv", **self.headers)
        response.render()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = response.content.decode()
        self.assertIn("GBP", content)
        self.assertIn("JPY", content)
        self.assertNotIn("USD", content)
        self.assertNotIn("EUR", content)

    def test_list_json_accept_unchanged_with_static_rates(self):
        """application/json still returns the nested currency catalog shape."""
        month_start = date.today().replace(day=1)
        month_end = _month_end(month_start)
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.920000000000000"),
                start_date=month_start,
                end_date=month_end,
            )

        url = reverse("currency-list") + "?filter[currency]=USD&limit=500"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["code"], "USD")
        self.assertIn("static_rates", data[0])
        self.assertEqual(len(data[0]["static_rates"]), 1)
        self.assertEqual(data[0]["static_rates"][0]["target_currency"], "EUR")

    def _utc_month_bounds(self):
        today = datetime.now(timezone.utc).date()
        month_start = today.replace(day=1)
        month_end = _month_end(month_start)
        return month_start, month_end

    def test_active_rate_type_none_when_currency_disabled(self):
        """Disabled currencies return none even when static and dynamic exist."""
        month_start, month_end = self._utc_month_bounds()
        with tenant_context(self.tenant):
            StaticExchangeRate.objects.all().delete()
            StaticExchangeRate.objects.create(
                base_currency="CHF",
                target_currency="EUR",
                exchange_rate=Decimal("0.920000000000000"),
                start_date=month_start,
                end_date=month_end,
            )

        url = reverse("currency-list") + "?filter[currency]=CHF&limit=500"
        with patch("api.settings.currency_views.get_dynamic_rate_currencies", return_value={"chf"}):
            response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        chf = next(item for item in response.data["data"] if item["code"] == "CHF")
        self.assertFalse(chf["enabled"])
        self.assertEqual(chf["active_rate_type"], ACTIVE_RATE_TYPE_NONE)

    def test_active_rate_type_static_when_static_covers_current_month(self):
        """Current-month static override wins over dynamic."""
        month_start, month_end = self._utc_month_bounds()
        with tenant_context(self.tenant):
            StaticExchangeRate.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")
            StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.920000000000000"),
                start_date=month_start,
                end_date=month_end,
            )

        url = reverse("currency-list") + "?filter[currency]=USD&limit=500"
        with patch("api.settings.currency_views.get_dynamic_rate_currencies", return_value={"usd"}):
            response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        usd = next(item for item in response.data["data"] if item["code"] == "USD")
        self.assertTrue(usd["enabled"])
        self.assertTrue(usd["has_dynamic_rate"])
        self.assertEqual(usd["active_rate_type"], ACTIVE_RATE_TYPE_STATIC)

    def test_active_rate_type_dynamic_when_enabled_no_static_override(self):
        """Enabled with dynamic and no current-month static returns dynamic."""
        with tenant_context(self.tenant):
            StaticExchangeRate.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")

        url = reverse("currency-list") + "?filter[currency]=USD&limit=500"
        with patch("api.settings.currency_views.get_dynamic_rate_currencies", return_value={"usd"}):
            response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        usd = next(item for item in response.data["data"] if item["code"] == "USD")
        self.assertTrue(usd["enabled"])
        self.assertTrue(usd["has_dynamic_rate"])
        self.assertEqual(usd["active_rate_type"], ACTIVE_RATE_TYPE_DYNAMIC)

    def test_active_rate_type_none_when_enabled_without_static_or_dynamic(self):
        """Enabled with no rate path returns none; UI uses enabled to tell it from disabled."""
        with tenant_context(self.tenant):
            StaticExchangeRate.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="CHF")

        url = reverse("currency-list") + "?filter[currency]=CHF&limit=500"
        with patch("api.settings.currency_views.get_dynamic_rate_currencies", return_value=set()):
            response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        chf = next(item for item in response.data["data"] if item["code"] == "CHF")
        self.assertTrue(chf["enabled"])
        self.assertFalse(chf["has_dynamic_rate"])
        self.assertEqual(chf["active_rate_type"], ACTIVE_RATE_TYPE_NONE)

    def test_active_rate_type_ignores_static_outside_current_month(self):
        """Past or future static windows do not count as the active rate this month."""
        _, month_end = self._utc_month_bounds()
        next_month_start = month_end + timedelta(days=1)
        next_month_end = _month_end(next_month_start)
        with tenant_context(self.tenant):
            StaticExchangeRate.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")
            StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.920000000000000"),
                start_date=date(2020, 1, 1),
                end_date=date(2020, 1, 31),
            )
            StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="GBP",
                exchange_rate=Decimal("0.790000000000000"),
                start_date=next_month_start,
                end_date=next_month_end,
            )

        url = reverse("currency-list") + "?filter[currency]=USD&limit=500"
        with patch("api.settings.currency_views.get_dynamic_rate_currencies", return_value={"usd"}):
            response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        usd = next(item for item in response.data["data"] if item["code"] == "USD")
        self.assertEqual(usd["active_rate_type"], ACTIVE_RATE_TYPE_DYNAMIC)

    def test_list_all_currencies_sorted_by_code_ascending(self):
        """Unfiltered list is A-Z by code (not enabled-first then disabled)."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="EUR")

        url = reverse("currency-list") + "?limit=500"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [c["code"] for c in response.data["data"]]
        self.assertEqual(codes, sorted(codes))
        # Enabled currencies appear in alphabetical position (not enabled-first)
        self.assertIn("USD", codes)
        self.assertIn("EUR", codes)
        self.assertLess(codes.index("EUR"), codes.index("USD"))
        codes_by_key = {c["code"]: c for c in response.data["data"]}
        self.assertTrue(codes_by_key["USD"]["enabled"])
        self.assertTrue(codes_by_key["EUR"]["enabled"])
        self.assertFalse(codes_by_key["GBP"]["enabled"])

    def test_list_order_by_code_desc(self):
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")

        url = reverse("currency-list") + "?order_by[code]=desc&limit=500"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [c["code"] for c in response.data["data"]]
        self.assertEqual(codes, sorted(codes, reverse=True))

    def test_list_invalid_order_by_rejected(self):
        url = reverse("currency-list") + "?order_by[name]=asc"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        url = reverse("currency-list") + "?order_by[code]=sideways"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_is_disableable_true_for_free_enabled_currency(self):
        """A freely enabled currency with no dependencies returns is_disableable=True."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="CHF")

        url = reverse("currency-list") + "?filter[currency]=CHF"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        chf = response.data["data"][0]
        self.assertTrue(chf["is_disableable"])

    def test_is_disableable_true_for_disabled_currency(self):
        """A disabled currency with no dependencies returns is_disableable=True.

        The Settings UI uses this flag for the enable/disable toggle; it must
        stay True after disable so the user can re-enable the currency.
        """
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")

        url = reverse("currency-list") + "?filter[currency]=CHF"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        chf = response.data["data"][0]
        self.assertFalse(chf["enabled"])
        self.assertTrue(chf["is_disableable"])

    @override_settings(KOKU_DEFAULT_CURRENCY="USD")
    def test_is_disableable_false_for_system_default_currency(self):
        """System default currency returns is_disableable=False."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="CHF")

        url = reverse("currency-list") + "?filter[currency]=USD"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        usd = response.data["data"][0]
        self.assertFalse(usd["is_disableable"])

    @override_settings(KOKU_DEFAULT_CURRENCY="USD")
    def test_is_disableable_true_for_disabled_system_default_currency(self):
        """Disabled system default returns is_disableable=True so the UI can re-enable it."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="CHF")

        url = reverse("currency-list") + "?filter[currency]=USD"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        usd = response.data["data"][0]
        self.assertFalse(usd["enabled"])
        self.assertTrue(usd["is_disableable"])

    def test_is_disableable_false_when_only_one_enabled(self):
        """The sole enabled currency returns is_disableable=False."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="CHF")

        url = reverse("currency-list") + "?filter[currency]=CHF"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        chf = response.data["data"][0]
        self.assertFalse(chf["is_disableable"])

    def test_is_disableable_false_for_currency_used_by_cost_model(self):
        """Currency used by a CostModel returns is_disableable=False."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="GBP")
            CostModel.objects.create(
                name="GBP Model",
                description="test",
                source_type="OCP",
                rates={},
                markup={},
                currency="GBP",
            )

        url = reverse("currency-list") + "?filter[currency]=GBP"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        gbp = response.data["data"][0]
        self.assertFalse(gbp["is_disableable"])

    def test_is_disableable_false_for_currency_used_by_price_list(self):
        """Currency used by a PriceList returns is_disableable=False."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="EUR")
            PriceList.objects.create(
                name="EUR PL",
                description="test",
                currency="EUR",
                effective_start_date="2026-01-01",
                effective_end_date="2026-12-31",
                rates=[],
            )

        url = reverse("currency-list") + "?filter[currency]=EUR"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        eur = response.data["data"][0]
        self.assertFalse(eur["is_disableable"])

    def test_is_disableable_false_for_account_default_currency(self):
        """Account default currency (UserSettings) returns is_disableable=False."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="NOK")
            UserSettings.objects.all().delete()
            UserSettings.objects.create(settings={"currency": "NOK"})

        url = reverse("currency-list") + "?filter[currency]=NOK"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        nok = response.data["data"][0]
        self.assertFalse(nok["is_disableable"])

    def test_is_disableable_true_for_disabled_account_default_currency(self):
        """Disabled account default returns is_disableable=True so the UI can re-enable it."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            UserSettings.objects.all().delete()
            UserSettings.objects.create(settings={"currency": "NOK"})

        url = reverse("currency-list") + "?filter[currency]=NOK"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        nok = response.data["data"][0]
        self.assertFalse(nok["enabled"])
        self.assertTrue(nok["is_disableable"])

    def test_is_disableable_false_for_cloud_provider_base_currencies(self):
        """Currencies used by cloud billing summary data return is_disableable=False."""
        cloud_providers = [
            (Provider.PROVIDER_AWS, AWSCostSummaryP, "currency_code", "AUD"),
            (Provider.PROVIDER_AZURE, AzureCostSummaryP, "currency", "CAD"),
            (Provider.PROVIDER_GCP, GCPCostSummaryP, "currency", "NZD"),
        ]
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            for provider_type, summary_model, currency_field, code in cloud_providers:
                EnabledCurrency.objects.create(currency_code=code)

        for provider_type, summary_model, currency_field, code in cloud_providers:
            provider = Provider.objects.create(
                name=f"{provider_type} {code}",
                type=provider_type,
                customer=self.customer,
            )
            with tenant_context(self.tenant):
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

        for _, _, _, code in cloud_providers:
            with self.subTest(code=code):
                url = reverse("currency-list") + f"?filter[currency]={code}"
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                entry = response.data["data"][0]
                self.assertFalse(entry["is_disableable"], f"{code} should not be disableable")


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

    def test_post_enable_rejects_inactive_currency(self):
        """POST must reject inactive / non-tender codes such as XXX."""
        with tenant_context(self.tenant):
            response = self.client.post(self._url("XXX"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(EnabledCurrency.objects.filter(currency_code="XXX").exists())

    def test_delete_allows_disabling_already_enabled_inactive_currency(self):
        """Already-enabled withdrawn currencies remain disableable via DELETE."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="FRF")

            response = self.client.delete(self._url("FRF"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertFalse(EnabledCurrency.objects.filter(currency_code="FRF").exists())
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
        for provider_type, summary_model, currency_field, code in cloud_providers:
            provider = Provider.objects.create(
                name=f"{provider_type} {code} Source",
                type=provider_type,
                customer=self.customer,
            )
            with tenant_context(self.tenant):
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

        with tenant_context(self.tenant):
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
        with tenant_context(self.tenant):
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="GBP")
            UserSettings.objects.all().delete()
            UserSettings.objects.create(settings={"currency": "GBP"})

            response = self.client.delete(self._url("GBP"), **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertTrue(EnabledCurrency.objects.filter(currency_code="GBP").exists())
