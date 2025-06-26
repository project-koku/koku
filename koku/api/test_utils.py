#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the API utils module."""
import datetime
import unittest
from unittest.mock import patch
from unittest.mock import PropertyMock

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.test import TestCase
from django.test.utils import override_settings
from django.utils import timezone
from django_tenants.utils import schema_context

from api.iam.test.iam_test_case import IamTestCase
from api.settings.settings import USER_SETTINGS
from api.utils import DateHelper
from api.utils import get_account_settings
from api.utils import get_cost_type
from api.utils import get_currency
from api.utils import get_months_in_date_range
from api.utils import materialized_view_month_start
from api.utils import merge_dicts
from api.utils import to_utc_datetime
from koku.settings import KOKU_DEFAULT_COST_TYPE
from koku.settings import KOKU_DEFAULT_CURRENCY
from masu.config import Config
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
        first = datetime.datetime.now().date().replace(day=1)
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

    def test_set_datetime_utc(self):
        """Test set_datetime_utc."""
        # Test with datetime
        start_date = datetime.datetime(2024, 7, 5, 0, 0, 0, 0)
        expected_date = start_date
        # self.assertEqual(self.date_helper.set_datetime_utc(start_date), expected_date)

        # Test with date
        self.assertEqual(self.date_helper.set_datetime_utc(start_date.date()), expected_date)

        # Test with str
        self.assertEqual(self.date_helper.set_datetime_utc("2024-07-05"), expected_date)

    def test_month_start(self):
        """Test month start method."""
        today = self.date_helper.today
        expected = datetime.datetime(1970, 1, 1, 0, 0, 0, 0)
        self.assertEqual(self.date_helper.month_start(today), expected)

        today_date = today.date()
        expected = datetime.date(1970, 1, 1)
        self.assertEqual(self.date_helper.month_start(today_date), expected)

        today_str = today_date.strftime("%Y-%m-%d")
        expected = datetime.date(1970, 1, 1)
        self.assertEqual(self.date_helper.month_start(today_str), expected)

    def test_month_end(self):
        """Test month end method."""
        today = self.date_helper.today
        expected = datetime.datetime(1970, 1, 31, 0, 0, 0, 0)
        self.assertEqual(self.date_helper.month_end(today), expected)

        today_date = today.date()
        expected = datetime.date(1970, 1, 31)
        self.assertEqual(self.date_helper.month_end(today_date), expected)

        today_str = today_date.strftime("%Y-%m-%d")
        expected = datetime.date(1970, 1, 31)
        self.assertEqual(self.date_helper.month_end(today_str), expected)

    def test_parse_to_date(self):
        """test datetime.date returned from given objects"""
        today = self.date_helper.today
        expected = datetime.date(1970, 1, 10)
        self.assertEqual(self.date_helper.parse_to_date(today), expected)

        today = self.date_helper.today.date()
        self.assertEqual(self.date_helper.parse_to_date(today), expected)

        today = self.date_helper.today
        today_str = today.strftime("%Y-%m-%d")
        self.assertEqual(self.date_helper.parse_to_date(today_str), expected)

    def test_midnight(self):
        """Test midnight property."""
        expected = datetime.time(0, 0, 0, 0)
        self.assertEqual(self.date_helper.midnight, expected)

    def test_list_days_params_as_strings(self):
        """Test the list_days method."""
        first = datetime.datetime.now().date().replace(day=1)
        second = first.replace(day=2)
        third = first.replace(day=3)
        expected = [first, second, third]
        result = self.date_helper.list_days(str(first), str(third))
        self.assertEqual(result, expected)

    def test_invoice_month_from_bill_date(self):
        """Test that we can get the gcp invoice month from bill date."""
        bill_date_str = "2022-08-01"
        result_invoice_month = self.date_helper.invoice_month_from_bill_date(bill_date_str)
        self.assertEqual(str(result_invoice_month), "202208")


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


