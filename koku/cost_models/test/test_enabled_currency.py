#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for CurrencyConfig views."""
from django.urls import reverse
from django_tenants.utils import tenant_context
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from cost_models.models import CurrencyConfig


class CurrencyConfigViewTest(IamTestCase):
    """Tests for CurrencyConfigView."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.url = reverse("enabled-currencies")

    def test_get_enabled_currencies_empty(self):
        with tenant_context(self.tenant):
            CurrencyConfig.objects.all().delete()
            response = self.client.get(self.url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_enabled_currencies(self):
        with tenant_context(self.tenant):
            CurrencyConfig.objects.all().delete()
            CurrencyConfig.objects.create(currency_code="USD", enabled=True)
            CurrencyConfig.objects.create(currency_code="EUR", enabled=False)
            response = self.client.get(self.url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_put_enable_currencies(self):
        with tenant_context(self.tenant):
            CurrencyConfig.objects.all().delete()
            CurrencyConfig.objects.create(currency_code="GBP", enabled=False)
            data = {"currencies": [{"currency_code": "GBP", "enabled": True}]}
            response = self.client.put(self.url, data=data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertTrue(CurrencyConfig.objects.get(currency_code="GBP").enabled)

    def test_put_creates_new_currency(self):
        with tenant_context(self.tenant):
            CurrencyConfig.objects.all().delete()
            data = {"currencies": [{"currency_code": "JPY", "enabled": True}]}
            response = self.client.put(self.url, data=data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertTrue(CurrencyConfig.objects.filter(currency_code="JPY", enabled=True).exists())
