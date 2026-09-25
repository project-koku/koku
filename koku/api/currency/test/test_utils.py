#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.db.models import Case
from django_tenants.utils import schema_context

from api.currency.exceptions import ExchangeRateNotFound
from api.currency.models import ExchangeRateDictionary
from api.currency.utils import build_exchange_dictionary
from api.currency.utils import build_exchange_rate_case
from api.currency.utils import exchange_dictionary
from api.currency.utils import get_monthly_exchange_rate
from api.iam.test.iam_test_case import IamTestCase
from cost_models.models import EnabledCurrency
from cost_models.models import MonthlyExchangeRate
from koku.cache import build_enabled_currency_codes_key
from koku.cache import delete_value_from_cache


class CurrencyUtilsTest(IamTestCase):
    """Tests for the currency utils."""

    def setUp(self):
        ExchangeRateDictionary.objects.all().delete()

    def test_build_exchange_dictionary(self):
        """Test that a list GET call returns the supported currencies."""
        expected = {
            "USD": {"USD": Decimal(1.0), "AUD": Decimal(2.0), "CAD": Decimal(1.25)},
            "AUD": {"USD": Decimal(0.5), "AUD": Decimal(1.0), "CAD": Decimal(0.625)},
            "CAD": {"USD": Decimal(0.8), "AUD": Decimal(1.6), "CAD": Decimal(1.0)},
        }

        output = build_exchange_dictionary({"USD": 1, "AUD": 2, "CAD": 1.25})
        self.assertEqual(output, expected)

    def test_exchange_dictionary(self):
        """Test that the exchange rate dict is sent to the DB."""
        exchange_dictionary({"USD": 1, "AUD": 2, "CAD": 1.25})
        exchanged_data = ExchangeRateDictionary.objects.all().first().currency_exchange_dictionary
        self.assertIsNotNone(exchanged_data)

    def test_build_exchange_rate_case_limits_to_provided_bases(self):
        """When clauses are limited to provided bases that exist in ERD."""
        exchange_rates = {
            "USD": {"USD": Decimal("1"), "EUR": Decimal("0.9"), "JPY": Decimal("110")},
            "EUR": {"USD": Decimal("1.1"), "EUR": Decimal("1"), "JPY": Decimal("120")},
            "JPY": {"USD": Decimal("0.009"), "EUR": Decimal("0.008"), "JPY": Decimal("1")},
            "GBP": {"USD": Decimal("1.3"), "EUR": Decimal("1.2"), "JPY": Decimal("140")},
        }
        case = build_exchange_rate_case("raw_currency", "EUR", exchange_rates, base_currencies={"USD", "EUR", "CHF"})
        self.assertIsInstance(case, Case)
        # CHF is enabled-style but absent from ERD; only USD and EUR produce Whens.
        self.assertEqual(len(case.cases), 2)

    def test_build_exchange_rate_case_uses_enabled_currencies_by_default(self):
        """Omitting base_currencies uses the tenant's enabled currency codes."""
        exchange_rates = {
            "USD": {"USD": Decimal("1"), "EUR": Decimal("0.9")},
            "EUR": {"USD": Decimal("1.1"), "EUR": Decimal("1")},
            "JPY": {"USD": Decimal("0.009"), "EUR": Decimal("0.008")},
        }
        with schema_context(self.schema_name):
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="EUR")
            delete_value_from_cache(build_enabled_currency_codes_key(self.schema_name))

            case = build_exchange_rate_case("raw_currency", "EUR", exchange_rates)
            self.assertEqual(len(case.cases), 2)

    @patch("api.currency.utils.get_enabled_currency_codes", return_value={"USD"})
    def test_build_exchange_rate_case_skips_bases_missing_from_erd(self, _):
        """Enabled codes with no ERD entry do not create When clauses."""
        exchange_rates = {"EUR": {"USD": Decimal("1.1"), "EUR": Decimal("1")}}
        case = build_exchange_rate_case("raw_currency", "USD", exchange_rates)
        self.assertEqual(len(case.cases), 0)

    def test_get_monthly_exchange_rate_returns_one_for_same_currency(self):
        """Same base and target currency returns 1 without a DB lookup."""
        self.assertEqual(get_monthly_exchange_rate("USD", "USD", date(2026, 3, 1)), Decimal("1"))

    def test_get_monthly_exchange_rate_returns_rate(self):
        """Returns the MER row for the requested month."""
        with schema_context(self.schema_name):
            MonthlyExchangeRate.objects.create(
                effective_date=date(2026, 3, 1),
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("1.50"),
                rate_type="static",
            )
            rate = get_monthly_exchange_rate("USD", "EUR", date(2026, 3, 15))
        self.assertEqual(rate, Decimal("1.50"))

    def test_get_monthly_exchange_rate_raises_when_missing(self):
        """Raises ExchangeRateNotFound when no MER row exists."""
        with schema_context(self.schema_name), self.assertRaises(ExchangeRateNotFound):
            get_monthly_exchange_rate("USD", "EUR", date(2026, 3, 1))
