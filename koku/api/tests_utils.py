#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the API utils module."""
import datetime
import random
import unittest

import pint
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.test import TestCase
from django.test.utils import override_settings
from django.utils import timezone
from pint.errors import UndefinedUnitError
from tenant_schemas.utils import schema_context

from api.iam.test.iam_test_case import IamTestCase
from api.user_settings.settings import USER_SETTINGS
from api.utils import DateHelper
from api.utils import get_account_settings
from api.utils import get_cost_type
from api.utils import get_currency
from api.utils import materialized_view_month_start
from api.utils import merge_dicts
from api.utils import UnitConverter
from koku.settings import KOKU_DEFAULT_COST_TYPE
from koku.settings import KOKU_DEFAULT_CURRENCY
from reporting.user_settings.models import UserSettings


class MergeDictsTest(unittest.TestCase):
    """Test the merge_dicts util."""

    def test_merge_dicts_simple(self):
        dikt1 = {"key": ["value"]}
        dikt2 = {"k": ["v"]}
        expected_1 = {"key": ["value"], "k": ["v"]}
        merge1 = merge_dicts(dikt1, dikt2)
        for k, v in expected_1.items():
            self.assertEqual(sorted(merge1[k]), sorted(v))

    def test_merge_dicts_more_complex(self):
        dikt1 = {"key": ["value"]}
        dikt3 = {"key": ["value2"], "k": ["v"]}
        expected_2 = {"key": ["value", "value2"], "k": ["v"]}
        merge2 = merge_dicts(dikt1, dikt3)
        for k, v in expected_2.items():
            self.assertEqual(sorted(merge2[k]), sorted(v))

    def test_merge_dicts_even_more_complex(self):
        dikt1 = {"key": ["value"]}
        dikt2 = {"k": ["v"]}
        dikt3 = {"key": ["value2"], "k": ["v"]}
        expected_2 = {"key": ["value", "value2"], "k": ["v"]}
        merge3 = merge_dicts(dikt1, dikt2, dikt3)
        for k, v in expected_2.items():
            self.assertEqual(sorted(merge3[k]), sorted(v))


class MaterializsedViewStartTest(unittest.TestCase):
    """Test the materialized_view_month_start util."""

    @override_settings(RETAIN_NUM_MONTHS=5)
    def test_materialized_view_month_start(self):
        """Test materialized_view_month_start property."""
        today = timezone.now().replace(microsecond=0, second=0, minute=0, hour=0)
        retain_months_ago = today - relativedelta(months=settings.RETAIN_NUM_MONTHS - 1)
        expected = retain_months_ago.replace(day=1)
        self.assertEqual(materialized_view_month_start(), expected)


class DateHelperTest(TestCase):
    """Test the DateHelper."""

    def setUp(self):
        """Test setup."""
        self.date_helper = DateHelper()
        self.date_helper._now = datetime.datetime(1970, 1, 10, 12, 59, 59)

    def test_this_hour(self):
        """Test this_hour property."""
        expected = datetime.datetime(1970, 1, 10, 12, 0, 0, 0)
        self.assertEqual(self.date_helper.this_hour, expected)

    def test_next_hour(self):
        """Test next_hour property."""
        expected = datetime.datetime(1970, 1, 10, 13, 0, 0, 0)
        self.assertEqual(self.date_helper.next_hour, expected)

    def test_prev_hour(self):
        """Test previous_hour property."""
        expected = datetime.datetime(1970, 1, 10, 11, 0, 0, 0)
        self.assertEqual(self.date_helper.previous_hour, expected)

    def test_today(self):
        """Test today property."""
        expected = datetime.datetime(1970, 1, 10, 0, 0, 0, 0)
        self.assertEqual(self.date_helper.today, expected)

    def test_yesterday(self):
        """Test yesterday property."""
        date_helper = DateHelper()
        date_helper._now = datetime.datetime(1970, 1, 1, 12, 59, 59)
        expected = datetime.datetime(1969, 12, 31, 0, 0, 0, 0)
        self.assertEqual(date_helper.yesterday, expected)

    def test_tomorrow(self):
        """Test tomorrow property."""
        expected = datetime.datetime(1970, 1, 11, 0, 0, 0, 0)
        self.assertEqual(self.date_helper.tomorrow, expected)

    def test_this_month_start(self):
        """Test this_month_start property."""
        expected = datetime.datetime(1970, 1, 1, 0, 0, 0, 0)
        self.assertEqual(self.date_helper.this_month_start, expected)

    def test_this_month_end(self):
        """Test this_month_end property."""
        expected = datetime.datetime(1970, 1, 31, 0, 0, 0, 0)
        self.assertEqual(self.date_helper.this_month_end, expected)

    def test_next_month_start(self):
        """Test next_month_start property."""
        expected = datetime.datetime(1970, 2, 1, 0, 0, 0, 0)
        self.assertEqual(self.date_helper.next_month_start, expected)

    def test_next_month_end(self):
        """Test next_month_end property."""
        expected = datetime.datetime(1970, 2, 28, 0, 0, 0, 0)
        self.assertEqual(self.date_helper.next_month_end, expected)

    def test_last_month_start(self):
        """Test last_month_start property."""
        expected = datetime.datetime(1969, 12, 1, 0, 0, 0, 0)
        self.assertEqual(self.date_helper.last_month_start, expected)

    def test_last_month_end(self):
        """Test last_month_end property."""
        expected = datetime.datetime(1969, 12, 31, 0, 0, 0, 0)
        self.assertEqual(self.date_helper.last_month_end, expected)

    def test_relative_month_start_neg(self):
        expected = datetime.datetime(1969, 10, 1)
        self.assertEqual(self.date_helper.relative_month_start(-3), expected)

    def test_relative_month_start_pos(self):
        expected = datetime.datetime(1970, 6, 1)
        self.assertEqual(self.date_helper.relative_month_start(5), expected)

    def test_relative_month_end_neg(self):
        expected = datetime.datetime(1969, 9, 30)
        self.assertEqual(self.date_helper.relative_month_end(-4), expected)

    def test_relative_month_end_pos(self):
        expected = datetime.datetime(1970, 8, 31)
        self.assertEqual(self.date_helper.relative_month_end(7), expected)

    def test_next_month(self):
        """Test the next_month method."""
        current_month = datetime.datetime.now().replace(microsecond=0, second=0, minute=0, hour=0, day=1)
        last_month = current_month - relativedelta(months=1)
        self.assertEqual(current_month, DateHelper().next_month(last_month))

    def test_previous_month(self):
        """Test the previous_month method."""
        current_month = datetime.datetime.now().replace(microsecond=0, second=0, minute=0, hour=0, day=1)
        last_month = current_month - relativedelta(months=1)
        self.assertEqual(last_month, DateHelper().previous_month(current_month))

    def test_list_days(self):
        """Test the list_days method."""
        first = datetime.datetime.now().replace(microsecond=0, second=0, minute=0, hour=0, day=1)
        second = first.replace(day=2)
        third = first.replace(day=3)
        expected = [first, second, third]
        self.assertEqual(self.date_helper.list_days(first, third), expected)

    def test_list_months(self):
        """Test the list_months method."""
        first = datetime.datetime(1970, 1, 1)
        second = datetime.datetime(1970, 2, 1)
        third = datetime.datetime(1970, 3, 1)
        expected = [first, second, third]
        self.assertEqual(self.date_helper.list_months(first, third), expected)

    def test_n_days_ago(self):
        """Test the n_days_ago method."""
        delta_day = datetime.timedelta(days=1)
        today = timezone.now().replace(microsecond=0, second=0, minute=0, hour=0)
        two_days_ago = (today - delta_day) - delta_day
        self.assertEqual(self.date_helper.n_days_ago(today, 2), two_days_ago)

    def test_month_start(self):
        """Test month start method."""
        today = self.date_helper.today
        expected = datetime.datetime(1970, 1, 1, 0, 0, 0, 0)
        self.assertEqual(self.date_helper.month_start(today), expected)

    def test_month_end(self):
        """Test month end method."""
        today = self.date_helper.today
        expected = datetime.datetime(1970, 1, 31, 0, 0, 0, 0)
        self.assertEqual(self.date_helper.month_end(today), expected)

        today_date = today.date()
        expected = datetime.date(1970, 1, 31)
        self.assertEqual(self.date_helper.month_end(today_date), expected)

    def test_midnight(self):
        """Test midnight property."""
        expected = datetime.time(0, 0, 0, 0)
        self.assertEqual(self.date_helper.midnight, expected)


