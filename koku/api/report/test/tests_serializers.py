#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Report serializers."""
from unittest import TestCase
from unittest.mock import Mock

from dateutil.relativedelta import relativedelta
from rest_framework import serializers
from rest_framework.serializers import ValidationError

from api.iam.test.iam_test_case import IamTestCase
from api.report.aws.serializers import FilterSerializer
from api.report.aws.serializers import GroupBySerializer
from api.report.aws.serializers import OrderBySerializer
from api.report.aws.serializers import QueryParamSerializer
from api.report.serializers import ParamSerializer
from api.utils import DateHelper
from api.utils import materialized_view_month_start


class FilterSerializerTest(TestCase):
    """Tests for the filter serializer."""

    def test_parse_filter_params_success(self):
        """Test parse of a filter param successfully."""
        filter_params = {
            "resolution": "daily",
            "time_scope_value": "-10",
            "time_scope_units": "day",
            "resource_scope": [],
        }
        serializer = FilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_filter_params_no_time(self):
        """Test parse of a filter param no time filter."""
        filter_params = {"resource_scope": ["S3"]}
        serializer = FilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_filter_params_invalid_fields(self):
        """Test parse of filter params for invalid fields."""
        filter_params = {
            "resolution": "daily",
            "time_scope_value": "-10",
            "time_scope_units": "day",
            "resource_scope": [],
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

    def test_filter_params_invalid_limit(self):
        """Test parse of filter params for invalid month time_scope_units."""
        filter_params = {
            "resolution": "monthly",
            "time_scope_value": "-1",
            "time_scope_units": "month",
            "limit": "invalid",
        }
        serializer = FilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ["valid_tag"]
        query_params = {"valid_tag": "value"}
        serializer = FilterSerializer(data=query_params, tag_keys=tag_keys)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"bad_tag": "value"}
        serializer = FilterSerializer(data=query_params, tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_with_or_string_success_single_item(self):
        """Test that the or: prefix is allowed with a string of items."""
        filter_params = {
            "resolution": "daily",
            "time_scope_value": "-10",
            "time_scope_units": "day",
            "or:account": "account1",
            "resource_scope": [],
        }
        serializer = FilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_filter_params_with_or_string_success_multi_item(self):
        """Test that the or: prefix is allowed with a string of items."""
        filter_params = {
            "resolution": "daily",
            "time_scope_value": "-10",
            "time_scope_units": "day",
            "or:az": "az1,az2",
            "resource_scope": [],
        }
        serializer = FilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_filter_params_with_or_list_success_single_item(self):
        """Test that the or: prefix is allowed with a list."""
        filter_params = {
            "resolution": "daily",
            "time_scope_value": "-10",
            "time_scope_units": "day",
            "or:service": ["service1"],
            "resource_scope": [],
        }
        serializer = FilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_filter_params_with_or_list_success_multi_item(self):
        """Test that the or: prefix is allowed with a list."""
        filter_params = {
            "resolution": "daily",
            "time_scope_value": "-10",
            "time_scope_units": "day",
            "or:region": ["region1", "region2"],
            "resource_scope": [],
        }
        serializer = FilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_filter_params_with_and_string_success(self):
        """Test that the and: prefix is allowed with a string of items."""
        filter_params = {
            "resolution": "daily",
            "time_scope_value": "-10",
            "time_scope_units": "day",
            "and:product_family": "fam1,fam2",
            "resource_scope": [],
        }
        serializer = FilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_filter_params_with_and_list_success(self):
        """Test that the and: prefix is allowed with a list."""
        filter_params = {
            "resolution": "daily",
            "time_scope_value": "-10",
            "time_scope_units": "day",
            "and:account": ["account1", "account2"],
            "resource_scope": [],
        }
        serializer = FilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_filter_params_with_and_string_success_single_item(self):
        """Test that the and: prefix succeeds with one item."""
        filter_params = {
            "resolution": "daily",
            "time_scope_value": "-10",
            "time_scope_units": "day",
            "and:account": "account1",
            "resource_scope": [],
        }
        serializer = FilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_filter_params_with_and_list_success_single_item(self):
        """Test that the and: prefix succeeds with one item."""
        filter_params = {
            "resolution": "daily",
            "time_scope_value": "-10",
            "time_scope_units": "day",
            "and:account": ["account1"],
            "resource_scope": [],
        }
        serializer = FilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_filter_params_with_and_failure_bad_param(self):
        """Test that and/or does not work on a field it is not allowed on."""
        filter_params = {
            "resolution": "daily",
            "time_scope_value": "-10",
            "time_scope_units": "day",
            "and:resolution": "daily",
            "resource_scope": [],
        }
        serializer = FilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_all_filter_op_fields(self):
        """Test that the allowed fields pass."""
        for field in FilterSerializer._opfields:
            field = "and:" + field
            filter_param = {field: ["1", "2"]}
            serializer = FilterSerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())
        for field in FilterSerializer._opfields:
            field = "or:" + field
            filter_param = {field: ["1", "2"]}
            serializer = FilterSerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())