class GetDateTimeTest(unittest.TestCase):
    """Test the to_utc_datetime util function."""

    def test_to_utc_datetime_with_none(self):
        """Test to_utc_datetime with None input returns None."""
        result = to_utc_datetime(None)
        self.assertIsNone(result)

    def test_to_utc_datetime_with_string_iso_format(self):
        """Test to_utc_datetime with ISO format string."""
        date_string = "2023-05-15T14:30:00+00:00"
        result = to_utc_datetime(date_string)

        self.assertIsInstance(result, datetime.datetime)
        self.assertEqual(result.tzinfo, settings.UTC)
        self.assertEqual(result.year, 2023)
        self.assertEqual(result.month, 5)
        self.assertEqual(result.day, 15)
        self.assertEqual(result.hour, 14)
        self.assertEqual(result.minute, 30)

    def test_to_utc_datetime_with_string_simple_date(self):
        """Test to_utc_datetime with simple date string."""
        date_string = "2023-05-15"
        result = to_utc_datetime(date_string)

        self.assertIsInstance(result, datetime.datetime)
        self.assertEqual(result.tzinfo, settings.UTC)
        self.assertEqual(result.year, 2023)
        self.assertEqual(result.month, 5)
        self.assertEqual(result.day, 15)

    def test_to_utc_datetime_with_string_different_timezone(self):
        """Test to_utc_datetime with string in different timezone."""
        date_string = "2023-05-15T14:30:00-05:00"
        result = to_utc_datetime(date_string)

        self.assertIsInstance(result, datetime.datetime)
        self.assertEqual(result.tzinfo, settings.UTC)
        # Should be converted to UTC (19:30)
        self.assertEqual(result.hour, 19)
        self.assertEqual(result.minute, 30)

    def test_to_utc_datetime_with_timezone_aware_datetime(self):
        """Test to_utc_datetime with timezone-aware datetime object."""
        import pytz

        eastern = pytz.timezone("US/Eastern")
        dt = datetime.datetime(2023, 5, 15, 14, 30, 0, tzinfo=eastern)
        result = to_utc_datetime(dt)

        self.assertIsInstance(result, datetime.datetime)
        self.assertEqual(result.tzinfo, settings.UTC)
        # Should be converted to UTC from Eastern time
        self.assertNotEqual(result.hour, 14)  # Should be different due to timezone conversion

    def test_to_utc_datetime_with_timezone_naive_datetime(self):
        """Test to_utc_datetime with timezone-naive datetime object."""
        dt = datetime.datetime(2023, 5, 15, 14, 30, 0)
        result = to_utc_datetime(dt)

        self.assertIsInstance(result, datetime.datetime)
        self.assertEqual(result.tzinfo, settings.UTC)
        self.assertEqual(result.year, 2023)
        self.assertEqual(result.month, 5)
        self.assertEqual(result.day, 15)
        self.assertEqual(result.hour, 14)
        self.assertEqual(result.minute, 30)

    def test_to_utc_datetime_with_utc_datetime(self):
        """Test to_utc_datetime with UTC datetime object."""
        dt = datetime.datetime(2023, 5, 15, 14, 30, 0, tzinfo=settings.UTC)
        result = to_utc_datetime(dt)

        self.assertIsInstance(result, datetime.datetime)
        self.assertEqual(result.tzinfo, settings.UTC)
        self.assertEqual(result, dt)  # Should be unchanged

    def test_to_utc_datetime_with_invalid_string(self):
        """Test to_utc_datetime with invalid date string raises ValueError."""
        with self.assertRaises(ValueError):
            to_utc_datetime("invalid-date-string")

    def test_to_utc_datetime_with_invalid_type(self):
        """Test to_utc_datetime with invalid type raises TypeError."""
        with self.assertRaises(TypeError):
            to_utc_datetime(12345)

        with self.assertRaises(TypeError):
            to_utc_datetime([])

        with self.assertRaises(TypeError):
            to_utc_datetime({})

    def test_to_utc_datetime_with_date_object(self):
        """Test to_utc_datetime with date object converts to datetime at midnight UTC."""
        date_obj = datetime.date(2023, 5, 15)
        result = to_utc_datetime(date_obj)

        self.assertIsInstance(result, datetime.datetime)
        self.assertEqual(result.tzinfo, settings.UTC)
        self.assertEqual(result.year, 2023)
        self.assertEqual(result.month, 5)
        self.assertEqual(result.day, 15)
        self.assertEqual(result.hour, 0)
        self.assertEqual(result.minute, 0)
        self.assertEqual(result.second, 0)
        self.assertEqual(result.microsecond, 0)

    def test_to_utc_datetime_preserves_precision(self):
        """Test to_utc_datetime preserves microsecond precision."""
        dt = datetime.datetime(2023, 5, 15, 14, 30, 45, 123456, tzinfo=settings.UTC)
        result = to_utc_datetime(dt)

        self.assertEqual(result.microsecond, 123456)

    def test_to_utc_datetime_with_various_string_formats(self):
        """Test to_utc_datetime with various string formats."""
        test_cases = [
            "2023-05-15T14:30:00Z",
            "2023-05-15 14:30:00",
            "2023/05/15 14:30:00",
            "May 15, 2023 2:30 PM",
            "2023-05-15T14:30:00.123456Z",
        ]

        for date_string in test_cases:
            with self.subTest(date_string=date_string):
                result = to_utc_datetime(date_string)
                self.assertIsInstance(result, datetime.datetime)
                self.assertEqual(result.tzinfo, settings.UTC)
                self.assertEqual(result.year, 2023)
                self.assertEqual(result.month, 5)
                self.assertEqual(result.day, 15)


