#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Azure Provider serializers."""
from unittest import TestCase
from unittest.mock import Mock

from faker import Faker
from rest_framework import serializers

from api.report.azure.openshift.serializers import OCPAzureFilterSerializer
from api.report.azure.openshift.serializers import OCPAzureGroupBySerializer
from api.report.azure.openshift.serializers import OCPAzureOrderBySerializer
from api.report.azure.openshift.serializers import OCPAzureQueryParamSerializer

FAKE = Faker()


class OCPAzureFilterSerializerTest(TestCase):
    """Tests for the filter serializer."""

    def test_parse_filter_params_success(self):
        """Test parse of a filter param successfully."""
        filter_params = {
            "resolution": "daily",
            "time_scope_value": "-10",
            "time_scope_units": "day",
            "resource_location": FAKE.word(),
            "subscription_guid": FAKE.uuid4(),
            "instance_type": FAKE.word(),
            "service_name": FAKE.word(),
        }
        serializer = OCPAzureFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_filter_params_no_time(self):
        """Test parse of a filter param no time filter."""
        filter_params = {
            "resource_location": FAKE.word(),
            "subscription_guid": FAKE.uuid4(),
            "instance_type": FAKE.word(),
        }
        serializer = OCPAzureFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_filter_params_invalid_fields(self):
        """Test parse of filter params for invalid fields."""
        filter_params = {"invalid": "param"}
        serializer = OCPAzureFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_time_scope_daily(self):
        """Test parse of filter params for invalid daily time_scope_units."""
        filter_params = {"resolution": "daily", "time_scope_value": "-1", "time_scope_units": "day"}
        serializer = OCPAzureFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_time_scope_monthly(self):
        """Test parse of filter params for invalid month time_scope_units."""
        filter_params = {"resolution": "monthly", "time_scope_value": "-10", "time_scope_units": "month"}
        serializer = OCPAzureFilterSerializer(data=filter_params)
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
        serializer = OCPAzureFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_limit_time_scope_resolution(self):
        """Test parse of filter params for invalid resolution time_scope_units."""
        filter_params = {"resolution": "monthly", "time_scope_value": "-10", "time_scope_units": "day"}
        serializer = OCPAzureFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ["valid_tag"]
        query_params = {"valid_tag": "value"}
        serializer = OCPAzureFilterSerializer(data=query_params, tag_keys=tag_keys)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"bad_tag": "value"}
        serializer = OCPAzureFilterSerializer(data=query_params, tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_parse_filter_project(self):
        """Test filter by project."""
        filter_params = {"project": ["*"]}
        serializer = OCPAzureFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_filter_cluster(self):
        """Test filter by cluster."""
        filter_params = {"cluster": ["*"]}
        serializer = OCPAzureFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_filter_node(self):
        """Test filter by node."""
        filter_params = {"node": ["*"]}
        serializer = OCPAzureFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_all_filter_op_fields(self):
        """Test that the allowed fields pass."""
        for field in OCPAzureFilterSerializer._opfields:
            field = "and:" + field
            filter_param = {field: ["1", "2"]}
            serializer = OCPAzureFilterSerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())
        for field in OCPAzureFilterSerializer._opfields:
            field = "or:" + field
            filter_param = {field: ["1", "2"]}
            serializer = OCPAzureFilterSerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())


class OCPAzureGroupBySerializerTest(TestCase):
    """Tests for the group_by serializer."""

    def test_parse_group_by_params_success(self):
        """Test parse of a group_by param successfully."""
        group_params = {"subscription_guid": [FAKE.uuid4()]}
        serializer = OCPAzureGroupBySerializer(data=group_params)
        self.assertTrue(serializer.is_valid())

    def test_group_by_params_invalid_fields(self):
        """Test parse of group_by params for invalid fields."""
        group_params = {"resource_location": [FAKE.word()], "invalid": "param"}
        serializer = OCPAzureGroupBySerializer(data=group_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_group_by_params_string_list_fields(self):
        """Test group_by params for handling string to list fields."""
        group_params = {"instance_type": FAKE.word()}
        serializer = OCPAzureGroupBySerializer(data=group_params)
        validation = serializer.is_valid()
        self.assertTrue(validation)
        result = serializer.data.get("instance_type")
        self.assertIsInstance(result, list)

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ["valid_tag"]
        query_params = {"valid_tag": "*"}
        serializer = OCPAzureGroupBySerializer(data=query_params, tag_keys=tag_keys)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"bad_tag": "*"}
        serializer = OCPAzureGroupBySerializer(data=query_params, tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_parse_group_by_project(self):
        """Test group by project."""
        group_params = {"project": ["*"]}
        serializer = OCPAzureGroupBySerializer(data=group_params)
        self.assertTrue(serializer.is_valid())

    def test_group_by_cluster(self):
        """Test group by cluster."""
        group_params = {"cluster": ["*"]}
        serializer = OCPAzureGroupBySerializer(data=group_params)
        self.assertTrue(serializer.is_valid())

    def test_group_by_node(self):
        """Test group by node."""
        group_params = {"node": ["*"]}
        serializer = OCPAzureGroupBySerializer(data=group_params)
        self.assertTrue(serializer.is_valid())

    def test_all_group_by_op_fields(self):
        """Test that the allowed fields pass."""
        for field in OCPAzureGroupBySerializer._opfields:
            field = "and:" + field
            filter_param = {field: ["1", "2"]}
            serializer = OCPAzureGroupBySerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())
        for field in OCPAzureGroupBySerializer._opfields:
            field = "or:" + field
            filter_param = {field: ["1", "2"]}
            serializer = OCPAzureGroupBySerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())


