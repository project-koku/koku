#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Azure Provider serializers."""
from unittest import TestCase

from faker import Faker
from rest_framework import serializers

from api.iam.test.iam_test_case import IamTestCase
from api.report.azure.serializers import AzureExcludeSerializer
from api.report.azure.serializers import AzureFilterSerializer
from api.report.azure.serializers import AzureGroupBySerializer
from api.report.azure.serializers import AzureOrderBySerializer
from api.report.azure.serializers import AzureQueryParamSerializer

FAKE = Faker()


class AzureExcludeSerializerTest(TestCase):
    """Tests for the exclude serializer."""

    def test_parse_exclude_params_no_time(self):
        """Test parse of a exclude param no time exclude."""
        exclude_params = {
            "resource_location": FAKE.word(),
            "subscription_guid": FAKE.uuid4(),
            "instance_type": FAKE.word(),
        }
        serializer = AzureExcludeSerializer(data=exclude_params)
        self.assertTrue(serializer.is_valid())

    def test_exclude_params_invalid_fields(self):
        """Test parse of exclude params for invalid fields."""
        exclude_params = {"invalid": "param"}
        serializer = AzureExcludeSerializer(data=exclude_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ["valid_tag"]
        query_params = {"valid_tag": "value"}
        serializer = AzureExcludeSerializer(data=query_params, tag_keys=tag_keys)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"bad_tag": "value"}
        serializer = AzureExcludeSerializer(data=query_params, tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_all_exclude_op_fields(self):
        """Test that the allowed fields pass."""
        for field in AzureExcludeSerializer._opfields:
            field = "and:" + field
            exclude_param = {field: ["1", "2"]}
            serializer = AzureExcludeSerializer(data=exclude_param)
            self.assertTrue(serializer.is_valid())
        for field in AzureExcludeSerializer._opfields:
            field = "or:" + field
            exclude_param = {field: ["1", "2"]}
            serializer = AzureExcludeSerializer(data=exclude_param)
            self.assertTrue(serializer.is_valid())


class AzureFilterSerializerTest(TestCase):
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
        serializer = AzureFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_filter_params_no_time(self):
        """Test parse of a filter param no time filter."""
        filter_params = {
            "resource_location": FAKE.word(),
            "subscription_guid": FAKE.uuid4(),
            "instance_type": FAKE.word(),
        }
        serializer = AzureFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_filter_params_invalid_fields(self):
        """Test parse of filter params for invalid fields."""
        filter_params = {"invalid": "param"}
        serializer = AzureFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_time_scope_daily(self):
        """Test parse of filter params for invalid daily time_scope_units."""
        filter_params = {"resolution": "daily", "time_scope_value": "-1", "time_scope_units": "day"}
        serializer = AzureFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_time_scope_monthly(self):
        """Test parse of filter params for invalid month time_scope_units."""
        filter_params = {"resolution": "monthly", "time_scope_value": "-10", "time_scope_units": "month"}
        serializer = AzureFilterSerializer(data=filter_params)
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
        serializer = AzureFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_limit_time_scope_resolution(self):
        """Test parse of filter params for invalid resolution time_scope_units."""
        filter_params = {"resolution": "monthly", "time_scope_value": "-10", "time_scope_units": "day"}
        serializer = AzureFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ["valid_tag"]
        query_params = {"valid_tag": "value"}
        serializer = AzureFilterSerializer(data=query_params, tag_keys=tag_keys)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"bad_tag": "value"}
        serializer = AzureFilterSerializer(data=query_params, tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_all_filter_op_fields(self):
        """Test that the allowed fields pass."""
        for field in AzureFilterSerializer._opfields:
            field = "and:" + field
            filter_param = {field: ["1", "2"]}
            serializer = AzureFilterSerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())
        for field in AzureFilterSerializer._opfields:
            field = "or:" + field
            filter_param = {field: ["1", "2"]}
            serializer = AzureFilterSerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())


