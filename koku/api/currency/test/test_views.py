#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from cost_models.models import EnabledCurrency


class CurrencyViewTest(IamTestCase):
    """Tests for the currency view."""

    def setUp(self):
        super().setUp()
        EnabledCurrency.objects.all().delete()
        EnabledCurrency.objects.create(currency_code="USD", enabled=True)
        EnabledCurrency.objects.create(currency_code="EUR", enabled=True)
        EnabledCurrency.objects.create(currency_code="GBP", enabled=False)

    @patch(
        "api.currency.view.get_currency_info",
        side_effect=lambda c: {
            "USD": {"code": "USD", "name": "US Dollar", "symbol": "$", "description": "USD ($) - US Dollar"},
            "EUR": {"code": "EUR", "name": "Euro", "symbol": "€", "description": "EUR (€) - Euro"},
        }[c],
    )
    def test_supported_currencies(self, _mock_display):
        """Test that GET returns only enabled currencies with name, symbol, description."""
        qs = "?limit=25"
        url = reverse("currency") + qs
        client = APIClient()

        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        expected = [
            {"code": "EUR", "name": "Euro", "symbol": "€", "description": "EUR (€) - Euro"},
            {"code": "USD", "name": "US Dollar", "symbol": "$", "description": "USD ($) - US Dollar"},
        ]
        self.assertEqual(data.get("data"), expected)

    def test_disabled_currencies_excluded(self):
        """Test that disabled currencies do not appear in the response."""
        url = reverse("currency") + "?limit=25"
        client = APIClient()

        response = client.get(url, **self.headers)
        codes = [c["code"] for c in response.data["data"]]
        self.assertNotIn("GBP", codes)
