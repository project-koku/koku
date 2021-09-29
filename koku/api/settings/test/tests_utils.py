#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from tenant_schemas.utils import schema_context

from api.settings.utils import get_currency_options
from api.settings.utils import get_selected_currency_or_setup
from api.settings.utils import set_currency
from koku.settings import KOKU_DEFAULT_CURRENCY
from masu.test import MasuTestCase
from reporting.currency.models import CurrencySettings


class TestCurrencyCommon(MasuTestCase):
    """Test cases for currency utils."""

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

    def test_set_currency_negative(self):
        """Test currency raises exception when providing a non-supported currency"""
        with self.assertRaises(ValueError):
            set_currency(self.schema, currency_code="BOGUS")