class AzureGroupBySerializerTest(TestCase):
    """Tests for the group_by serializer."""

    def test_parse_group_by_params_success(self):
        """Test parse of a group_by param successfully."""
        group_params = {"subscription_guid": [FAKE.uuid4()]}
        serializer = AzureGroupBySerializer(data=group_params)
        self.assertTrue(serializer.is_valid())

    def test_group_by_params_invalid_fields(self):
        """Test parse of group_by params for invalid fields."""
        group_params = {"resource_location": [FAKE.word()], "invalid": "param"}
        serializer = AzureGroupBySerializer(data=group_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_group_by_params_string_list_fields(self):
        """Test group_by params for handling string to list fields."""
        group_params = {"instance_type": FAKE.word()}
        serializer = AzureGroupBySerializer(data=group_params)
        validation = serializer.is_valid()
        self.assertTrue(validation)
        result = serializer.data.get("instance_type")
        self.assertIsInstance(result, list)

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ["valid_tag"]
        query_params = {"valid_tag": "*"}
        serializer = AzureGroupBySerializer(data=query_params, tag_keys=tag_keys)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"bad_tag": "*"}
        serializer = AzureGroupBySerializer(data=query_params, tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_all_group_by_op_fields(self):
        """Test that the allowed fields pass."""
        for field in AzureGroupBySerializer._opfields:
            field = "and:" + field
            filter_param = {field: ["1", "2"]}
            serializer = AzureGroupBySerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())
        for field in AzureGroupBySerializer._opfields:
            field = "or:" + field
            filter_param = {field: ["1", "2"]}
            serializer = AzureGroupBySerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())


