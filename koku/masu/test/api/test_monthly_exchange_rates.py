#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the monthly_exchange_rates endpoint view."""
from unittest.mock import patch

from django.test.utils import override_settings
from django.urls import reverse

from masu.test import MasuTestCase


@override_settings(ROOT_URLCONF="masu.urls")
class MonthlyExchangeRatesTest(MasuTestCase):
    """Test Cases for the monthly_exchange_rates endpoint."""

    @patch("koku.middleware.MASU", return_value=True)
    def test_missing_schema_returns_400(self, _):
        """Test that omitting the schema parameter returns 400."""
        response = self.client.get(reverse("monthly_exchange_rates"))
        self.assertEqual(response.status_code, 400)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_rates(self, _):
        """Test the endpoint returns 200 with valid schema."""
        response = self.client.get(reverse("monthly_exchange_rates"), {"schema": self.schema})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("count", body)
        self.assertIn("rates", body)