class OCPAzureOrderBySerializerTest(TestCase):
    """Tests for the order_by serializer."""

    def test_order_by_project(self):
        """Test order by project."""
        order_params = {"project": "asc"}
        serializer = OCPAzureOrderBySerializer(data=order_params)
        self.assertTrue(serializer.is_valid())

    def test_order_by_cluster(self):
        """Test order by cluster."""
        order_params = {"cluster": "asc"}
        serializer = OCPAzureOrderBySerializer(data=order_params)
        self.assertTrue(serializer.is_valid())

    def test_order_by_node(self):
        """Test order by node."""
        order_params = {"node": "asc"}
        serializer = OCPAzureOrderBySerializer(data=order_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_order_by_params_success(self):
        """Test parse of a order_by param successfully."""
        order_params = {"instance_type": "asc"}
        serializer = OCPAzureOrderBySerializer(data=order_params)
        self.assertTrue(serializer.is_valid())

    def test_order_by_params_invalid_fields(self):
        """Test parse of order_by params for invalid fields."""
        order_params = {"subscription_guid": "asc", "invalid": "param"}
        serializer = OCPAzureOrderBySerializer(data=order_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class OCPAzureQueryParamSerializerTest(TestCase):
    """Tests for the handling query parameter parsing serializer."""

    def test_parse_query_azure_params_success(self):
        """Test parse of a query params successfully."""
        query_params = {
            "group_by": {"instance_type": [FAKE.word()]},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "subscription_guid": [FAKE.uuid4()],
            },
        }
        serializer = OCPAzureQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_query_ocp_params_success(self):
        """Test parse of a query params successfully."""
        query_params = {
            "group_by": {"project": ["account1"]},
            "order_by": {"project": "asc"},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_scope": [],
            },
            "units": "byte",
        }
        serializer = OCPAzureQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_query_params_invalid_fields(self):
        """Test parse of query params for invalid fields."""
        query_params = {
            "group_by": {"instance_type": [FAKE.word()]},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_location": [FAKE.word()],
            },
            "invalid": "param",
        }
        serializer = OCPAzureQueryParamSerializer(data=query_params)
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
                "subscription_guid": [FAKE.uuid4()],
            },
        }
        serializer = OCPAzureQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_parse_units(self):
        """Test pass while parsing units query params."""
        query_params = {"units": "bytes"}
        serializer = OCPAzureQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_units_failure(self):
        """Test failure while parsing units query params."""
        query_params = {"units": "bites"}
        serializer = OCPAzureQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ["valid_tag"]
        query_params = {"filter": {"valid_tag": "value"}}
        serializer = OCPAzureQueryParamSerializer(data=query_params, tag_keys=tag_keys)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"filter": {"bad_tag": "value"}}
        serializer = OCPAzureQueryParamSerializer(data=query_params, tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_valid_delta_costs(self):
        """Test successful handling of valid delta for cost requests."""
        query_params = {"delta": "cost"}
        req = Mock(path="/api/cost-management/v1/reports/azure/costs/")
        serializer = OCPAzureQueryParamSerializer(data=query_params, context={"request": req})
        self.assertTrue(serializer.is_valid())

    def test_valid_delta_usage(self):
        """Test successful handling of valid delta for usage requests."""
        query_params = {"delta": "usage"}
        req = Mock(path="/api/cost-management/v1/reports/azure/storage/")
        serializer = OCPAzureQueryParamSerializer(data=query_params, context={"request": req})
        self.assertTrue(serializer.is_valid())

    def test_invalid_delta_costs(self):
        """Test failure while handling invalid delta for cost requests."""
        query_params = {"delta": "cost_bad"}
        req = Mock(path="/api/cost-management/v1/reports/azure/storage/")
        serializer = OCPAzureQueryParamSerializer(data=query_params, context={"request": req})
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_invalid_delta_usage(self):
        """Test failure while handling invalid delta for usage requests."""
        query_params = {"delta": "usage"}
        req = Mock(path="/api/cost-management/v1/reports/azure/costs/")
        serializer = OCPAzureQueryParamSerializer(data=query_params, context={"request": req})
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_order_by_service_with_groupby(self):
        """Test that order_by[service_name] works with a matching group-by."""
        query_params = {"group_by": {"service_name": "asc"}, "order_by": {"service_name": "asc"}}
        serializer = OCPAzureQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_order_by_service_without_groupby(self):
        """Test that order_by[service_name] fails without a matching group-by."""
        query_params = {"order_by": {"service_name": "asc"}}
        serializer = OCPAzureQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_query_params_invalid_order_by_request(self):
        """Test parse of charge query params for invalid fields."""
        # Charge can't order by request or usage
        query_params = {
            "group_by": {"subscription_guid": [FAKE.uuid4()]},
            "order_by": {"request": "asc"},
            "filter": {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day"},
            "invalid": "param",
        }
        serializer = OCPAzureQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_query_params_invalid_order_by_usage(self):
        """Test parse of charge query params for invalid fields."""
        # Charge can't order by request or usage
        query_params = {
            "group_by": {"subscription_guid": [FAKE.uuid4()]},
            "order_by": {"usage": "asc"},
            "filter": {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day"},
            "invalid": "param",
        }
        serializer = OCPAzureQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)
