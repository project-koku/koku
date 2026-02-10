#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Custom throttling classes for the Koku API."""
import logging
from datetime import datetime

from rest_framework.throttling import SimpleRateThrottle

from masu.processor import is_feature_flag_enabled_by_schema
from masu.processor import TAG_QUERY_RATE_LIMIT_FLAG

LOG = logging.getLogger(__name__)


class TagQueryThrottle(SimpleRateThrottle):
    """
    Throttle large date range tag queries for flagged customers.

    This throttle limits tag group-by queries with date ranges >= 30 days
    to one request per 12 hours for customers flagged via Unleash.

    Smaller date ranges are always allowed, encouraging customers to
    use more efficient query patterns.
    """

    scope = "tag_query"
    rate = "1/43200s"  # 1 request per 12 hours (43200 seconds)
    DAYS_RANGE_LIMIT = 30

    def get_cache_key(self, request, view):
        """
        Return a cache key if this request should be throttled.

        Returns None to skip throttling for:
        - Customers not flagged in Unleash
        - Requests without tag group-by parameters
        - Requests with date ranges < 30 days
        """
        # Get schema name
        try:
            schema_name = request.user.customer.schema_name
        except AttributeError:
            return None  # No customer context, skip throttling

        # Check for tag group-by parameters
        tag_keys = self._extract_tag_keys(request.query_params)
        if not tag_keys:
            return None

        # Only throttle customers flagged in Unleash
        if not is_feature_flag_enabled_by_schema(schema_name, TAG_QUERY_RATE_LIMIT_FLAG):
            return None

        # Check date range
        date_range_days = self._get_date_range_days(request.query_params)
        if date_range_days < self.DAYS_RANGE_LIMIT:
            return None

        # Build cache key: schema + sorted tag keys
        tag_keys_str = ",".join(sorted(tag_keys))
        cache_key = f"tag_query_throttle:{schema_name}:{tag_keys_str}"

        LOG.debug(f"Tag query throttle check: {cache_key}, date_range: {date_range_days} days")
        return cache_key

    def _extract_tag_keys(self, query_params):
        """Extract tag group-by keys from query parameters."""
        return [key for key in query_params if "group_by" in key and "tag:" in key]

    def _get_date_range_days(self, query_params):
        """Calculate the date range in days from query parameters."""
        start_date_str = query_params.get("start_date")
        end_date_str = query_params.get("end_date")

        if not start_date_str or not end_date_str:
            return 0  # Default to not throttling if dates missing

        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
            return (end_date - start_date).days
        except (ValueError, TypeError):
            return 0
