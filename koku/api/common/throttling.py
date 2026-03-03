#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Custom throttling classes for the Koku API."""
import logging
import re
from datetime import datetime

from rest_framework.throttling import SimpleRateThrottle

from masu.processor import is_feature_flag_enabled_by_schema
from masu.processor import TAG_QUERY_RATE_LIMIT_FLAG

LOG = logging.getLogger(__name__)


def _get_param_keys_with_tag(query_params):
    """
    Return query param keys that contain 'tag:' in a filter or group_by context.

    E.g. filter[tag:namespace], group_by[tag:app]. Used by both OCP and AWS throttles;
    OCP then filters to group_by only, AWS accepts filter or group_by.
    """
    return [key for key in query_params if "tag:" in key and ("filter" in key or "group_by" in key)]


def _parse_tag_throttle_rate(rate):
    """
    Parse rate string 'num/duration' where duration is e.g. 43200s or 12h.

    DRF's default only supports a single unit letter (s/m/h/d), so we use this
    to support a numeric prefix like 43200s (43200 seconds). Shared by OCP and AWS throttles.
    """
    if rate is None:
        return (None, None)
    num, period = rate.split("/")
    num_requests = int(num)
    match = re.match(r"^(\d+)([smhd])$", period.strip().lower())
    if match:
        amount, unit = int(match.group(1)), match.group(2)
        duration = amount * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
        return (num_requests, duration)
    return (None, None)


def _get_schema_name(request):
    """Return request.user.customer.schema_name or None if not available."""
    try:
        return request.user.customer.schema_name
    except AttributeError:
        return None


class OcpTagQueryThrottle(SimpleRateThrottle):
    """
    Throttle large date range tag queries for OCP (OpenShift) reports for flagged customers.

    This throttle limits tag group-by queries with date ranges > 30 days
    to one request per 12 hours for customers flagged via Unleash.

    Smaller date ranges are always allowed, encouraging customers to
    use more efficient query patterns. Applies only to OCP report views.
    """

    scope = "tag_query"
    rate = "1/43200s"  # 1 request per 12 hours (43200 seconds)
    DAYS_RANGE_LIMIT = 31

    def parse_rate(self, rate):
        """Parse rate string; supports 43200s and 12h."""
        return _parse_tag_throttle_rate(rate)

    def get_cache_key(self, request, view):
        """
        Return a cache key if this request should be throttled.

        Returns None to skip throttling for:
        - Customers not flagged in Unleash
        - Requests without tag group-by parameters
        - Requests with date ranges < 30 days
        """
        schema_name = _get_schema_name(request)
        if schema_name is None:
            return None

        tag_keys = self._extract_tag_keys(request.query_params)
        if not tag_keys:
            return None

        date_range_days = self._get_date_range_days(request.query_params)
        if date_range_days < self.DAYS_RANGE_LIMIT:
            return None

        if not is_feature_flag_enabled_by_schema(schema_name, TAG_QUERY_RATE_LIMIT_FLAG):
            return None

        cache_key = f"tag_query_throttle:{schema_name}"
        LOG.debug(f"Tag query throttle check: {cache_key}, date_range: {date_range_days} days")
        return cache_key

    @staticmethod
    def _extract_tag_keys(query_params):
        """Extract tag group-by keys from query parameters (OCP uses group_by only)."""
        return [key for key in _get_param_keys_with_tag(query_params) if "group_by" in key]

    @staticmethod
    def _get_date_range_days(query_params):
        """Calculate the date range in days from query parameters."""
        start_date_str = query_params.get("start_date")
        end_date_str = query_params.get("end_date")

        if not start_date_str or not end_date_str:
            return 0

        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
            return (end_date - start_date).days
        except (ValueError, TypeError):
            return 0


class AwsTagQueryThrottle(SimpleRateThrottle):
    """
    Throttle heavy AWS report queries that use tag (filter or group_by) and large time scope.

    Limits such requests to one per 12 hours per schema for customers flagged via
    the same Unleash flag as OcpTagQueryThrottle (cost-management.backend.rate-limit-tag-queries).
    """

    scope = "aws_tag_query"
    rate = "1/43200s"  # 1 request per 12 hours (43200 seconds)

    def parse_rate(self, rate):
        """Parse rate string; supports 43200s and 12h."""
        return _parse_tag_throttle_rate(rate)

    def get_cache_key(self, request, view):
        """
        Return a cache key if this request should be throttled.

        Returns None to skip throttling for:
        - Customers not flagged in Unleash
        - Requests without tag in filter or group_by
        - Requests without heavy time scope (month/-1)
        """
        schema_name = _get_schema_name(request)
        if schema_name is None:
            return None

        if not self._has_tag_in_filter_or_group_by(request.query_params):
            return None

        if not self._is_aws_heavy_time_scope(request.query_params):
            return None

        if not is_feature_flag_enabled_by_schema(schema_name, TAG_QUERY_RATE_LIMIT_FLAG):
            return None

        cache_key = f"tag_query_throttle:aws:{schema_name}"
        LOG.debug(f"AWS tag query throttle check: {cache_key}")
        return cache_key

    @staticmethod
    def _has_tag_in_filter_or_group_by(query_params):
        """Return True if any query param has tag in filter or group_by (AWS uses both)."""
        return bool(_get_param_keys_with_tag(query_params))

    @staticmethod
    def _is_aws_heavy_time_scope(query_params):
        """
        Return True if the request uses a heavy time scope (>= 31 days equivalent).

        For AWS reports we use time_scope_units and time_scope_value.
        Consider heavy when time_scope_units=month and time_scope_value is -1, -2, or -3
        (1, 2, or 3 months of data; API allows these per TIME_SCOPE_VALUES_MONTHLY).
        """
        units = (query_params.get("time_scope_units") or "").strip().lower()
        value_str = (query_params.get("time_scope_value") or "").strip()
        if units == "month" and value_str in ("-1", "-2", "-3"):
            return True
        return False
