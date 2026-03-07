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

from masu.util.timezone_utils import get_provider_timezone
from masu.util.timezone_utils import normalize_datetime_to_provider_tz
from masu.util.timezone_utils import sanitize_timezone_for_sql


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
        # Provider is imported inside get_provider_timezone to avoid circular
        # imports, so we patch it at its definition site.
        with patch("api.provider.models.Provider") as MockProvider:
            MockProvider.objects.get.return_value = mock_provider
            result = get_provider_timezone("some-uuid")
        self.assertEqual(result, ZoneInfo("America/Chicago"))

    def test_fallback_to_utc_when_blank(self):
        """Falls back to UTC when timezone field is empty."""
        mock_provider = MagicMock()
        mock_provider.timezone = ""
        with patch("api.provider.models.Provider") as MockProvider:
            MockProvider.objects.get.return_value = mock_provider
            result = get_provider_timezone("some-uuid")
        self.assertEqual(result, ZoneInfo("UTC"))

    def test_fallback_to_utc_on_exception(self):
        """Falls back to UTC when the DB lookup raises any unexpected error."""
        with patch("api.provider.models.Provider") as MockProvider:
            MockProvider.objects.get.side_effect = Exception("db error")
            result = get_provider_timezone("some-uuid")
        self.assertEqual(result, ZoneInfo("UTC"))


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