class GroupBySerializerTest(TestCase):
    """Tests for the group_by serializer."""

    def test_parse_group_by_params_success(self):
        """Test parse of a group_by param successfully."""
        group_params = {"account": ["account1"]}
        serializer = GroupBySerializer(data=group_params)
        self.assertTrue(serializer.is_valid())

    def test_group_by_params_invalid_fields(self):
        """Test parse of group_by params for invalid fields."""
        group_params = {"account": ["account1"], "invalid": "param"}
        serializer = GroupBySerializer(data=group_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_group_by_params_string_list_fields(self):
        """Test group_by params for handling string to list fields."""
        group_params = {"account": "account1"}
        serializer = GroupBySerializer(data=group_params)
        validation = serializer.is_valid()
        self.assertTrue(validation)
        account_result = serializer.data.get("account")
        self.assertIsInstance(account_result, list)

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ["valid_tag"]
        query_params = {"valid_tag": "*"}
        serializer = GroupBySerializer(data=query_params, tag_keys=tag_keys)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"bad_tag": "*"}
        serializer = GroupBySerializer(data=query_params, tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_group_by_params_with_or_string_success_single_item(self):
        """Test that the or: prefix is allowed with a string of items."""
        group_by_params = {"or:account": "account1"}
        serializer = GroupBySerializer(data=group_by_params)
        self.assertTrue(serializer.is_valid())

    def test_group_by_params_with_or_string_success_multi_item(self):
        """Test that the or: prefix is allowed with a string of items."""
        group_by_params = {"or:account": "account1,account2"}
        serializer = GroupBySerializer(data=group_by_params)
        self.assertTrue(serializer.is_valid())

    def test_group_by_params_with_or_list_success_single_item(self):
        """Test that the or: prefix is allowed with a list."""
        group_by_params = {"or:account": ["account1"]}
        serializer = GroupBySerializer(data=group_by_params)
        self.assertTrue(serializer.is_valid())

    def test_group_by_params_with_or_list_success_multi_item(self):
        """Test that the or: prefix is allowed with a list."""
        group_by_params = {"or:account": ["account1", "account2"]}
        serializer = GroupBySerializer(data=group_by_params)
        self.assertTrue(serializer.is_valid())

    def test_group_by_params_with_and_string_success(self):
        """Test that the and: prefix is allowed with a string of items."""
        group_by_params = {"and:account": "account1,account2"}
        serializer = GroupBySerializer(data=group_by_params)
        self.assertTrue(serializer.is_valid())

    def test_group_by_params_with_and_list_success(self):
        """Test that the and: prefix is allowed with a list."""
        group_by_params = {"and:account": ["account1", "account2"]}
        serializer = GroupBySerializer(data=group_by_params)
        self.assertTrue(serializer.is_valid())

    def test_group_by_params_with_and_string_success_single_item(self):
        """Test that the and: prefix is okay with one item."""
        group_by_params = {"and:account": "account1"}
        serializer = GroupBySerializer(data=group_by_params)
        self.assertTrue(serializer.is_valid())

    def test_group_by_params_with_and_list_success_single_item(self):
        """Test that the and: prefix is okay with one item."""
        group_by_params = {"and:account": ["account1"]}
        serializer = GroupBySerializer(data=group_by_params)
        self.assertTrue(serializer.is_valid())

    def test_group_by_params_with_and_failure_bad_param(self):
        """Test that and/or does not work on a field it is not allowed on."""
        group_by_params = {"and:resolution": "daily"}
        serializer = GroupBySerializer(data=group_by_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_all_group_by_op_fields(self):
        """Test that the allowed fields pass."""
        for field in GroupBySerializer._opfields:
            field = "and:" + field
            filter_param = {field: ["1", "2"]}
            serializer = GroupBySerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())
        for field in GroupBySerializer._opfields:
            field = "or:" + field
            filter_param = {field: ["1", "2"]}
            serializer = GroupBySerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())

    def test_multiple_params(self):
        """Test that multiple group_by parameters works."""
        group_by_params = {"account": "account1", "project": "project1"}
        serializer = GroupBySerializer(data=group_by_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class OrderBySerializerTest(TestCase):
    """Tests for the order_by serializer."""

    def test_parse_order_by_params_success(self):
        """Test parse of a order_by param successfully."""
        order_params = {"usage": "asc"}
        serializer = OrderBySerializer(data=order_params)
        self.assertTrue(serializer.is_valid())

    def test_order_by_params_invalid_fields(self):
        """Test parse of order_by params for invalid fields."""
        order_params = {"cost": "asc", "invalid": "param"}
        serializer = OrderBySerializer(data=order_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_order_by_params_invalid_fields_or(self):
        """Test parse of order_by params for invalid fields."""
        order_params = {"or:cost": "asc", "invalid": "param"}
        serializer = OrderBySerializer(data=order_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class QueryParamSerializerTest(IamTestCase):
    """Tests for the handling query parameter parsing serializer."""

    def setUp(self):
        """setting up a user to test with."""
        self.user_data = self._create_user_data()
        self.alt_request_context = self._create_request_context(
            self.create_mock_customer_data(), self.user_data, create_tenant=True
        )

    def test_parse_query_params_success(self):
        """Test parse of a query params successfully."""
        query_params = {
            "group_by": {"account": ["account1"]},
            "order_by": {"usage": "asc"},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_scope": [],
            },
            "units": "byte",
        }
        serializer = QueryParamSerializer(data=query_params, context=self.alt_request_context)
        self.assertTrue(serializer.is_valid())

    def test_query_params_invalid_fields(self):
        """Test parse of query params for invalid fields."""
        query_params = {
            "group_by": {"account": ["account1"]},
            "order_by": {"cost": "asc"},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_scope": [],
            },
            "invalid": "param",
        }
        serializer = QueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_query_params_invalid_nested_fields(self):
        """Test parse of query params for invalid nested_fields."""
        query_params = {
            "group_by": {"invalid": ["invalid"]},
            "order_by": {"cost": "asc"},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_scope": [],
            },
        }
        serializer = QueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_parse_units_failure(self):
        """Test failure while parsing units query params."""
        query_params = {"units": "bites"}
        serializer = QueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_invalid_delta(self):
        """Test failure while handling invalid delta for different requests."""
        query_params = {"delta": "cost"}
        req = Mock(path="/api/cost-management/v1/reports/aws/storage/")
        serializer = QueryParamSerializer(data=query_params, context={"request": req})
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

        query_params = {"delta": "usage"}
        req = Mock(path="/api/cost-management/v1/reports/aws/costs/")
        serializer = QueryParamSerializer(data=query_params, context={"request": req})
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_invalid_cost_type(self):
        """Test failure while handling invalid cost_type."""
        query_params = {"cost_type": "invalid_cost"}
        serializer = QueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.validate_cost_type("invalid_cost")

    def test_valid_cost_type_no_exception(self):
        """Test that a valid cost type doesn't raise an exception."""
        query_params = {"cost_type": "blended_cost"}
        req = Mock(path="/api/cost-management/v1/reports/aws/costs/")
        serializer = QueryParamSerializer(data=query_params, context={"request": req})
        serializer.validate_cost_type("blended_cost")

    def test_multiple_group_by(self):
        """Test parse of query params with multiple group_bys."""
        query_params = {
            "group_by": {"account": ["account1"], "project": ["project1"]},
            "order_by": {"cost": "asc"},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_scope": [],
            },
        }
        serializer = QueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_multiple_group_by_with_matching_sort_or(self):
        """Test multiple group by with a matching sort for or group_by parameters."""
        query_params = {
            "group_by": {"or:account": "*", "or:region": "east"},
            "order_by": {"region": "asc"},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_scope": [],
            },
        }
        serializer = QueryParamSerializer(data=query_params, context=self.alt_request_context)
        self.assertTrue(serializer.is_valid())

    def test_multiple_group_by_with_matching_sort(self):
        """Test multiple group by with a matching sort for group_by parameters"""
        query_params = {
            "group_by": {"account": "*", "region": "east"},
            "order_by": {"region": "asc"},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_scope": [],
            },
        }
        serializer = QueryParamSerializer(data=query_params, context=self.alt_request_context)
        self.assertTrue(serializer.is_valid())

    def test_multiple_group_by_error_invalid_or_key(self):
        """Test error is thrown when or order_by parameter is used."""
        query_params = {
            "group_by": {"account": ["account1"], "project": ["project1"]},
            "order_by": {"or:usage": "asc"},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_scope": [],
            },
        }
        serializer = QueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_multiple_group_by_error_invalid_key(self):
        """Test error when invalid order_by parameter is passed."""
        query_params = {
            "group_by": {"or:account": "*", "or:project": "*"},
            "order_by": {"region": "asc"},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_scope": [],
            },
        }
        serializer = QueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_multiple_group_by_error_valid_key_allowlist(self):
        """Test for valid key for special case account alias."""
        query_params = {
            "group_by": {"account": ["account1"], "project": ["project1"]},
            "order_by": {"account_alias": "asc"},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_scope": [],
            },
        }
        serializer = QueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_multiple_group_by_valid_with_or(self):
        """Test for valid key on special case account alias with or group_by parameters."""
        query_params = {
            "group_by": {"or:account": ["account1"], "or:project": ["project1"]},
            "order_by": {"account_alias": "asc"},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_scope": [],
            },
        }
        serializer = QueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_parse_filter_dates_valid(self):
        """Test parse of a filter date-based param should succeed."""
        dh = DateHelper()
        scenarios = [
            {"start_date": dh.yesterday.date(), "end_date": dh.today.date()},
            {
                "start_date": dh.last_month_end.date(),
                "end_date": dh.this_month_start.date(),
                "filter": {"resolution": "daily"},
            },
            {
                "start_date": materialized_view_month_start().date(),
                "end_date": dh.today.date(),
                "filter": {"resolution": "daily"},
            },
            {
                "start_date": dh.last_month_end.date(),
                "end_date": dh.this_month_start.date(),
                "filter": {"resolution": "monthly"},
            },
            {
                "start_date": materialized_view_month_start().date(),
                "end_date": dh.today.date(),
                "filter": {"resolution": "monthly"},
            },
        ]

        for params in scenarios:
            with self.subTest(params=params):
                serializer = QueryParamSerializer(data=params, context=self.alt_request_context)
                self.assertTrue(serializer.is_valid(raise_exception=True))

    def test_parse_filter_dates_invalid_delta_pairing(self):
        """Test parse of a filter date-based param with delta should not succeed."""
        dh = DateHelper()
        scenarios = [
            {"end_date": dh.this_month_start.date(), "delta": "cost"},
            {"start_date": materialized_view_month_start().date(), "delta": "cost"},
            {"start_date": materialized_view_month_start().date(), "end_date": dh.today.date(), "delta": "cost"},
        ]

        for params in scenarios:
            with self.subTest(params=params):
                with self.assertRaises(ValidationError):
                    serializer = QueryParamSerializer(data=params)
                    serializer.is_valid(raise_exception=True)

    def test_parse_filter_dates_invalid(self):
        """Test parse of invalid data for filter date-based param should not succeed."""
        dh = DateHelper()
        scenarios = [
            {"start_date": dh.today.date()},
            {"end_date": dh.today.date()},
            {"start_date": dh.yesterday.date(), "end_date": dh.tomorrow.date()},
            {"start_date": dh.n_days_ago(materialized_view_month_start(), 1), "end_date": dh.today.date()},
            {"start_date": dh.today.date(), "end_date": dh.yesterday.date()},
            {"start_date": "llamas", "end_date": dh.yesterday.date()},
            {"start_date": dh.yesterday.date(), "end_date": "alpacas"},
            {"start_date": "llamas", "end_date": "alpacas"},
            {
                "start_date": materialized_view_month_start().date(),
                "end_date": dh.last_month_end.date(),
                "filter": {"time_scope_units": "day"},
            },
            {
                "start_date": materialized_view_month_start().date(),
                "end_date": dh.last_month_end.date(),
                "filter": {"time_scope_value": "-1"},
            },
            {
                "start_date": materialized_view_month_start().date(),
                "end_date": dh.last_month_end.date(),
                "filter": {"time_scope_units": "day", "time_scope_value": "-1"},
            },
            {
                "start_date": materialized_view_month_start().date() - relativedelta(months=1),
                "end_date": dh.last_month_end.date(),
                "filter": {"time_scope_units": "day", "time_scope_value": "-1"},
            },
        ]

        for params in scenarios:
            with self.subTest(params=params):
                serializer = QueryParamSerializer(data=params)
                self.assertFalse(serializer.is_valid())


class ParamSerializerTest(TestCase):
    """Tests for the handling query parameter parsing serializer."""

    def test_parse_filter_dates_invalid_delta(self):
        """Test parse of a filter date-based param with monthly presolution should not succeed."""
        dh = DateHelper()
        params = {"start_date": dh.last_month_end.date(), "end_date": dh.this_month_start.date(), "delta": "cost"}
        with self.assertRaises(ValidationError):
            serializer = ParamSerializer(data=params)
            self.assertFalse(serializer.is_valid())
            serializer.is_valid(raise_exception=True)
