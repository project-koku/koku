#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from decimal import Decimal

from api.currency.models import ExchangeRateDictionary
from api.currency.utils import build_exchange_dictionary
from api.currency.utils import exchange_dictionary
from api.iam.test.iam_test_case import IamTestCase


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
