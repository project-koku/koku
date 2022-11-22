#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCI Provider serializers."""
from unittest import TestCase

from faker import Faker
from rest_framework import serializers

from api.iam.test.iam_test_case import IamTestCase
from api.report.oci.serializers import OCIExcludeSerializer
from api.report.oci.serializers import OCIFilterSerializer
from api.report.oci.serializers import OCIGroupBySerializer
from api.report.oci.serializers import OCIOrderBySerializer
from api.report.oci.serializers import OCIQueryParamSerializer

FAKE = Faker()


class OCIExcludeSerializerTest(TestCase):
    """Tests for the exclude serializer."""

    def test_parse_exclude_params_no_time(self):
        """Test parse of a exclude param no time exclude."""
        exclude_params = {
            "region": FAKE.word(),
            "payer_tenant_id": FAKE.uuid4(),
            "instance_type": FAKE.word(),
        }
        serializer = OCIExcludeSerializer(data=exclude_params)
        self.assertTrue(serializer.is_valid())

    def test_exclude_params_invalid_fields(self):
        """Test parse of exclude params for invalid fields."""
        exclude_params = {"invalid": "param"}
        serializer = OCIExcludeSerializer(data=exclude_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"bad_tag": "value"}
        serializer = OCIExcludeSerializer(data=query_params, tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_all_exclude_op_fields(self):
        """Test that the allowed fields pass."""
        for field in OCIExcludeSerializer._opfields:
            field = "and:" + field
            exclude_param = {field: ["1", "2"]}
            serializer = OCIExcludeSerializer(data=exclude_param)
            self.assertTrue(serializer.is_valid())
        for field in OCIExcludeSerializer._opfields:
            field = "or:" + field
            exclude_param = {field: ["1", "2"]}
            serializer = OCIExcludeSerializer(data=exclude_param)
            self.assertTrue(serializer.is_valid())


class OCIFilterSerializerTest(TestCase):
    """Tests for the filter serializer."""

    def test_parse_filter_params_success(self):
        """Test parse of a filter param successfully."""
        filter_params = {
            "resolution": "daily",
            "time_scope_value": "-10",
            "time_scope_units": "day",
            "region": FAKE.word(),
            "payer_tenant_id": FAKE.uuid4(),
            "product_service": FAKE.word(),
        }
        serializer = OCIFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_filter_params_no_time(self):
        """Test parse of a filter param no time filter."""
        filter_params = {
            "region": FAKE.word(),
            "payer_tenant_id": FAKE.uuid4(),
            "instance_type": FAKE.word(),
        }
        serializer = OCIFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_filter_params_invalid_fields(self):
        """Test parse of filter params for invalid fields."""
        filter_params = {"invalid": "param"}
        serializer = OCIFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_time_scope_daily(self):
        """Test parse of filter params for invalid daily time_scope_units."""
        filter_params = {"resolution": "daily", "time_scope_value": "-1", "time_scope_units": "day"}
        serializer = OCIFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_time_scope_monthly(self):
        """Test parse of filter params for invalid month time_scope_units."""
        filter_params = {"resolution": "monthly", "time_scope_value": "-10", "time_scope_units": "month"}
        serializer = OCIFilterSerializer(data=filter_params)
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
        serializer = OCIFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_limit_time_scope_resolution(self):
        """Test parse of filter params for invalid resolution time_scope_units."""
        filter_params = {"resolution": "monthly", "time_scope_value": "-10", "time_scope_units": "day"}
        serializer = OCIFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"bad_tag": "value"}
        serializer = OCIFilterSerializer(data=query_params, tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_all_filter_op_fields(self):
        """Test that the allowed fields pass."""
        for field in OCIFilterSerializer._opfields:
            field = "and:" + field
            filter_param = {field: ["1", "2"]}
            serializer = OCIFilterSerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())
        for field in OCIFilterSerializer._opfields:
            field = "or:" + field
            filter_param = {field: ["1", "2"]}
            serializer = OCIFilterSerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())


