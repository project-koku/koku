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
"""Test the DateAccessor object."""
from datetime import datetime

import dateutil
import pytz
from faker import Faker

from api.utils import DateHelper
from masu.config import Config
from masu.external.date_accessor import DateAccessor
from masu.external.date_accessor import DateAccessorError
from masu.test import MasuTestCase


class DateAccessorTest(MasuTestCase):
    """Test Cases for the DateAccessor object."""

    fake = Faker()

    @classmethod
    def setUpClass(cls):
        """Class initialization."""
        super().setUpClass()
        cls.initial_debug = Config.DEBUG
        cls.initial_override = Config.MASU_DATE_OVERRIDE

    @classmethod
    def tearDownClass(cls):
        """Class Teardown."""
        super().tearDownClass()
        Config.DEBUG = cls.initial_debug
        Config.MASU_DATE_OVERRIDE = cls.initial_override

    def setUp(self):
        """Set up the tests."""
        DateAccessor.mock_date_time = None
        Config.DEBUG = False
        Config.MASU_DATE_OVERRIDE = None

    def test_today_override(self):
        """Test today() with override."""
        fake_dt = self.fake.date_time(tzinfo=pytz.UTC)
        Config.DEBUG = True
        Config.MASU_DATE_OVERRIDE = fake_dt.strftime("%Y-%m-%d %H:%M:%S")

        accessor = DateAccessor()
        today = accessor.today()

        self.assertEqual(today.year, fake_dt.year)
        self.assertEqual(today.month, fake_dt.month)
        self.assertEqual(today.day, fake_dt.day)
        self.assertEqual(today.tzinfo.tzname(today), str(pytz.UTC))

    def test_today_override_debug_false(self):
        """Test today() with override when debug is false."""
        fake_tz = pytz.timezone(self.fake.timezone())
        fake_dt = self.fake.date_time(tzinfo=fake_tz)
        Config.DEBUG = False
        Config.MASU_DATE_OVERRIDE = fake_dt

        accessor = DateAccessor()
        today = accessor.today()
        expected_date = datetime.now(tz=pytz.UTC)

        self.assertEqual(today.year, expected_date.year)
        self.assertEqual(today.month, expected_date.month)
        self.assertEqual(today.day, expected_date.day)
        self.assertEqual(today.tzinfo, pytz.UTC)

    def test_today_override_override_not_set(self):
        """Test today() with override set when debug is true."""
        Config.DEBUG = True
        Config.MASU_DATE_OVERRIDE = None

        accessor = DateAccessor()
        today = accessor.today()
        expected_date = datetime.now(tz=pytz.UTC)

        self.assertEqual(today.year, expected_date.year)
        self.assertEqual(today.month, expected_date.month)
        self.assertEqual(today.day, expected_date.day)
        self.assertEqual(today.tzinfo, pytz.UTC)

    def test_today_override_override_not_set_debug_false(self):
        """Test today() with override not set when debug is false."""
        Config.DEBUG = False
        Config.MASU_DATE_OVERRIDE = None

        accessor = DateAccessor()
        today = accessor.today()
        expected_date = datetime.now(tz=pytz.UTC)

        self.assertEqual(today.year, expected_date.year)
        self.assertEqual(today.month, expected_date.month)
        self.assertEqual(today.day, expected_date.day)
        self.assertEqual(today.tzinfo, pytz.UTC)

    def test_today_override_with_iso8601(self):
        """Test today() with override and using ISO8601 format."""
        fake_tz_name = self.fake.timezone()
        fake_tz = pytz.timezone(fake_tz_name)
        fake_dt = self.fake.date_time(tzinfo=fake_tz)

        Config.DEBUG = True
        Config.MASU_DATE_OVERRIDE = fake_dt.isoformat()
        accessor = DateAccessor()
        today = accessor.today()

        self.assertEqual(today.year, fake_dt.year)
        self.assertEqual(today.month, fake_dt.month)
        self.assertEqual(today.day, fake_dt.day)

        expected_offset = dateutil.tz.tzoffset(fake_tz_name, fake_tz.utcoffset(fake_dt, is_dst=False))
        self.assertEqual(today.tzinfo, expected_offset)

    def test_today_with_timezone_string(self):
        """Test that a timezone string works as expected."""
        string_tz = "UTC"
        current_utc_time = datetime.utcnow()
        accessor = DateAccessor()
        result_time = accessor.today_with_timezone(string_tz)

        self.assertEqual(current_utc_time.date(), result_time.date())
        self.assertEqual(current_utc_time.hour, result_time.hour)
        self.assertEqual(current_utc_time.minute, result_time.minute)
        self.assertEqual(result_time.tzinfo, pytz.UTC)

    def test_today_with_timezone_object(self):
        """Test that a timezone string works as expected."""
        fake_tz_name = self.fake.timezone()
        fake_tz = pytz.timezone(fake_tz_name)

        current_time = datetime.now(fake_tz)
        accessor = DateAccessor()
        result_time = accessor.today_with_timezone(fake_tz)

        self.assertEqual(current_time.date(), result_time.date())
        self.assertEqual(current_time.hour, result_time.hour)
        self.assertEqual(current_time.minute, result_time.minute)
        self.assertEqual(str(result_time.tzinfo), fake_tz_name)

    def test_today_with_timezone_error_raised(self):
        """Test that an error is raised with an invalid timezone."""
        string_tz = "Moon/Mare Tranquillitatis"
        accessor = DateAccessor()

        with self.assertRaises(DateAccessorError):
            accessor.today_with_timezone(string_tz)

    def test_get_billing_month_start(self):
        """Test that a proper datetime is returend for bill month."""
        dh = DateHelper()
        accessor = DateAccessor()
        expected = dh.this_month_start.date()
        today = dh.today
        str_input = str(today)
        datetime_input = today
        date_input = today.date()
        self.assertEqual(accessor.get_billing_month_start(str_input), expected)
        self.assertEqual(accessor.get_billing_month_start(datetime_input), expected)
        self.assertEqual(accessor.get_billing_month_start(date_input), expected)