class APIUtilsUnitConverterTest(TestCase):
    """Tests against the API utils."""

    @classmethod
    def setUpClass(cls):
        """Set up for test class."""
        super().setUpClass()
        cls.converter = UnitConverter()

    def test_initializer(self):
        """Test that the UnitConverter starts properly."""
        self.assertIsInstance(self.converter.unit_registry, pint.registry.UnitRegistry)

        self.assertTrue(hasattr(self.converter.Quantity, "units"))
        self.assertTrue(hasattr(self.converter.Quantity, "magnitude"))

    def test_validate_unit_success(self):
        """Test that unit validation succeeds with known units."""
        unit = "GB"
        result = self.converter.validate_unit(unit)
        self.assertEqual(unit, result)

        unit = "Hrs"
        result = self.converter.validate_unit(unit)
        self.assertEqual(unit.lower(), result)

    def test_validate_unit_failure(self):
        """Test that an exception is thrown with an invalid unit."""
        unit = "Gigglebots"

        with self.assertRaises(UndefinedUnitError):
            self.converter.validate_unit(unit)

    def test_unit_converter(self):
        """Test that unit conversion succeeds."""
        value = random.randint(1, 9)
        from_unit = "gigabyte"
        to_unit = "byte"

        expected_value = value * 1e9

        result = self.converter.convert_quantity(value, from_unit, to_unit)

        self.assertEqual(result.units, to_unit)
        self.assertEqual(result.magnitude, expected_value)


class GeneralUtilsTest(IamTestCase):
    """Test general functions in utils"""

    def test_get_cost_type(self):
        """Test the get_cost_type function in utils."""
        with schema_context(self.schema_name):
            query_settings = UserSettings.objects.all().first()
            if not query_settings:
                self.assertEqual(get_cost_type(self.request_context["request"]), KOKU_DEFAULT_COST_TYPE)
            else:
                cost_type = query_settings.settings["cost_type"]
                self.assertEqual(get_cost_type(self.request_context["request"]), cost_type)

    def test_get_currency(self):
        """Test the get_currency function in utils."""
        with schema_context(self.schema_name):
            query_settings = UserSettings.objects.all().first()
            if not query_settings:
                self.assertEqual(get_currency(self.request_context["request"]), KOKU_DEFAULT_CURRENCY)
            else:
                currency = query_settings.settings["currency"]
                self.assertEqual(get_currency(self.request_context["request"]), currency)

    def test_get_user_settings(self):
        """Test the get_user_settings function in utils."""
        with schema_context(self.schema_name):
            query_settings = UserSettings.objects.all().first()
            if not query_settings:
                self.assertEqual(get_account_settings(self.request_context["request"]), USER_SETTINGS)
            else:
                settings = query_settings.settings
                self.assertEqual(get_account_settings(self.request_context["request"]), settings)
