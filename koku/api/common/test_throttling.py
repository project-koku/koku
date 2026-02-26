#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for API throttling classes."""
from unittest.mock import Mock
from unittest.mock import patch

from django.test import TestCase

from api.common.throttling import TagQueryThrottle


class TagQueryThrottleParseRateTest(TestCase):
    """Tests for TagQueryThrottle.parse_rate."""

    def test_parse_rate_none_returns_none_none(self):
        """When rate is None, return (None, None)."""
        throttle = TagQueryThrottle()
        self.assertEqual(throttle.parse_rate(None), (None, None))

    def test_parse_rate_invalid_period_returns_none_none(self):
        """When period does not match digits+unit, return (None, None)."""
        throttle = TagQueryThrottle()
        self.assertEqual(throttle.parse_rate("1/invalid"), (None, None))
        self.assertEqual(throttle.parse_rate("1/"), (None, None))

    def test_parse_rate_valid_returns_requests_and_duration(self):
        """Valid rate like 1/43200s returns (1, 43200)."""
        throttle = TagQueryThrottle()
        self.assertEqual(throttle.parse_rate("1/43200s"), (1, 43200))
        self.assertEqual(throttle.parse_rate("1/12h"), (1, 43200))


class TagQueryThrottleGetCacheKeyTest(TestCase):
    """Tests for TagQueryThrottle.get_cache_key."""

    def test_get_cache_key_no_customer_returns_none(self):
        """When request.user has no customer, return None (AttributeError path)."""
        throttle = TagQueryThrottle()
        request = Mock()
        # User with no .customer so request.user.customer raises AttributeError
        request.user = type("User", (), {})()
        self.assertIsNone(throttle.get_cache_key(request, None))

    def test_get_cache_key_no_tag_keys_returns_none(self):
        """When query has no tag group_by, return None."""
        throttle = TagQueryThrottle()
        request = Mock()
        request.user.customer.schema_name = "acct"
        request.query_params = {"start_date": "2024-01-01", "end_date": "2024-12-31"}
        self.assertIsNone(throttle.get_cache_key(request, None))

    def test_get_cache_key_date_range_under_limit_returns_none(self):
        """When date range < 30 days, return None."""
        throttle = TagQueryThrottle()
        request = Mock()
        request.user.customer.schema_name = "acct"
        request.query_params = {
            "group_by[tag:app]": "*",
            "start_date": "2024-01-01",
            "end_date": "2024-01-15",
        }
        self.assertIsNone(throttle.get_cache_key(request, None))

    @patch("api.common.throttling.is_feature_flag_enabled_by_schema", return_value=False)
    def test_get_cache_key_flag_disabled_returns_none(self, mock_flag):
        """When Unleash flag is off, return None."""
        throttle = TagQueryThrottle()
        request = Mock()
        request.user.customer.schema_name = "acct"
        request.query_params = {
            "group_by[tag:app]": "*",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        }
        self.assertIsNone(throttle.get_cache_key(request, None))

    @patch("api.common.throttling.is_feature_flag_enabled_by_schema", return_value=True)
    def test_get_cache_key_success_returns_key(self, mock_flag):
        """When all conditions pass, return cache key."""
        throttle = TagQueryThrottle()
        request = Mock()
        request.user.customer.schema_name = "acct123"
        request.query_params = {
            "group_by[tag:app]": "*",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        }
        key = throttle.get_cache_key(request, None)
        self.assertIsNotNone(key)
        self.assertEqual(key, "tag_query_throttle:acct123")


class TagQueryThrottleGetDateRangeDaysTest(TestCase):
    """Tests for TagQueryThrottle._get_date_range_days."""

    def test_missing_dates_returns_zero(self):
        """When start_date or end_date missing, return 0."""
        self.assertEqual(TagQueryThrottle._get_date_range_days({}), 0)
        self.assertEqual(TagQueryThrottle._get_date_range_days({"start_date": "2024-01-01"}), 0)
        self.assertEqual(TagQueryThrottle._get_date_range_days({"end_date": "2024-12-31"}), 0)

    def test_valid_dates_returns_days(self):
        """Valid start_date and end_date return difference in days."""
        params = {"start_date": "2024-01-01", "end_date": "2024-01-31"}
        self.assertEqual(TagQueryThrottle._get_date_range_days(params), 30)

    def test_invalid_date_format_returns_zero(self):
        """Invalid date strings raise ValueError/TypeError; return 0."""
        params = {"start_date": "not-a-date", "end_date": "2024-12-31"}
        self.assertEqual(TagQueryThrottle._get_date_range_days(params), 0)
