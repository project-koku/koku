#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Metrics views."""
import json
import os
from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.currency.view import load_currencies
from api.iam.test.iam_test_case import IamTestCase
from koku import settings


test_filename = os.path.join(settings.BASE_DIR, "..", "koku/api/currency/specs/currencies.json")


def read_api_json():
    """Read the openapi.json file out of the docs dir."""
    return load_currencies(test_filename)


class CurrencyViewTest(IamTestCase):
    """Tests for the metrics view."""

    @patch("api.currency.view.load_currencies", return_value=read_api_json())
    def test_supported_currencies(self, _):
        """Test that a list GET call returns the supported currencies."""
        qs = "?limit=20"
        url = reverse("currency") + qs
        client = APIClient()

        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        with open(test_filename) as api_file:
            expected = json.load(api_file)
        self.assertEqual(data.get("data"), expected)

    @patch("api.currency.view.load_currencies")
    def test_supported_currencies_fnf_error(self, currency):
        """Test that a list GET call with a FNF error returns 404."""
        url = reverse("currency")
        client = APIClient()
        currency.side_effect = FileNotFoundError
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_load_currencies(self):
        """Test load currency function happy path."""
        data = load_currencies(test_filename)
        with open(test_filename) as api_file:
            expected = json.load(api_file)
        self.assertEqual(data, expected)

    def test_load_currencies_fnf(self):
        """Test file not found load_currencies."""
        with self.assertRaises(FileNotFoundError):
            load_currencies("doesnotexist.json")
