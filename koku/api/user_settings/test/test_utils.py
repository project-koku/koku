#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from django_tenants.utils import schema_context

from api.user_settings.utils import set_cost_type
from api.user_settings.utils import set_currency
from masu.test import MasuTestCase
from reporting.user_settings.models import UserSettings


class TestUserSettingCommon(MasuTestCase):
    """Test cases for currency utils."""

    def setUp(self):
        """Set up test suite."""
        with schema_context(self.schema):
            UserSettings.objects.all().delete()

    """Tests for cost_type utils."""

    def test_set_currency_negative(self):
        """Test cost_type raises exception when providing a non-supported cost_type"""
        with self.assertRaises(ValueError):
            set_currency(self.schema, currency_code="BOGUS")

    """Tests for cost_type utils."""

    def test_set_cost_type_negative(self):
        """Test cost_type raises exception when providing a non-supported cost_type"""
        with self.assertRaises(ValueError):
            set_cost_type(self.schema, cost_type_code="BOGUS")
