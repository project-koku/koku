#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Custom throttling classes for the Koku API."""
import logging
import re
from datetime import datetime

from rest_framework.throttling import SimpleRateThrottle

from api.report.constants import TIME_SCOPE_UNITS_MONTHLY
from api.report.constants import TIME_SCOPE_VALUES_MONTHLY
from masu.processor import is_feature_flag_enabled_by_schema
from masu.processor import TAG_QUERY_RATE_LIMIT_FLAG

LOG = logging.getLogger(__name__)


class BaseTagQueryThrottle(SimpleRateThrottle):
    """
    Base throttle for tag-based report queries with a large time/date scope."""

    rate = "1/43200s"  # 1 request per 12 hours (43200 seconds)
    cache_key_label = ""  # Subclass sets e.g. "aws" for "tag_query_throttle:aws:{schema}"

    def parse_rate(self, rate):
        """Parse rate string; supports 43200s and 12h."""
        return self._parse_tag_throttle_rate(rate)

    def get_cache_key(self, request, view):
        """
        Return a cache key if this request should be throttled.

        Returns None to skip throttling when: no schema, no tag query, not heavy, or flag off.
        """
        schema_name = self._get_schema_name(request)
        if schema_name is None:
            return None

        if not self._has_tag_query(request.query_params):
            return None

        if not self._is_heavy_query(request.query_params):
            return None

        if not is_feature_flag_enabled_by_schema(schema_name, TAG_QUERY_RATE_LIMIT_FLAG):
            return None

        cache_key = self._build_cache_key(schema_name)
        LOG.debug("Tag query throttle check: %s", cache_key)
        return cache_key

    @staticmethod
    def _get_schema_name(request):
        """Return request.user.customer.schema_name or None if not available."""
        try:
            return request.user.customer.schema_name
        except AttributeError:
            return None

    @staticmethod
    def _get_param_keys_with_tag(query_params):
        """
        Return query param keys that contain 'tag:' in a filter or group_by context.

        E.g. filter[tag:namespace], group_by[tag:app].
        """
        return [key for key in query_params if "tag:" in key and ("filter" in key or "group_by" in key)]

    @staticmethod
    def _parse_tag_throttle_rate(rate):
        """
        Parse rate string 'num/duration' where duration is e.g. 43200s or 12h.

        DRF's default only supports a single unit letter (s/m/h/d), so we use this
        to support a numeric prefix like 43200s (43200 seconds).
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

    def _has_tag_query(self, query_params):
        """Return True if the request has a tag-based query (filter or group_by). Subclass implements."""
        raise NotImplementedError

    def _is_heavy_query(self, query_params):
        """Return True if the request uses a heavy time/date scope. Subclass implements."""
        raise NotImplementedError

    def _build_cache_key(self, schema_name):
        """Build the throttle cache key for this schema."""
        if self.cache_key_label:
            return f"tag_query_throttle:{self.cache_key_label}:{schema_name}"
        return f"tag_query_throttle:{schema_name}"


class OcpTagQueryThrottle(BaseTagQueryThrottle):
    """
    Throttle large date range tag queries for OCP (OpenShift) reports for flagged customers.

    This throttle limits tag group-by queries with date ranges > 30 days
    to one request per 12 hours for customers flagged via Unleash.

    Smaller date ranges are always allowed, encouraging customers to
    use more efficient query patterns. Applies only to OCP report views.
    """

    scope = "tag_query"
    DAYS_RANGE_LIMIT = 31

    def _has_tag_query(self, query_params):
        """OCP: only group_by with tag counts."""
        keys = [k for k in self._get_param_keys_with_tag(query_params) if "group_by" in k]
        return bool(keys)

    def _is_heavy_query(self, query_params):
        """OCP: heavy when start_date/end_date range >= DAYS_RANGE_LIMIT."""
        return self._get_date_range_days(query_params) >= self.DAYS_RANGE_LIMIT

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


class AwsTagQueryThrottle(BaseTagQueryThrottle):
    """
    Throttle heavy AWS report queries that use tag (filter or group_by) and large time scope.

    Limits such requests to one per 12 hours per schema for customers flagged via
    the same Unleash flag as OcpTagQueryThrottle (cost-management.backend.rate-limit-tag-queries).
    """

    scope = "aws_tag_query"
    cache_key_label = "aws"

    def _has_tag_query(self, query_params):
        """AWS: any param with tag in filter or group_by."""
        return bool(self._get_param_keys_with_tag(query_params))

    @staticmethod
    def _get_param_value(query_params, key):
        """Return param value from either key or filter[key] (API sends filter[time_scope_units] etc)."""
        return query_params.get(key) or query_params.get(f"filter[{key}]") or ""

    def _is_heavy_query(self, query_params):
        """AWS: heavy when time_scope_units=month and time_scope_value in (-1, -2, -3)."""
        units = self._get_param_value(query_params, "time_scope_units").strip().lower()
        value_str = self._get_param_value(query_params, "time_scope_value").strip()
        return units == TIME_SCOPE_UNITS_MONTHLY and value_str in TIME_SCOPE_VALUES_MONTHLY