class AzureOrderBySerializerTest(TestCase):
    """Tests for the order_by serializer."""

    def test_parse_order_by_params_success(self):
        """Test parse of a order_by param successfully."""
        order_params = {"instance_type": "asc"}
        serializer = AzureOrderBySerializer(data=order_params)
        self.assertTrue(serializer.is_valid())

    def test_order_by_params_invalid_fields(self):
        """Test parse of order_by params for invalid fields."""
        order_params = {"subscription_guid": "asc", "invalid": "param"}
        serializer = AzureOrderBySerializer(data=order_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class AzureQueryParamSerializerTest(IamTestCase):
    """Tests for the handling query parameter parsing serializer."""

    def test_parse_query_params_success(self):
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

        path = "/api/cost-management/v1/reports/azure/costs/"
        ctx = self._create_request_context(
            self.customer_data, self._create_user_data(), create_customer=False, create_user=True, path=path
        )
        serializer = AzureQueryParamSerializer(data=query_params, context=ctx)
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

        path = "/api/cost-management/v1/reports/azure/costs/"
        ctx = self._create_request_context(
            self.customer_data, self._create_user_data(), create_customer=False, create_user=True, path=path
        )
        serializer = AzureQueryParamSerializer(data=query_params, context=ctx)
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

        path = "/api/cost-management/v1/reports/azure/costs/"
        ctx = self._create_request_context(
            self.customer_data, self._create_user_data(), create_customer=False, create_user=True, path=path
        )
        serializer = AzureQueryParamSerializer(data=query_params, context=ctx)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ["valid_tag"]
        query_params = {"filter": {"valid_tag": "value"}}

        path = "/api/cost-management/v1/reports/azure/costs/"
        ctx = self._create_request_context(
            self.customer_data, self._create_user_data(), create_customer=False, create_user=True, path=path
        )
        serializer = AzureQueryParamSerializer(data=query_params, tag_keys=tag_keys, context=ctx)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"filter": {"bad_tag": "value"}}

        path = "/api/cost-management/v1/reports/azure/costs/"
        ctx = self._create_request_context(
            self.customer_data, self._create_user_data(), create_customer=False, create_user=True, path=path
        )
        serializer = AzureQueryParamSerializer(data=query_params, tag_keys=tag_keys, context=ctx)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_valid_delta_costs(self):
        """Test successful handling of valid delta for cost requests."""
        query_params = {"delta": "cost"}
        path = "/api/cost-management/v1/reports/azure/costs/"
        ctx = self._create_request_context(
            self.customer_data, self._create_user_data(), create_customer=False, create_user=True, path=path
        )
        serializer = AzureQueryParamSerializer(data=query_params, context=ctx)
        self.assertTrue(serializer.is_valid())

    def test_valid_delta_usage(self):
        """Test successful handling of valid delta for usage requests."""
        query_params = {"delta": "usage"}
        path = "/api/cost-management/v1/reports/azure/storage/"
        ctx = self._create_request_context(
            self.customer_data, self._create_user_data(), create_customer=False, create_user=True, path=path
        )
        serializer = AzureQueryParamSerializer(data=query_params, context=ctx)
        self.assertTrue(serializer.is_valid())

    def test_invalid_delta_costs(self):
        """Test failure while handling invalid delta for cost requests."""
        query_params = {"delta": "cost_bad"}
        path = "/api/cost-management/v1/reports/azure/storage/"
        ctx = self._create_request_context(
            self.customer_data, self._create_user_data(), create_customer=False, create_user=True, path=path
        )
        serializer = AzureQueryParamSerializer(data=query_params, context=ctx)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_invalid_delta_usage(self):
        """Test failure while handling invalid delta for usage requests."""
        query_params = {"delta": "usage"}
        path = "/api/cost-management/v1/reports/azure/costs/"
        ctx = self._create_request_context(
            self.customer_data, self._create_user_data(), create_customer=False, create_user=True, path=path
        )
        serializer = AzureQueryParamSerializer(data=query_params, context=ctx)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_order_by_service_with_groupby(self):
        """Test that order_by[service_name] works with a matching group-by."""
        query_params = {"group_by": {"service_name": "asc"}, "order_by": {"service_name": "asc"}}

        path = "/api/cost-management/v1/reports/azure/costs/"
        ctx = self._create_request_context(
            self.customer_data, self._create_user_data(), create_customer=False, create_user=True, path=path
        )
        serializer = AzureQueryParamSerializer(data=query_params, context=ctx)
        self.assertTrue(serializer.is_valid())

    def test_order_by_service_without_groupby(self):
        """Test that order_by[service_name] fails without a matching group-by."""
        query_params = {"order_by": {"service_name": "asc"}}

        path = "/api/cost-management/v1/reports/azure/costs/"
        ctx = self._create_request_context(
            self.customer_data, self._create_user_data(), create_customer=False, create_user=True, path=path
        )
        serializer = AzureQueryParamSerializer(data=query_params, context=ctx)
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

        path = "/api/cost-management/v1/reports/azure/costs/"
        ctx = self._create_request_context(
            self.customer_data, self._create_user_data(), create_customer=False, create_user=True, path=path
        )
        serializer = AzureQueryParamSerializer(data=query_params, context=ctx)
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

        path = "/api/cost-management/v1/reports/azure/costs/"
        ctx = self._create_request_context(
            self.customer_data, self._create_user_data(), create_customer=False, create_user=True, path=path
        )
        serializer = AzureQueryParamSerializer(data=query_params, context=ctx)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_fail_without_group_by(self):
        """Test fail if filter[limit] and filter[offset] passed without group by."""
        param_failures_list = [
            {"filter": {"limit": "1", "offset": "1"}},
            {"filter": {"limit": "1"}},
            {"filter": {"offset": "1"}},
        ]
        path = "/api/cost-management/v1/reports/azure/costs/"
        ctx = self._create_request_context(
            self.customer_data, self._create_user_data(), create_customer=False, create_user=True, path=path
        )
        for param in param_failures_list:
            with self.subTest(param=param):
                with self.assertRaises(serializers.ValidationError):
                    serializer = AzureQueryParamSerializer(data=param, context=ctx)
                    self.assertFalse(serializer.is_valid())
                    serializer.is_valid(raise_exception=True)

    def test_pass_without_group_by(self):
        """Test pass if filter[limit] and filter[offset] passed without group by on instance type."""
        param_list = [
            {"filter": {"limit": "1", "offset": "1"}},
            {"filter": {"limit": "1"}},
            {"filter": {"offset": "1"}},
        ]
        path = "/api/cost-management/v1/reports/azure/instance-types/"
        ctx = self._create_request_context(
            self.customer_data, self._create_user_data(), create_customer=False, create_user=True, path=path
        )
        for param in param_list:
            with self.subTest(param=param):
                serializer = AzureQueryParamSerializer(data=param, context=ctx)
                self.assertTrue(serializer.is_valid())
