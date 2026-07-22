#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the monthly_exchange_rates endpoint view."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test.utils import override_settings
from django.urls import reverse
from django_tenants.utils import schema_context

from cost_models.models import MonthlyExchangeRate
from cost_models.models import RateType
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
        """Test the endpoint returns 200 with exchange_rate as a JSON number."""
        with schema_context(self.schema):
            MonthlyExchangeRate.objects.create(
                effective_date=date(2026, 1, 1),
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.920000000000000"),
                rate_type=RateType.STATIC,
            )

        response = self.client.get(
            reverse("monthly_exchange_rates"),
            {
                "schema": self.schema,
                "start_date": "2026-01-01",
                "end_date": "2026-06-01",
                "base_currency": "usd",
                "target_currency": "eur",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(len(body["rates"]), 1)
        self.assertIsInstance(body["rates"][0]["exchange_rate"], float)
        self.assertEqual(body["rates"][0]["exchange_rate"], 0.92)

    @patch("koku.middleware.MASU", return_value=True)
    def test_invalid_start_date_returns_400(self, _):
        """Test that an invalid start_date format returns 400."""
        response = self.client.get(
            reverse("monthly_exchange_rates"), {"schema": self.schema, "start_date": "not-a-date"}
        )
        self.assertEqual(response.status_code, 400)

    @patch("koku.middleware.MASU", return_value=True)
    def test_invalid_end_date_returns_400(self, _):
        """Test that an invalid end_date format returns 400."""
        response = self.client.get(
            reverse("monthly_exchange_rates"), {"schema": self.schema, "end_date": "not-a-date"}
        )
        self.assertEqual(response.status_code, 400)

    @patch("koku.middleware.MASU", return_value=True)
    def test_nonexistent_schema_returns_400(self, _):
        """Test that a non-existent schema returns 400 instead of 500."""
        response = self.client.get(reverse("monthly_exchange_rates"), {"schema": "nonexistent"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("does not exist", response.json()["errors"][0]["detail"])
