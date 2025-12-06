#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.currency.currencies import CURRENCIES
from api.iam.test.iam_test_case import IamTestCase


class CurrencyViewTest(IamTestCase):
    """Tests for the currency view."""

    def test_supported_currencies(self):
        """Test that a list GET call returns the supported currencies."""
        qs = "?limit=25"
        url = reverse("currency") + qs
        client = APIClient()

        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        self.assertEqual(data.get("data"), CURRENCIES)
