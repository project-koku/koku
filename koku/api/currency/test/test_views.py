#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from unittest.mock import patch

from django.urls import reverse
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from api.currency.models import ExchangeRateDictionary
from api.iam.test.iam_test_case import IamTestCase
from cost_models.models import EnabledCurrency


class CurrencyViewTest(IamTestCase):
    """Tests for the currency view."""

    def setUp(self):
        super().setUp()
        with schema_context(self.schema_name):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")

    def test_returns_only_enabled_currencies(self):
        """Test that GET returns enabled currencies and excludes non-enabled ones."""
        qs = "?limit=25"
        url = reverse("currency") + qs
        client = APIClient()

        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        codes = [c["code"] for c in response.data["data"]]
        self.assertIn("USD", codes)
        self.assertNotIn("GBP", codes)

    @patch("masu.celery.tasks.get_daily_currency_rates")
    def test_get_exchange_rates_returns_404_when_dictionary_missing(self, mock_fetch):
        """When no ExchangeRateDictionary exists after fetch, return 404 instead of AttributeError."""
        ExchangeRateDictionary.objects.all().delete()
        mock_fetch.return_value = {}

        response = APIClient().get(reverse("exchange-rates"), **self.headers)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("No exchange rates are available", response.data["detail"])
        mock_fetch.assert_called_once()

    def test_get_exchange_rates_returns_dictionary(self):
        """When ExchangeRateDictionary exists, return its payload."""
        ExchangeRateDictionary.objects.all().delete()
        ExchangeRateDictionary.objects.create(currency_exchange_dictionary={"USD": {"EUR": 0.9}})

        response = APIClient().get(reverse("exchange-rates"), **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"USD": {"EUR": 0.9}})
