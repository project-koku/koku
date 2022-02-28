#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Report serializers."""
from unittest import TestCase

from rest_framework import serializers

from api.report.ocp.serializers import FilterSerializer
from api.report.ocp.serializers import GroupBySerializer
from api.report.ocp.serializers import OCPCostQueryParamSerializer
from api.report.ocp.serializers import OCPInventoryQueryParamSerializer
from api.report.ocp.serializers import OCPQueryParamSerializer
from api.report.ocp.serializers import OrderBySerializer


class OCPFilterSerializerTest(TestCase):
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

    def test_filter_params_invalid_limit_time_scope_resolution(self):
        """Test parse of filter params for invalid resolution time_scope_units."""
        filter_params = {"resolution": "monthly", "time_scope_value": "-10", "time_scope_units": "day"}
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

    def test_infrastructure_field_validation_success(self):
        """Test that infrastructure filter are validated for aws."""
        query_params = {"infrastructures": "aws"}
        serializer = FilterSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_infrastructure_field_validation_failure(self):
        """Test that infrastructure filter are validated for non-aws."""
        query_params = {"infrastructures": "notaws"}
        serializer = FilterSerializer(data=query_params)
        self.assertFalse(serializer.is_valid())

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


class OCPGroupBySerializerTest(TestCase):
    """Tests for the group_by serializer."""

    def test_parse_group_by_params_success(self):
        """Test parse of a group_by param successfully."""
        group_params = {"cluster": ["cluster1"]}
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
        group_params = {"node": "localhost"}
        serializer = GroupBySerializer(data=group_params)
        validation = serializer.is_valid()
        self.assertTrue(validation)
        node_result = serializer.data.get("node")
        self.assertIsInstance(node_result, list)

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


class OCPOrderBySerializerTest(TestCase):
    """Tests for the order_by serializer."""

    def test_parse_order_by_params_success(self):
        """Test parse of a order_by param successfully."""
        order_params = {"project": "asc"}
        serializer = OrderBySerializer(data=order_params)
        self.assertTrue(serializer.is_valid())

    def test_order_by_params_invalid_fields(self):
        """Test parse of order_by params for invalid fields."""
        order_params = {"cost": "asc", "invalid": "param"}
        serializer = OrderBySerializer(data=order_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class OCPQueryParamSerializerTest(TestCase):
    """Tests for the handling query parameter parsing serializer."""

    def test_parse_query_params_success(self):
        """Test parse of a query params successfully."""
        query_params = {
            "group_by": {"project": ["project1"]},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_scope": [],
            },
        }
        serializer = OCPQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_query_params_invalid_fields(self):
        """Test parse of query params for invalid fields."""
        query_params = {
            "group_by": {"account": ["account1"]},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_scope": [],
            },
            "invalid": "param",
        }
        serializer = OCPQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_query_params_invalid_nested_fields(self):
        """Test parse of query params for invalid nested_fields."""
        query_params = {
            "group_by": {"invalid": ["invalid"]},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_scope": [],
            },
        }
        serializer = OCPQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_parse_units(self):
        """Test pass while parsing units query params."""
        query_params = {"units": "bytes"}
        serializer = OCPQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_units_failure(self):
        """Test failure while parsing units query params."""
        query_params = {"units": "bites"}
        serializer = OCPQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ["valid_tag"]
        query_params = {"filter": {"valid_tag": "value"}}
        serializer = OCPQueryParamSerializer(data=query_params, tag_keys=tag_keys)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"filter": {"bad_tag": "value"}}
        serializer = OCPQueryParamSerializer(data=query_params, tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class OCPInventoryQueryParamSerializerTest(TestCase):
    """Tests for the handling inventory query parameter parsing serializer."""

    def test_parse_query_params_success(self):
        """Test parse of an inventory query params successfully."""
        query_params = {
            "group_by": {"project": ["project1"]},
            "order_by": {"usage": "asc"},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_scope": [],
            },
        }
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_query_params_invalid_order_by(self):
        """Test parse of inventory query params for invalid fields."""
        # Pass requests instead of request
        query_params = {
            "group_by": {"account": ["account1"]},
            "order_by": {"requests": "asc"},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_scope": [],
            },
            "invalid": "param",
        }
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_delta_success(self):
        """Test that a proper delta value is serialized."""
        query_params = {"delta": "cost"}
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

        query_params = {"delta": "usage"}
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

        query_params = {"delta": "request"}
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_delta_failure(self):
        """Test that a bad delta value is not serialized."""
        query_params = {"delta": "bad_delta"}
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_current_month_delta_success(self):
        """Test that a proper current month delta value is serialized."""
        query_params = {"delta": "usage__request"}
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

        query_params = {"delta": "usage__capacity"}
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

        query_params = {"delta": "request__capacity"}
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_current_month_delta_failure(self):
        """Test that a bad current month delta value is not serialized."""
        query_params = {"delta": "bad__delta"}
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

        query_params = {"delta": "usage__request__capacity"}
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_order_by_delta_with_delta(self):
        """Test that order_by[delta] works with a delta param."""
        query_params = {"delta": "usage__request", "order_by": {"delta": "asc"}}
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_order_by_delta_without_delta(self):
        """Test that order_by[delta] does not work without a delta param."""
        query_params = {"order_by": {"delta": "asc"}}
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_order_by_node_with_groupby(self):
        """Test that order_by[node] works with a matching group-by."""
        query_params = {"group_by": {"node": "asc"}, "order_by": {"node": "asc"}}
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_order_by_node_without_groupby(self):
        """Test that order_by[node] fails without a matching group-by."""
        query_params = {"order_by": {"node": "asc"}}
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class OCPCostQueryParamSerializerTest(TestCase):
    """Tests for the handling charge query parameter parsing serializer."""

    def test_parse_query_params_success(self):
        """Test parse of a charge query params successfully."""
        query_params = {
            "group_by": {"project": ["project1"]},
            "order_by": {"cost": "asc"},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_scope": [],
            },
        }
        serializer = OCPCostQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_query_params_invalid_order_by_request(self):
        """Test parse of charge query params for invalid fields."""
        # Charge can't order by request or usage
        query_params = {
            "group_by": {"account": ["account1"]},
            "order_by": {"request": "asc"},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_scope": [],
            },
            "invalid": "param",
        }
        serializer = OCPCostQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_query_params_invalid_order_by_usage(self):
        """Test parse of charge query params for invalid fields."""
        # Charge can't order by request or usage
        query_params = {
            "group_by": {"account": ["account1"]},
            "order_by": {"usage": "asc"},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_scope": [],
            },
            "invalid": "param",
        }
        serializer = OCPCostQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_query_params_valid_delta(self):
        """Test parse of delta charge query params for valid fields."""
        # Charge can't order by request or usage
        query_params = {
            "group_by": {"account": ["account1"]},
            "order_by": {"usage": "asc"},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_scope": [],
            },
            "delta": "cost",
        }
        serializer = OCPCostQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)
