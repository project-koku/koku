#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for masu/util/timezone_utils.py."""
import datetime
from unittest.mock import MagicMock
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase

from masu.util.timezone_utils import aws_region_to_tz
from masu.util.timezone_utils import get_provider_timezone
from masu.util.timezone_utils import normalize_datetime_to_provider_tz
from masu.util.timezone_utils import sanitize_timezone_for_sql
from masu.util.timezone_utils import trino_date_expr
from masu.util.timezone_utils import utc_range_for_provider_local_day


class SanitizeTimezoneForSqlTest(TestCase):
    """Validate SQL-injection guard on timezone names."""

    def test_valid_iana_name_passes(self):
        """Well-formed IANA names are returned unchanged."""
        self.assertEqual(sanitize_timezone_for_sql("America/New_York"), "America/New_York")
        self.assertEqual(sanitize_timezone_for_sql("Europe/Paris"), "Europe/Paris")
        self.assertEqual(sanitize_timezone_for_sql("UTC"), "UTC")

    def test_empty_or_whitespace_returns_utc(self):
        """Empty / blank input falls back to UTC."""
        self.assertEqual(sanitize_timezone_for_sql(""), "UTC")
        self.assertEqual(sanitize_timezone_for_sql("   "), "UTC")

    def test_injection_attempt_returns_utc(self):
        """Strings containing SQL-injection characters are rejected."""
        self.assertEqual(sanitize_timezone_for_sql("'; DROP TABLE --"), "UTC")
        self.assertEqual(sanitize_timezone_for_sql("America/New_York' OR '1'='1"), "UTC")


class GetProviderTimezoneTest(TestCase):
    """Validate Provider DB lookup with fallback logic."""

    def test_returns_provider_timezone(self):
        """Returns the timezone stored on the Provider model."""
        mock_provider = MagicMock()
        mock_provider.timezone = "America/Chicago"
        with patch("masu.util.timezone_utils.Provider") as MockProvider:
            MockProvider.objects.get.return_value = mock_provider
            result = get_provider_timezone("some-uuid")
        self.assertEqual(result, "America/Chicago")

    def test_fallback_to_utc_when_blank(self):
        """Falls back to UTC when timezone field is empty."""
        mock_provider = MagicMock()
        mock_provider.timezone = ""
        with patch("masu.util.timezone_utils.Provider") as MockProvider:
            MockProvider.objects.get.return_value = mock_provider
            result = get_provider_timezone("some-uuid")
        self.assertEqual(result, "UTC")

    def test_fallback_to_utc_on_exception(self):
        """Falls back to UTC when the DB lookup raises."""
        with patch("masu.util.timezone_utils.Provider") as MockProvider:
            MockProvider.objects.get.side_effect = Exception("db error")
            result = get_provider_timezone("some-uuid")
        self.assertEqual(result, "UTC")


class NormalizeDatetimeTest(TestCase):
    """Validate datetime normalisation to a provider timezone."""

    def test_naive_datetime_gets_provider_tz(self):
        """Naive datetimes are treated as UTC then converted to provider tz."""
        utc_naive = datetime.datetime(2024, 3, 15, 3, 0, 0)
        result = normalize_datetime_to_provider_tz(utc_naive, ZoneInfo("America/New_York"))
        # 03:00 UTC == 23:00 EDT the previous night
        self.assertEqual(result.tzinfo.key, "America/New_York")
        self.assertEqual(result.hour, 23)

    def test_aware_datetime_is_converted(self):
        """Tz-aware datetimes are converted correctly."""
        utc_aware = datetime.datetime(2024, 3, 15, 3, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = normalize_datetime_to_provider_tz(utc_aware, ZoneInfo("America/New_York"))
        self.assertEqual(result.tzinfo.key, "America/New_York")
        self.assertEqual(result.hour, 23)


class UtcRangeForProviderLocalDayTest(TestCase):
    """Validate UTC window generation for a provider-local calendar day."""

    def test_utc_range_standard(self):
        """UTC window for a standard timezone day."""
        tz = ZoneInfo("America/New_York")
        # New York is UTC-4 in summer (EDT)
        local_day = datetime.date(2024, 7, 4)
        start, end = utc_range_for_provider_local_day(local_day, tz)
        # Midnight EDT == 04:00 UTC; next-day midnight == 04:00 UTC next day
        self.assertEqual(start.utcoffset(), datetime.timedelta(0))
        self.assertLess(start, end)
        self.assertEqual((end - start).days, 1)

    def test_utc_range_utc_timezone(self):
        """UTC window for a UTC provider is exactly a 24-hour day."""
        tz = ZoneInfo("UTC")
        local_day = datetime.date(2024, 1, 31)
        start, end = utc_range_for_provider_local_day(local_day, tz)
        self.assertEqual(start, datetime.datetime(2024, 1, 31, 0, 0, tzinfo=ZoneInfo("UTC")))
        self.assertEqual(end, datetime.datetime(2024, 2, 1, 0, 0, tzinfo=ZoneInfo("UTC")))


class AwsRegionToTzTest(TestCase):
    """Validate AWS region → IANA timezone mapping."""

    def test_known_region(self):
        """Known AWS regions return their IANA timezone string."""
        self.assertEqual(aws_region_to_tz("us-east-1"), "America/New_York")
        self.assertEqual(aws_region_to_tz("eu-west-1"), "Europe/Dublin")
        self.assertEqual(aws_region_to_tz("ap-northeast-1"), "Asia/Tokyo")

    def test_unknown_region_returns_utc(self):
        """Unknown regions fall back to UTC."""
        self.assertEqual(aws_region_to_tz("unknown-region-99"), "UTC")


class TrinoDateExprTest(TestCase):
    """Validate Trino SQL fragment generation."""

    def test_non_utc_timezone_uses_at_time_zone(self):
        """Non-UTC timezones produce an AT TIME ZONE expression."""
        expr = trino_date_expr("lineitem_usagestartdate", "America/New_York")
        self.assertIn("AT TIME ZONE", expr)
        self.assertIn("America/New_York", expr)

    def test_utc_timezone_is_plain_date(self):
        """UTC timezone produces a simple date() call without AT TIME ZONE."""
        expr = trino_date_expr("lineitem_usagestartdate", "UTC")
        self.assertNotIn("AT TIME ZONE", expr)
        self.assertTrue(expr.startswith("date("))
