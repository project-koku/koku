#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the StaticExchangeRate ViewSet."""
from unittest.mock import patch

from django.urls import reverse
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
        self.list_url = reverse("exchange-rate-list")
        self.valid_data = {
            "base_currency": "USD",
            "target_currency": "EUR",
            "exchange_rate": "0.870000000000000",
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
        }

    @patch("cost_models.static_exchange_rate_serializer.invalidate_view_cache_for_tenant_and_all_source_types")
    def test_create_static_rate(self, mock_invalidate):
        """Test creating a static exchange rate via API."""
        with tenant_context(self.tenant):
            response = self.client.post(self.list_url, data=self.valid_data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            data = response.data
            self.assertEqual(data["base_currency"], "USD")
            self.assertEqual(data["target_currency"], "EUR")
            self.assertEqual(data["name"], "USD-EUR")

    @patch("cost_models.static_exchange_rate_serializer.invalidate_view_cache_for_tenant_and_all_source_types")
    def test_list_returns_grouped_by_currency(self, mock_invalidate):
        """Test that GET list returns exchange rates grouped by target currency with enabled flag."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="EUR")
            self.client.post(self.list_url, data=self.valid_data, format="json", **self.headers)

            response = self.client.get(self.list_url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            data = response.data["data"]
            self.assertEqual(len(data), 1)

            eur_entry = data[0]
            self.assertEqual(eur_entry["code"], "EUR")
            self.assertEqual(eur_entry["enabled"], True)
            self.assertIn("name", eur_entry)
            self.assertIn("symbol", eur_entry)
            self.assertEqual(len(eur_entry["exchange_rates"]), 1)

            rate = eur_entry["exchange_rates"][0]
            self.assertEqual(rate["base_currency"], "USD")
            self.assertEqual(rate["target_currency"], "EUR")
            self.assertIn("uuid", rate)

    @patch("cost_models.static_exchange_rate_serializer.invalidate_view_cache_for_tenant_and_all_source_types")
    def test_list_disabled_currency_shows_enabled_false(self, mock_invalidate):
        """Test that a currency without EnabledCurrency row shows enabled=False."""
        with tenant_context(self.tenant):
            EnabledCurrency.objects.filter(currency_code="EUR").delete()
            self.client.post(self.list_url, data=self.valid_data, format="json", **self.headers)

            response = self.client.get(self.list_url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            eur_entry = response.data["data"][0]
            self.assertEqual(eur_entry["code"], "EUR")
            self.assertEqual(eur_entry["enabled"], False)

    @patch("cost_models.static_exchange_rate_serializer.invalidate_view_cache_for_tenant_and_all_source_types")
    def test_update_static_rate(self, mock_invalidate):
        """Test updating a static exchange rate via PUT."""
        with tenant_context(self.tenant):
            create_response = self.client.post(self.list_url, data=self.valid_data, format="json", **self.headers)
            uuid = create_response.data["uuid"]
            detail_url = reverse("exchange-rate-detail", kwargs={"uuid": uuid})

            update_data = self.valid_data.copy()
            update_data["exchange_rate"] = "0.900000000000000"
            response = self.client.put(detail_url, data=update_data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("cost_models.static_exchange_rate_serializer.invalidate_view_cache_for_tenant_and_all_source_types")
    def test_delete_static_rate(self, mock_invalidate):
        """Test deleting a static exchange rate."""
        with tenant_context(self.tenant):
            create_response = self.client.post(self.list_url, data=self.valid_data, format="json", **self.headers)
            uuid = create_response.data["uuid"]
            detail_url = reverse("exchange-rate-detail", kwargs={"uuid": uuid})
            response = self.client.delete(detail_url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertFalse(StaticExchangeRate.objects.filter(uuid=uuid).exists())

    def test_create_invalid_currency(self):
        """Test creating with invalid currency code returns 400."""
        with tenant_context(self.tenant):
            data = self.valid_data.copy()
            data["base_currency"] = "FAKE"
            response = self.client.post(self.list_url, data=data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_mid_month_start_date(self):
        """Test creating with non-first-of-month start_date returns 400."""
        with tenant_context(self.tenant):
            data = self.valid_data.copy()
            data["start_date"] = "2026-01-15"
            response = self.client.post(self.list_url, data=data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_by_base_currency(self):
        """Test filtering by base_currency query parameter."""
        with tenant_context(self.tenant):
            response = self.client.get(self.list_url, {"base_currency": "USD"}, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
