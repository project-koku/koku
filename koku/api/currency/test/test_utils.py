#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from api.currency.models import ExchangeRateDictionary
from api.currency.utils import build_exchange_dictionary
from api.currency.utils import exchange_dictionary
from api.iam.test.iam_test_case import IamTestCase

RATE_DICT = {
    "USD": 1,
    "AUD": 1.44,
    "CAD": 1.29,
}


class CurrencyUtilsTest(IamTestCase):
    """Tests for the currency utils."""

    def setUp(self):
        ExchangeRateDictionary.objects.all().delete()

    def test_build_exchange_dictionary(self):
        """Test that a list GET call returns the supported currencies."""
        expected = {
            "USD": {"USD": 1, "AUD": 1.44, "CAD": 1.29},
            "AUD": {"USD": 0.6944444444444444, "AUD": 1.0, "CAD": 0.8958333333333334},
            "CAD": {"USD": 0.7751937984496123, "AUD": 1.1162790697674418, "CAD": 1.0},
        }

        output = build_exchange_dictionary(RATE_DICT)
        self.assertEqual(output, expected)

    def test_exchange_dictionary(self):
        """Test that the exchange rate dict is sent to the DB."""
        exchange_dictionary(RATE_DICT)
        exchanged_data = ExchangeRateDictionary.objects.all().first().currency_exchange_dictionary
        self.assertIsNotNone(exchanged_data)
