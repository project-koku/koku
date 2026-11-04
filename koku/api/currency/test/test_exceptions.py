#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for currency-related exceptions."""
from datetime import date

from django.test import override_settings
from django.test import SimpleTestCase

from api.currency.exceptions import ExchangeRateNotFound


class ExchangeRateNotFoundTest(SimpleTestCase):
    """Tests for ExchangeRateNotFound detail text."""

    @override_settings(CURRENCY_URL="https://exchange-rates.example/v6/latest/USD")
    def test_detail_explains_preferred_currency_is_target_when_currency_url_set(self):
        """Missing-rate detail names the target and requires source -> preferred rates."""
        exc = ExchangeRateNotFound(
            ["USD", "EUR"],
            "KPW",
            date(2026, 10, 1),
            date(2026, 10, 1),
        )
        detail = exc.detail["currency"]
        self.assertEqual(
            detail,
            "No exchange rate available to convert costs into KPW for USD -> KPW, EUR -> KPW "
            "for 2026-10-01 to 2026-10-01. Costs are stored in the source currency; preferred "
            "currency is the conversion target. Ask your administrator to configure static "
            "exchange rates for each missing source -> KPW pair (the reverse direction is not used).",
        )

    @override_settings(CURRENCY_URL="")
    def test_detail_mentions_dynamic_rates_when_currency_url_unset(self):
        """Without CURRENCY_URL, the message also suggests enabling dynamic rates."""
        exc = ExchangeRateNotFound(["USD"], "EUR", date(2026, 1, 1), date(2026, 3, 31))
        detail = exc.detail["currency"]
        self.assertIn("to convert costs into EUR", detail)
        self.assertIn("source -> EUR pair (the reverse direction is not used)", detail)
        self.assertTrue(detail.endswith(" or enable dynamic exchange rates."))

    @override_settings(CURRENCY_URL="https://exchange-rates.example/v6/latest/USD")
    def test_missing_months_detail_explains_preferred_currency_is_target(self):
        """Month-gap detail uses the same target-currency explanation."""
        exc = ExchangeRateNotFound(
            ["USD"],
            "KPW",
            date(2026, 1, 1),
            date(2026, 3, 31),
            missing_months={date(2026, 2, 1)},
        )
        detail = exc.detail["currency"]
        self.assertTrue(
            detail.startswith("Exchange rate missing to convert costs into KPW for USD -> KPW for months: 2026-02.")
        )
        self.assertIn("preferred currency is the conversion target", detail)
        self.assertIn("source -> KPW pair (the reverse direction is not used).", detail)
