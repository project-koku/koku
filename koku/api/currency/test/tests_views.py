#
# Copyright 2021 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Test the Metrics views."""
import json
from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.currency.view import CURRENCY_FILE_NAME
from api.currency.view import load_currencies
from api.iam.test.iam_test_case import IamTestCase


class CurrencyViewTest(IamTestCase):
    """Tests for the metrics view."""

    def test_supported_currencies(self):
        """Test that a list GET call returns the supported currencies."""
        qs = "?limit=20"
        url = reverse("currency") + qs
        client = APIClient()

        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        with open(CURRENCY_FILE_NAME) as api_file:
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
        data = load_currencies(CURRENCY_FILE_NAME)
        with open(CURRENCY_FILE_NAME) as api_file:
            expected = json.load(api_file)
        self.assertEqual(data, expected)

    def test_load_currencies_fnf(self):
        """Test file not found load_currencies."""
        with self.assertRaises(FileNotFoundError):
            load_currencies("doesnotexist.json")
