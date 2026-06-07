#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from django.urls import reverse
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from cost_models.models import EnabledCurrency


class CurrencyViewTest(IamTestCase):
    """Tests for the currency view."""

    def setUp(self):
        super().setUp()
        with schema_context(self.schema_name):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")

    def test_supported_currencies(self):
        """Test that GET returns enabled currencies with name, symbol, description."""
        url = reverse("currency")
        client = APIClient()

        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data["data"]
        self.assertEqual(len(data), 1)
        usd = data[0]
        self.assertEqual(usd["code"], "USD")
        self.assertIn("name", usd)
        self.assertIn("symbol", usd)
        self.assertIn("description", usd)

    def test_non_enabled_currencies_excluded(self):
        """Test that currencies not in the EnabledCurrency table do not appear in the response."""
        url = reverse("currency")
        client = APIClient()

        response = client.get(url, **self.headers)
        codes = [c["code"] for c in response.data["data"]]
        self.assertIn("USD", codes)
        self.assertNotIn("GBP", codes)
