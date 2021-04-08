#
# Copyright 2020 Red Hat, Inc.
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
"""Test the organizations serializer."""
from unittest import TestCase

from rest_framework import serializers

from api.organizations.serializers import AWSOrgFilterSerializer
from api.organizations.serializers import FilterSerializer
from api.organizations.serializers import OrgQueryParamSerializer
from api.utils import DateHelper
from api.utils import materialized_view_month_start


class FilterSerializerTest(TestCase):
    """Tests for the filter serializer."""

    def test_parse_filter_params_success(self):
        """Test parse of a filter param successfully."""
        filter_params = {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day"}
        serializer = FilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_filter_no_params_success(self):
        """Test parse of a filter param successfully."""
        filter_params = {}
        serializer = FilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_filter_params_invalid_fields(self):
        """Test parse of filter params for invalid fields."""
        filter_params = {
            "resolution": "daily",
            "time_scope_value": "-10",
            "time_scope_units": "day",
            "invalid": "param",
        }
        serializer = FilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_time_scope_daily(self):
        """Test parse of filter params for invalid daily time_scope_units."""
        filter_params = {"resolution": "daily", "time_scope_value": "-1", "time_scope_units": "day"}
        serializer = FilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_time_scope_monthly(self):
        """Test parse of filter params for invalid month time_scope_units."""
        filter_params = {"resolution": "monthly", "time_scope_value": "-10", "time_scope_units": "month"}
        serializer = FilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_limit_time_scope_resolution(self):
        """Test parse of filter params for invalid resolution time_scope_units."""
        filter_params = {"resolution": "monthly", "time_scope_value": "-10", "time_scope_units": "day"}
        serializer = FilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class AWSFilterSerializerTest(TestCase):
    """Tests for the AWS filter serializer."""

    def test_parse_filter_params_w_project_success(self):
        """Test parse of a filter param with project successfully."""
        filter_params = {
            "resolution": "daily",
            "time_scope_value": "-10",
            "time_scope_units": "day",
            "org_unit_id": "r-id",
        }
        serializer = AWSOrgFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_filter_params_w_project_failure(self):
        """Test parse of a filter param with an invalid project."""
        filter_params = {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day", "account": 3}
        serializer = AWSOrgFilterSerializer(data=filter_params)
        self.assertFalse(serializer.is_valid())

    def test_parse_filter_params_type_fail(self):
        """Test parse of a filter param with type for invalid type."""
        types = ["aws_tags", "pod", "storage"]
        for tag_type in types:
            filter_params = {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day", "type": None}
            filter_params["type"] = tag_type
            serializer = AWSOrgFilterSerializer(data=filter_params)
            self.assertFalse(serializer.is_valid())


class OrgQueryParamSerializerTest(TestCase):
    """Tests for the handling query parameter parsing serializer."""

    def test_parse_query_params_success(self):
        """Test parse of a query params successfully."""
        query_params = {
            "filter": {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day"},
            "limit": "5",
            "offset": "3",
        }
        serializer = OrgQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_query_params_invalid_fields(self):
        """Test parse of query params for invalid fields."""
        query_params = {"invalid": "invalid"}
        serializer = OrgQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_parse_filter_dates_valid(self):
        """Test parse of a filter date-based param should succeed."""
        dh = DateHelper()
        scenarios = [
            {"start_date": dh.yesterday.date(), "end_date": dh.today.date()},
            {"start_date": dh.this_month_start.date(), "end_date": dh.today.date()},
            {
                "start_date": dh.last_month_end.date(),
                "end_date": dh.this_month_start.date(),
                "filter": {"resolution": "monthly"},
            },
            {
                "start_date": dh.last_month_start.date(),
                "end_date": dh.last_month_end.date(),
                "filter": {"resolution": "monthly"},
            },
        ]

        for params in scenarios:
            with self.subTest(params=params):
                serializer = OrgQueryParamSerializer(data=params)
                self.assertTrue(serializer.is_valid(raise_exception=True))

    def test_parse_filter_dates_invalid(self):
        """Test parse of invalid data for filter date-based param should not succeed."""
        dh = DateHelper()
        scenarios = [
            {"start_date": dh.today.date()},
            {"end_date": dh.today.date()},
            {"start_date": dh.yesterday.date(), "end_date": dh.tomorrow.date()},
            {"start_date": dh.n_days_ago(materialized_view_month_start(dh), 1).date(), "end_date": dh.today.date()},
            {"start_date": "llamas", "end_date": dh.yesterday.date()},
            {"start_date": dh.yesterday.date(), "end_date": "alpacas"},
            {"start_date": "llamas", "end_date": "alpacas"},
            {
                "start_date": dh.last_month_start.date(),
                "end_date": dh.last_month_end.date(),
                "filter": {"time_scope_units": "day"},
            },
            {
                "start_date": dh.last_month_start.date(),
                "end_date": dh.last_month_end.date(),
                "filter": {"time_scope_value": "-1"},
            },
            {
                "start_date": dh.last_month_start.date(),
                "end_date": dh.last_month_end.date(),
                "filter": {"time_scope_units": "day", "time_scope_value": "-1"},
            },
        ]

        for params in scenarios:
            with self.subTest(params=params):
                serializer = OrgQueryParamSerializer(data=params)
                self.assertFalse(serializer.is_valid())
