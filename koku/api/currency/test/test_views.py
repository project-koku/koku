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

    def test_returns_only_enabled_currencies(self):
        """Test that GET returns enabled currencies and excludes non-enabled ones."""
        url = reverse("currency")
        client = APIClient()

        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        codes = [c["code"] for c in response.data["data"]]
        self.assertIn("USD", codes)
        self.assertNotIn("GBP", codes)
