#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for API throttling classes."""
from unittest.mock import Mock
from unittest.mock import patch

from django.test import TestCase

from api.common.throttling import AwsTagQueryThrottle
from api.common.throttling import OcpTagQueryThrottle


class OcpTagQueryThrottleParseRateTest(TestCase):
    """Tests for OcpTagQueryThrottle.parse_rate."""

    def test_parse_rate_none_returns_none_none(self):
        """When rate is None, return (None, None)."""
        throttle = OcpTagQueryThrottle()
        self.assertEqual(throttle.parse_rate(None), (None, None))

    def test_parse_rate_invalid_period_returns_none_none(self):
        """When period does not match digits+unit, return (None, None)."""
        throttle = OcpTagQueryThrottle()
        self.assertEqual(throttle.parse_rate("1/invalid"), (None, None))
        self.assertEqual(throttle.parse_rate("1/"), (None, None))

    def test_parse_rate_valid_returns_requests_and_duration(self):
        """Valid rate like 1/43200s returns (1, 43200)."""
        throttle = OcpTagQueryThrottle()
        self.assertEqual(throttle.parse_rate("1/43200s"), (1, 43200))
        self.assertEqual(throttle.parse_rate("1/12h"), (1, 43200))


class OcpTagQueryThrottleGetCacheKeyTest(TestCase):
    """Tests for OcpTagQueryThrottle.get_cache_key."""

    def test_get_cache_key_no_customer_returns_none(self):
        """When request.user has no customer, return None (AttributeError path)."""
        throttle = OcpTagQueryThrottle()
        request = Mock()
        # User with no .customer so request.user.customer raises AttributeError
        request.user = type("User", (), {})()
        self.assertIsNone(throttle.get_cache_key(request, None))

    def test_get_cache_key_no_tag_keys_returns_none(self):
        """When query has no tag group_by, return None."""
        throttle = OcpTagQueryThrottle()
        request = Mock()
        request.user.customer.schema_name = "acct"
        request.query_params = {"start_date": "2024-01-01", "end_date": "2024-12-31"}
        self.assertIsNone(throttle.get_cache_key(request, None))

    def test_get_cache_key_date_range_under_limit_returns_none(self):
        """When date range < 30 days, return None."""
        throttle = OcpTagQueryThrottle()
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
        throttle = OcpTagQueryThrottle()
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
        throttle = OcpTagQueryThrottle()
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


class OcpTagQueryThrottleGetDateRangeDaysTest(TestCase):
    """Tests for OcpTagQueryThrottle._get_date_range_days."""

    def test_missing_dates_returns_zero(self):
        """When start_date or end_date missing, return 0."""
        self.assertEqual(OcpTagQueryThrottle._get_date_range_days({}), 0)
        self.assertEqual(OcpTagQueryThrottle._get_date_range_days({"start_date": "2024-01-01"}), 0)
        self.assertEqual(OcpTagQueryThrottle._get_date_range_days({"end_date": "2024-12-31"}), 0)

    def test_valid_dates_returns_days(self):
        """Valid start_date and end_date return difference in days."""
        params = {"start_date": "2024-01-01", "end_date": "2024-01-31"}
        self.assertEqual(OcpTagQueryThrottle._get_date_range_days(params), 30)

    def test_invalid_date_format_returns_zero(self):
        """Invalid date strings raise ValueError/TypeError; return 0."""
        params = {"start_date": "not-a-date", "end_date": "2024-12-31"}
        self.assertEqual(OcpTagQueryThrottle._get_date_range_days(params), 0)


