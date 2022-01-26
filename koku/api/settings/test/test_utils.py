#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from tenant_schemas.utils import schema_context

from api.settings.utils import get_cost_type_options
from api.settings.utils import get_selected_cost_type_or_setup
from api.settings.utils import get_selected_currency_or_setup
from api.settings.utils import set_cost_type
from api.settings.utils import set_currency
from koku.settings import KOKU_DEFAULT_COST_TYPE
from koku.settings import KOKU_DEFAULT_CURRENCY
from masu.test import MasuTestCase
from reporting.user_settings.models import UserSettings


class TestUserSettingCommon(MasuTestCase):
    """Test cases for currency utils."""

    def setUp(self):
        """Set up test suite."""
        with schema_context(self.schema):
            UserSettings.objects.all().delete()

    """Tests for cost_type utils."""

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
        options = get_cost_type_options()
        self.assertTrue(len(options) != 0)

    def test_set_currency_negative(self):
        """Test cost_type raises exception when providing a non-supported cost_type"""
        with self.assertRaises(ValueError):
            set_currency(self.schema, currency_code="BOGUS")

    """Tests for cost_type utils."""

    def test_get_selected_cost_type_or_setup(self):
        """Test cost_type initialization."""
        cost_type = get_selected_cost_type_or_setup(self.schema)
        self.assertEqual(cost_type, KOKU_DEFAULT_COST_TYPE)

        new_cost_type = "savingsplan_effective_cost"
        set_cost_type(self.schema, cost_type_code=new_cost_type)
        cost_type = get_selected_cost_type_or_setup(self.schema)
        self.assertEqual(cost_type, new_cost_type)

    def test_get_cost_type_options(self):
        """Test get_cost_type_options."""
        options = get_cost_type_options()
        self.assertTrue(len(options) != 0)

    def test_set_cost_type_negative(self):
        """Test cost_type raises exception when providing a non-supported cost_type"""
        with self.assertRaises(ValueError):
            set_cost_type(self.schema, cost_type_code="BOGUS")
