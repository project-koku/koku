#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the currency common."""
from tenant_schemas.utils import schema_context

from currency.common import get_currency_options
from currency.common import get_selected_currency_or_setup
from currency.common import set_currency
from koku.settings import KOKU_DEFAULT_CURRENCY
from masu.test import MasuTestCase
from reporting.currency.models import CurrencySettings


class TestCurrencyCommon(MasuTestCase):
    """Test cases for currency common."""

    def setUp(self):
        """Set up test suite."""
        with schema_context(self.schema):
            CurrencySettings.objects.all().delete()

    def test_get_selected_currency_or_setup(self):
        """Test currency initialization."""
        currency = get_selected_currency_or_setup(self.schema)
        self.assertEqual(currency, KOKU_DEFAULT_CURRENCY)

        new_currency = "JPY"
        set_currency(self.schema, currency_code=new_currency)
        currency = get_selected_currency_or_setup(self.schema)
        self.assertEqual(currency, new_currency)

    def test_get_currency_options(self):
        """Test get_currency_options."""
        options = get_currency_options()
        self.assertTrue(len(options) != 0)
