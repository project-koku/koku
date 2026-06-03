#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the StaticExchangeRate ViewSet."""
import calendar
from datetime import date
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from django.urls import reverse
from django.utils import timezone
from django_tenants.utils import tenant_context
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from cost_models.models import EnabledCurrency
from cost_models.models import StaticExchangeRate


class StaticExchangeRateViewSetTest(IamTestCase):
    """Tests for StaticExchangeRateViewSet."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.list_url = reverse("currency-list")
        self.create_url = reverse("exchange-rate-create")
        today = timezone.now().date()
        current_month_start = today.replace(day=1)
        end_month = current_month_start + relativedelta(months=2)
        end_day = calendar.monthrange(end_month.year, end_month.month)[1]
        self.valid_data = {
            "base_currency": "USD",
            "target_currency": "EUR",
            "exchange_rate": "0.870000000000000",
            "start_date": str(current_month_start),
            "end_date": str(date(end_month.year, end_month.month, end_day)),
        }

    def _past_data(self):
        """Return valid_data with dates set to a past billing period (2 months ago to last month)."""
        today = timezone.now().date()
        start = today.replace(day=1) - relativedelta(months=2)
        end_month = today.replace(day=1) - relativedelta(months=1)
        end = date(end_month.year, end_month.month, calendar.monthrange(end_month.year, end_month.month)[1])
        data = self.valid_data.copy()
        data["start_date"] = str(start)
        data["end_date"] = str(end)
        return data

    @patch("cost_models.static_exchange_rate_serializer.invalidate_view_cache_for_tenant_and_all_source_types")
    def test_create_current_allowed_past_blocked(self, mock_invalidate):
        """Test that create succeeds for current month but is blocked for past periods."""
        with tenant_context(self.tenant):
            response = self.client.post(self.create_url, data=self.valid_data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            data = response.data
            self.assertEqual(data["base_currency"], "USD")
            self.assertEqual(data["target_currency"], "EUR")
            self.assertEqual(data["name"], "USD-EUR")

            response = self.client.post(self.create_url, data=self._past_data(), format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("cost_models.static_exchange_rate_serializer.invalidate_view_cache_for_tenant_and_all_source_types")
    def test_list_returns_grouped_by_currency(self, mock_invalidate):
        """Test that GET list returns exchange rates grouped by base currency with enabled flag."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            StaticExchangeRate.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")
            self.client.post(self.create_url, data=self.valid_data, format="json", **self.headers)

            response = self.client.get(self.list_url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            data = response.data["data"]
            usd_entry = next(e for e in data if e["code"] == "USD")
            self.assertEqual(usd_entry["enabled"], True)
            self.assertIn("name", usd_entry)
            self.assertIn("symbol", usd_entry)
            self.assertEqual(len(usd_entry["exchange_rates"]), 1)

            rate = usd_entry["exchange_rates"][0]
            self.assertEqual(rate["base_currency"], "USD")
            self.assertEqual(rate["target_currency"], "EUR")
            self.assertIn("uuid", rate)

    @patch("cost_models.static_exchange_rate_serializer.invalidate_view_cache_for_tenant_and_all_source_types")
    def test_list_disabled_currency_shows_enabled_false(self, mock_invalidate):
        """Test that a currency without EnabledCurrency row shows enabled=False."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            StaticExchangeRate.objects.all().delete()
            self.client.post(self.create_url, data=self.valid_data, format="json", **self.headers)

            response = self.client.get(self.list_url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            usd_entry = next(e for e in response.data["data"] if e["code"] == "USD")
            self.assertEqual(usd_entry["enabled"], False)

    @patch("cost_models.static_exchange_rate_serializer.invalidate_view_cache_for_tenant_and_all_source_types")
    def test_update_current_allowed_past_blocked(self, mock_invalidate):
        """Test that update succeeds for current month but is blocked for past periods."""
        with tenant_context(self.tenant):
            create_response = self.client.post(self.create_url, data=self.valid_data, format="json", **self.headers)
            uuid = create_response.data["uuid"]
            detail_url = reverse("exchange-rate-detail", kwargs={"uuid": uuid})

            update_data = self.valid_data.copy()
            update_data["exchange_rate"] = "0.900000000000000"
            response = self.client.put(detail_url, data=update_data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            response = self.client.put(detail_url, data=self._past_data(), format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("cost_models.static_exchange_rate_serializer.invalidate_view_cache_for_tenant_and_all_source_types")
    @patch("cost_models.static_exchange_rate_view.invalidate_view_cache_for_tenant_and_all_source_types")
    def test_delete_current_allowed_past_blocked(self, mock_invalidate_view, mock_invalidate_ser):
        """Test that delete succeeds for current month rates but is blocked for past periods."""
        with tenant_context(self.tenant):
            create_response = self.client.post(self.create_url, data=self.valid_data, format="json", **self.headers)
            uuid = create_response.data["uuid"]
            detail_url = reverse("exchange-rate-detail", kwargs={"uuid": uuid})
            response = self.client.delete(detail_url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertFalse(StaticExchangeRate.objects.filter(uuid=uuid).exists())

            past_data = self._past_data()
            past_rate = StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="CAD",
                exchange_rate="1.350000000000000",
                start_date=past_data["start_date"],
                end_date=past_data["end_date"],
            )
            detail_url = reverse("exchange-rate-detail", kwargs={"uuid": past_rate.uuid})
            response = self.client.delete(detail_url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertTrue(StaticExchangeRate.objects.filter(uuid=past_rate.uuid).exists())

    def test_create_invalid_currency(self):
        """Test creating with invalid currency code returns 400."""
        with tenant_context(self.tenant):
            data = self.valid_data.copy()
            data["base_currency"] = "FAKE"
            response = self.client.post(self.create_url, data=data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_mid_month_start_date(self):
        """Test creating with non-first-of-month start_date returns 400."""
        with tenant_context(self.tenant):
            today = timezone.now().date()
            mid_month = today.replace(day=15)
            data = self.valid_data.copy()
            data["start_date"] = str(mid_month)
            response = self.client.post(self.create_url, data=data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_returns_all_iso_currencies(self):
        """Test that GET list returns all ISO 4217 currencies, not just those with rates."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            StaticExchangeRate.objects.all().delete()
            response = self.client.get(self.list_url, {"limit": 1000}, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.data["data"]
            codes = [c["code"] for c in data]
            self.assertIn("USD", codes)
            self.assertIn("EUR", codes)
            self.assertIn("JPY", codes)
            self.assertGreater(len(codes), 100)

    def test_list_search_filters_by_code_or_name(self):
        """Test that ?search= filters currencies by code or name."""
        with tenant_context(self.tenant):
            response = self.client.get(self.list_url, {"search": "eur", "limit": 1000}, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.data["data"]
            codes = [c["code"] for c in data]
            self.assertIn("EUR", codes)
            for entry in data:
                self.assertTrue(
                    "eur" in entry["code"].lower() or "eur" in entry["name"].lower(),
                    f"{entry['code']} should not match 'eur'",
                )

    def test_list_enabled_filter(self):
        """Test that ?enabled=true returns only enabled currencies."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="EUR")
            response = self.client.get(self.list_url, {"enabled": "true", "limit": 1000}, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.data["data"]
            codes = [c["code"] for c in data]
            self.assertEqual(sorted(codes), ["EUR", "USD"])
            for entry in data:
                self.assertTrue(entry["enabled"])
