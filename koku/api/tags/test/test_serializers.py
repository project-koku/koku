#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the tag serializer."""
from unittest import TestCase

from rest_framework import serializers

from api.tags.serializers import AWSFilterSerializer
from api.tags.serializers import AWSTagsQueryParamSerializer
from api.tags.serializers import FilterSerializer
from api.tags.serializers import OCPFilterSerializer
from api.tags.serializers import OCPTagsQueryParamSerializer
from api.tags.serializers import TagsQueryParamSerializer
from api.utils import DateHelper


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
            "account": "myaccount",
        }
        serializer = AWSFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_filter_params_w_project_failure(self):
        """Test parse of a filter param with an invalid project."""
        filter_params = {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day", "account": 3}
        serializer = AWSFilterSerializer(data=filter_params)
        self.assertFalse(serializer.is_valid())

    def test_parse_filter_params_type_fail(self):
        """Test parse of a filter param with type for invalid type."""
        types = ["aws_tags", "pod", "storage"]
        for tag_type in types:
            filter_params = {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day", "type": None}
            filter_params["type"] = tag_type
            serializer = AWSFilterSerializer(data=filter_params)
            self.assertFalse(serializer.is_valid())


class OCPFilterSerializerTest(TestCase):
    """Tests for the OCP filter serializer."""

    def test_parse_filter_params_w_project_success(self):
        """Test parse of a filter param with project successfully."""
        filter_params = {
            "resolution": "daily",
            "time_scope_value": "-10",
            "time_scope_units": "day",
            "project": "myproject",
        }
        serializer = OCPFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_filter_params_w_project_failure(self):
        """Test parse of a filter param with an invalid project."""
        filter_params = {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day", "project": 3}
        serializer = OCPFilterSerializer(data=filter_params)
        self.assertFalse(serializer.is_valid())

    def test_parse_filter_params_type_success(self):
        """Test parse of a filter param with type successfully."""
        types = ["pod", "storage"]
        for tag_type in types:
            filter_params = {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day", "type": None}
            filter_params["type"] = tag_type
            serializer = OCPFilterSerializer(data=filter_params)
            self.assertTrue(serializer.is_valid())

    def test_parse_filter_params_type_fail(self):
        """Test parse of a filter param with type for invalid type."""
        types = ["bad1", "aws_tags"]
        for tag_type in types:
            filter_params = {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day", "type": None}
            filter_params["type"] = tag_type
            serializer = OCPFilterSerializer(data=filter_params)
            self.assertFalse(serializer.is_valid())


class TagsQueryParamSerializerTest(TestCase):
    """Tests for the handling query parameter parsing serializer."""

    def test_parse_query_params_success(self):
        """Test parse of a query params successfully."""
        query_params = {"filter": {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day"}}
        serializer = TagsQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_query_params_ocp_invalid_fields(self):
        """Test parse of query params for invalid fields."""
        query_params = {
            "filter": {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day", "invalid": "param"}
        }
        serializer = OCPTagsQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_query_params_aws_invalid_fields(self):
        """Test parse of query params for invalid fields."""
        query_params = {
            "filter": {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day", "invalid": "param"}
        }
        serializer = AWSTagsQueryParamSerializer(data=query_params)
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
                "filter": {"resolution": "daily"},
            },
            {
                "start_date": dh.last_month_start.date(),
                "end_date": dh.last_month_end.date(),
                "filter": {"resolution": "daily"},
            },
        ]

        for params in scenarios:
            with self.subTest(params=params):
                serializer = TagsQueryParamSerializer(data=params)
                self.assertTrue(serializer.is_valid(raise_exception=True))

    def test_parse_filter_dates_invalid(self):
        """Test parse of invalid data for filter date-based param should not succeed."""
        dh = DateHelper()
        scenarios = [
            {"start_date": dh.today.date()},
            {"end_date": dh.today.date()},
            {"start_date": dh.yesterday.date(), "end_date": dh.tomorrow.date()},
            {"start_date": dh.n_days_ago(dh.last_month_start, 1), "end_date": dh.today.date()},
            {"start_date": dh.today.date(), "end_date": dh.yesterday.date()},
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
                serializer = TagsQueryParamSerializer(data=params)
                self.assertFalse(serializer.is_valid())
