#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Test the API utils module."""

import datetime
import random

import pint
from django.test import TestCase
from django.utils import timezone
from pint.errors import UndefinedUnitError

from api.utils import DateHelper, UnitConverter


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

    def test_next_month(self):
        """Test the next_month method."""
        current_month = datetime.datetime.now().replace(microsecond=0, second=0,
                                                        minute=0, hour=0, day=1)
        last_month = current_month.replace(month=(current_month.month - 1))
        self.assertEqual(current_month,
                         DateHelper().next_month(last_month))

    def test_previous_month(self):
        """Test the previous_month method."""
        current_month = datetime.datetime.now().replace(microsecond=0, second=0,
                                                        minute=0, hour=0, day=1)
        last_month = current_month.replace(month=(current_month.month - 1))
        self.assertEqual(last_month,
                         DateHelper().previous_month(current_month))

    def test_list_days(self):
        """Test the list_days method."""
        first = datetime.datetime.now().replace(microsecond=0, second=0,
                                                minute=0, hour=0, day=1)
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
        today = timezone.now().replace(microsecond=0, second=0,
                                       minute=0, hour=0)
        two_days_ago = (today - delta_day) - delta_day
        self.assertEqual(self.date_helper.n_days_ago(today, 2),
                         two_days_ago)


class APIUtilsUnitConverterTest(TestCase):
    """Tests against the API utils."""

    @classmethod
    def setUpClass(cls):
        """Set up for test class."""
        super().setUpClass()
        cls.converter = UnitConverter()

    def test_initializer(self):
        """Test that the UnitConverter starts properly."""
        self.assertIsInstance(
            self.converter.unit_registry,
            pint.registry.UnitRegistry
        )

        self.assertTrue(hasattr(self.converter.Quantity, 'units'))
        self.assertTrue(hasattr(self.converter.Quantity, 'magnitude'))

    def test_validate_unit_success(self):
        """Test that unit validation succeeds with known units."""
        unit = 'GB'
        result = self.converter.validate_unit(unit)
        self.assertEqual(unit, result)

        unit = 'Hrs'
        result = self.converter.validate_unit(unit)
        self.assertEqual(unit.lower(), result)

    def test_validate_unit_failure(self):
        """Test that an exception is thrown with an invalid unit."""
        unit = 'Gigglebots'

        with self.assertRaises(UndefinedUnitError):
            self.converter.validate_unit(unit)

    def test_unit_converter(self):
        """Test that unit conversion succeeds."""
        value = random.randint(1, 9)
        from_unit = 'gigabyte'
        to_unit = 'byte'

        expected_value = value * 1E9

        result = self.converter.convert_quantity(value, from_unit, to_unit)

        self.assertEqual(result.units, to_unit)
        self.assertEqual(result.magnitude, expected_value)