class AwsTagQueryThrottleGetCacheKeyTest(TestCase):
    """Tests for AwsTagQueryThrottle.get_cache_key."""

    def test_get_cache_key_no_customer_returns_none(self):
        """When request.user has no customer, return None."""
        throttle = AwsTagQueryThrottle()
        request = Mock()
        request.user = type("User", (), {})()
        request.query_params = {
            "filter[tag:namespace]": "x",
            "time_scope_units": "month",
            "time_scope_value": "-1",
        }
        self.assertIsNone(throttle.get_cache_key(request, None))

    def test_get_cache_key_no_tag_returns_none(self):
        """When query has no tag in filter or group_by, return None."""
        throttle = AwsTagQueryThrottle()
        request = Mock()
        request.user.customer.schema_name = "acct123"
        request.query_params = {
            "time_scope_units": "month",
            "time_scope_value": "-1",
        }
        self.assertIsNone(throttle.get_cache_key(request, None))

    def test_get_cache_key_light_time_scope_returns_none(self):
        """When time_scope is not heavy (e.g. day/-1), return None."""
        throttle = AwsTagQueryThrottle()
        request = Mock()
        request.user.customer.schema_name = "acct123"
        request.query_params = {
            "filter[tag:namespace]": "x",
            "time_scope_units": "day",
            "time_scope_value": "-1",
        }
        self.assertIsNone(throttle.get_cache_key(request, None))

    @patch("api.common.throttling.is_feature_flag_enabled_by_schema", return_value=False)
    def test_get_cache_key_flag_disabled_returns_none(self, mock_flag):
        """When Unleash flag is off, return None."""
        throttle = AwsTagQueryThrottle()
        request = Mock()
        request.user.customer.schema_name = "acct123"
        request.query_params = {
            "filter[tag:namespace]": "x",
            "time_scope_units": "month",
            "time_scope_value": "-1",
        }
        self.assertIsNone(throttle.get_cache_key(request, None))

    @patch("api.common.throttling.is_feature_flag_enabled_by_schema", return_value=True)
    def test_get_cache_key_success_returns_aws_key(self, mock_flag):
        """When all conditions pass, return AWS cache key."""
        throttle = AwsTagQueryThrottle()
        request = Mock()
        request.user.customer.schema_name = "acct6083048"
        request.query_params = {
            "filter[tag:namespace]": "value",
            "time_scope_units": "month",
            "time_scope_value": "-1",
        }
        key = throttle.get_cache_key(request, None)
        self.assertIsNotNone(key)
        self.assertEqual(key, "tag_query_throttle:aws:acct6083048")

    @patch("api.common.throttling.is_feature_flag_enabled_by_schema", return_value=True)
    def test_get_cache_key_group_by_tag_returns_key(self, mock_flag):
        """When group_by has tag (not only filter), still throttle."""
        throttle = AwsTagQueryThrottle()
        request = Mock()
        request.user.customer.schema_name = "acct99"
        request.query_params = {
            "group_by[tag:app]": "*",
            "time_scope_units": "month",
            "time_scope_value": "-1",
        }
        key = throttle.get_cache_key(request, None)
        self.assertIsNotNone(key)
        self.assertEqual(key, "tag_query_throttle:aws:acct99")

    @patch("api.common.throttling.is_feature_flag_enabled_by_schema", return_value=True)
    def test_get_cache_key_month_minus_2_and_minus_3_are_heavy(self, mock_flag):
        """Month scope with -2 or -3 (2 or 3 months) is also considered heavy."""
        throttle = AwsTagQueryThrottle()
        request = Mock()
        request.user.customer.schema_name = "acct123"
        for value in ("-2", "-3"):
            with self.subTest(time_scope_value=value):
                request.query_params = {
                    "filter[tag:env]": "prod",
                    "time_scope_units": "month",
                    "time_scope_value": value,
                }
                key = throttle.get_cache_key(request, None)
                self.assertIsNotNone(key, f"time_scope_value={value} should be heavy")
                self.assertEqual(key, "tag_query_throttle:aws:acct123")

    @patch("api.common.throttling.is_feature_flag_enabled_by_schema", return_value=True)
    def test_get_cache_key_filter_prefix_keys_returns_key(self, mock_flag):
        """Real API sends filter[time_scope_units] and filter[time_scope_value]; throttle must apply."""
        throttle = AwsTagQueryThrottle()
        request = Mock()
        request.user.customer.schema_name = "acct7049367"
        request.query_params = {
            "filter[tag:namespace]": "vulnerability-engine-stage",
            "filter[time_scope_units]": "month",
            "filter[time_scope_value]": "-1",
            "filter[resolution]": "monthly",
            "group_by[service]": "*",
        }
        key = throttle.get_cache_key(request, None)
        self.assertIsNotNone(key, "filter[] param keys must be recognized as heavy")
        self.assertEqual(key, "tag_query_throttle:aws:acct7049367")