class GetMonthsInDateRangeTest(unittest.TestCase):
    """Test the get_months_in_date_range util."""

    def setUp(self):
        """Set up get_months_in_date_range tests."""
        super().setUp()

        self.start_date = datetime.datetime(2023, 4, 3, tzinfo=settings.UTC)
        self.end_date = datetime.datetime(2023, 4, 12, tzinfo=settings.UTC)
        self.first_of_year = datetime.datetime(2023, 1, 1, tzinfo=settings.UTC)
        self.first_of_month = datetime.datetime(2023, 1, 1, tzinfo=settings.UTC)
        self.early_start_date = datetime.datetime(2022, 4, 3, tzinfo=settings.UTC)
        self.early_end_date = datetime.datetime(2022, 4, 12, tzinfo=settings.UTC)

    @patch("api.utils.DateHelper.today", new_callable=PropertyMock)
    def test_get_months_in_date_range__report_with_dates(self, mock_dh_today):
        """Test that calling get_months_in_date_range with report only returns list of month tuples"""

        mock_dh_today.return_value = self.start_date
        expected_start = self.start_date
        expected_end = self.end_date
        test_report = {
            "schema": "org1234567",
            "start": expected_start,
            "end": expected_end,
            "provider_uuid": "f3da28f7-00c7-43ba-a1de-f0be0b9d6060",
        }
        expected_months = [(expected_start, expected_end, None)]

        returned_months = get_months_in_date_range(test_report)

        mock_dh_today.assert_called()
        self.assertEqual(returned_months, expected_months)

    @patch("api.utils.DateHelper.today", new_callable=PropertyMock)
    def test_get_months_in_date_range__report_with_no_dates(self, mock_dh_today):
        """
        Test that calling get_months_in_date_range
        with a report missing start, end or both dates
        returns list of month tuples.
        """

        mock_dh_today.return_value = self.start_date
        test_report = {
            "schema": "org1234567",
            "provider_uuid": "f3da28f7-00c7-43ba-a1de-f0be0b9d6060",
        }
        expected_start = self.start_date - datetime.timedelta(days=2)
        expected_end = self.start_date
        expected_months = [(expected_start, expected_end, None)]

        returned_months = get_months_in_date_range(test_report)

        mock_dh_today.assert_called()
        self.assertEqual(returned_months, expected_months)

    @patch("api.utils.DateHelper.today", new_callable=PropertyMock)
    def test_get_months_in_date_range__report_with_no_dates_year_start(self, mock_dh_today):
        """
        Test that calling get_months_in_date_range
        with a report missing start, end or both dates
        returns list of month tuples at the beginning of the year
        """

        mock_dh_today.return_value = self.first_of_year
        test_report = {
            "schema": "org1234567",
            "provider_uuid": "f3da28f7-00c7-43ba-a1de-f0be0b9d6060",
        }
        expected_date_2 = self.first_of_year
        expected_months = [(expected_date_2, expected_date_2, None)]

        returned_months = get_months_in_date_range(test_report)

        mock_dh_today.assert_called()
        self.assertEqual(returned_months, expected_months)

    @patch("api.utils.DateHelper.today", new_callable=PropertyMock)
    def test_get_months_in_date_range__report_with_no_dates_month_start(self, mock_dh_today):
        """
        Test that calling get_months_in_date_range
        with a report missing start, end or both dates
        returns list of month tuples during first of a month
        """
        end_date = self.first_of_month.replace(day=3)
        mock_dh_today.return_value = end_date
        test_report = {
            "schema": "org1234567",
            "provider_uuid": "f3da28f7-00c7-43ba-a1de-f0be0b9d6060",
        }
        expected_date = self.first_of_month
        expected_months = [(expected_date, end_date, None)]

        returned_months = get_months_in_date_range(test_report)

        mock_dh_today.assert_called()
        self.assertEqual(returned_months, expected_months)

    @patch("api.utils.DateHelper.today", new_callable=PropertyMock)
    def test_get_months_in_date_range__start_invoice_month_only(self, mock_dh_today):
        """
        Test that calling get_months_in_date_range
        with invoice_month and start_date only
        returns list of month tuples.
        """

        mock_dh_today.return_value = self.start_date
        invoice_month = self.start_date.strftime("%Y%m")
        expected_date = self.start_date
        expected_months = [(expected_date, expected_date, invoice_month)]

        returned_months = get_months_in_date_range(
            report=None, start=expected_date, end=None, invoice_month=invoice_month
        )

        mock_dh_today.assert_called()
        self.assertEqual(returned_months, expected_months)

    def test_get_months_in_date_range__start_end_invoice_month(self):
        """
        Test that calling get_months_in_date_range
        with start and end dates, and invoice_month only
        returns list of month tuples.
        """

        invoice_month = self.start_date.strftime("%Y%m")
        expected_start = self.start_date
        expected_end = self.end_date
        expected_months = [(expected_start, expected_end, invoice_month)]

        returned_months = get_months_in_date_range(
            report=None,
            start=expected_start.strftime("%Y-%m-%d"),
            end=expected_end.strftime("%Y-%m-%d"),
            invoice_month=invoice_month,
        )

        self.assertEqual(returned_months, expected_months)

    @patch("api.utils.DateHelper.today", new_callable=PropertyMock)
    def test_get_months_in_date_range__start_end_only(self, mock_dh_today):
        """
        Test that calling get_months_in_date_range
        with start and end dates only
        returns list of month tuples.
        """

        mock_dh_today.return_value = self.start_date
        expected_start = self.start_date
        expected_end = self.end_date
        expected_months = [(expected_start, expected_end, None)]

        returned_months = get_months_in_date_range(
            report=None,
            start=expected_start.strftime("%Y-%m-%d"),
            end=expected_end.strftime("%Y-%m-%d"),
        )

        mock_dh_today.assert_called()
        self.assertEqual(returned_months, expected_months)

    @patch("api.utils.DateHelper.today", new_callable=PropertyMock)
    def test_get_months_in_date_range__early_start_date(self, mock_dh_today):
        """
        Test that get_months_in_date_range
        with a start date earlier than configured INITIAL_INGEST_NUM_MONTHS
        returns list of month tuples.
        """

        initial_month_qty = Config.INITIAL_INGEST_NUM_MONTHS
        Config.INITIAL_INGEST_NUM_MONTHS = 0
        mock_dh_today.return_value = self.start_date
        expected_start = self.start_date.replace(day=1)
        expected_end = self.end_date
        expected_months = [(expected_start, expected_end, None)]

        returned_months = get_months_in_date_range(
            report=None, start=self.early_start_date.strftime("%Y-%m-%d"), end=self.end_date
        )

        Config.INITIAL_INGEST_NUM_MONTHS = initial_month_qty

        mock_dh_today.assert_called()
        self.assertEqual(returned_months, expected_months)

    @patch("api.utils.DateHelper.today", new_callable=PropertyMock)
    def test_get_months_in_date_range__early_start_early_end_dates(self, mock_dh_today):
        """
        Test that calling get_months_in_date_range
        with both start and end dates earlier than configured INITIAL_INGEST_NUM_MONTHS
        returns list of month tuples.
        """

        initial_month_qty = Config.INITIAL_INGEST_NUM_MONTHS
        Config.INITIAL_INGEST_NUM_MONTHS = 0
        mock_dh_today.return_value = self.start_date
        expected_start = self.start_date.replace(day=1)
        expected_end = self.start_date
        expected_months = [(expected_start, expected_end, None)]

        returned_months = get_months_in_date_range(
            report=None, start=self.early_start_date.strftime("%Y-%m-%d"), end=self.early_end_date.strftime("%Y-%m-%d")
        )

        Config.INITIAL_INGEST_NUM_MONTHS = initial_month_qty

        mock_dh_today.assert_called()
        self.assertEqual(returned_months, expected_months)