class OCIGroupBySerializerTest(TestCase):
    """Tests for the group_by serializer."""

    def test_parse_group_by_params_success(self):
        """Test parse of a group_by param successfully."""
        group_params = {"payer_tenant_id": [FAKE.uuid4()]}
        serializer = OCIGroupBySerializer(data=group_params)
        self.assertTrue(serializer.is_valid())

    def test_group_by_params_invalid_fields(self):
        """Test parse of group_by params for invalid fields."""
        group_params = {"region": [FAKE.word()], "invalid": "param"}
        serializer = OCIGroupBySerializer(data=group_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_group_by_params_string_list_fields(self):
        """Test group_by params for handling string to list fields."""
        group_params = {"instance_type": FAKE.word()}
        serializer = OCIGroupBySerializer(data=group_params)
        validation = serializer.is_valid()
        self.assertTrue(validation)
        result = serializer.data.get("instance_type")
        self.assertIsInstance(result, list)

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ["valid_tag"]
        query_params = {"valid_tag": "*"}
        serializer = OCIGroupBySerializer(data=query_params, tag_keys=tag_keys)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"bad_tag": "*"}
        serializer = OCIGroupBySerializer(data=query_params, tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_all_group_by_op_fields(self):
        """Test that the allowed fields pass."""
        for field in OCIGroupBySerializer._opfields:
            field = "and:" + field
            filter_param = {field: ["1", "2"]}
            serializer = OCIGroupBySerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())
        for field in OCIGroupBySerializer._opfields:
            field = "or:" + field
            filter_param = {field: ["1", "2"]}
            serializer = OCIGroupBySerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())


class OCIOrderBySerializerTest(TestCase):
    """Tests for the order_by serializer."""

    def test_order_by_params_invalid_fields(self):
        """Test parse of order_by params for invalid fields."""
        order_params = {"payer_tenant_id": "asc", "invalid": "param"}
        serializer = OCIOrderBySerializer(data=order_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class OCIQueryParamSerializerTest(IamTestCase):
    """Tests for the handling query parameter parsing serializer."""

    def test_query_params_invalid_fields(self):
        """Test parse of query params for invalid fields."""
        query_params = {
            "group_by": {"instance_type": [FAKE.word()]},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "region": [FAKE.word()],
            },
            "invalid": "param",
        }
        serializer = OCIQueryParamSerializer(data=query_params)
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
                "payer_tenant_id": [FAKE.uuid4()],
            },
        }
        serializer = OCIQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"filter": {"bad_tag": "value"}}
        serializer = OCIQueryParamSerializer(data=query_params, tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_invalid_delta_costs(self):
        """Test failure while handling invalid delta for cost requests."""
        query_params = {"delta": "cost_bad"}
        self.request_path = "/api/cost-management/v1/reports/oci/storage/"
        serializer = OCIQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_invalid_delta_usage(self):
        """Test failure while handling invalid delta for usage requests."""
        query_params = {"delta": "usage"}
        self.request_path = "/api/cost-management/v1/reports/oci/costs/"
        serializer = OCIQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_order_by_service_without_groupby(self):
        """Test that order_by[product_service] fails without a matching group-by."""
        query_params = {"order_by": {"product_service": "asc"}}
        serializer = OCIQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_query_params_invalid_order_by_request(self):
        """Test parse of charge query params for invalid fields."""
        # Charge can't order by request or usage
        query_params = {
            "group_by": {"payer_tenant_id": [FAKE.uuid4()]},
            "order_by": {"request": "asc"},
            "filter": {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day"},
            "invalid": "param",
        }
        serializer = OCIQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_query_params_invalid_order_by_usage(self):
        """Test parse of charge query params for invalid fields."""
        # Charge can't order by request or usage
        query_params = {
            "group_by": {"payer_tenant_id": [FAKE.uuid4()]},
            "order_by": {"usage": "asc"},
            "filter": {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day"},
            "invalid": "param",
        }
        serializer = OCIQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)
