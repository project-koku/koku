#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the GCP Provider serializers."""
from unittest import TestCase

from faker import Faker
from rest_framework import serializers

from api.iam.test.iam_test_case import IamTestCase
from api.report.gcp.openshift.serializers import OCPGCPExcludeSerializer
from api.report.gcp.openshift.serializers import OCPGCPFilterSerializer
from api.report.gcp.openshift.serializers import OCPGCPGroupBySerializer
from api.report.gcp.openshift.serializers import OCPGCPOrderBySerializer
from api.report.gcp.openshift.serializers import OCPGCPQueryParamSerializer

FAKE = Faker()


class OCPGCPExcludeSerializerTest(TestCase):
    """Tests for the exclude serializer."""

    def test_parse_exclude_params_no_time(self):
        """Test parse of a exclude param no time exclude."""
        exclude_params = {"account": FAKE.word(), "region": FAKE.uuid4(), "instance_type": FAKE.word()}
        serializer = OCPGCPExcludeSerializer(data=exclude_params)
        self.assertTrue(serializer.is_valid())

    def test_exclude_params_invalid_fields(self):
        """Test parse of exclude params for invalid fields."""
        exclude_params = {"invalid": "param"}
        serializer = OCPGCPExcludeSerializer(data=exclude_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ["valid_tag"]
        query_params = {"valid_tag": "value"}
        serializer = OCPGCPExcludeSerializer(data=query_params, tag_keys=tag_keys)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"bad_tag": "value"}
        serializer = OCPGCPExcludeSerializer(data=query_params, tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_parse_exclude_project(self):
        """Test exclude by project."""
        exclude_params = {"project": ["*"]}
        serializer = OCPGCPExcludeSerializer(data=exclude_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_exclude_cluster(self):
        """Test exclude by cluster."""
        exclude_params = {"cluster": ["*"]}
        serializer = OCPGCPExcludeSerializer(data=exclude_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_exclude_node(self):
        """Test exclude by node."""
        exclude_params = {"node": ["*"]}
        serializer = OCPGCPExcludeSerializer(data=exclude_params)
        self.assertTrue(serializer.is_valid())

    def test_all_exclude_op_fields(self):
        """Test that the allowed fields pass."""
        for field in OCPGCPExcludeSerializer._opfields:
            field = "and:" + field
            exclude_param = {field: ["1", "2"]}
            serializer = OCPGCPExcludeSerializer(data=exclude_param)
            self.assertTrue(serializer.is_valid())
        for field in OCPGCPExcludeSerializer._opfields:
            field = "or:" + field
            exclude_param = {field: ["1", "2"]}
            serializer = OCPGCPExcludeSerializer(data=exclude_param)
            self.assertTrue(serializer.is_valid())


class OCPGCPFilterSerializerTest(TestCase):
    """Tests for the filter serializer."""

    def test_parse_filter_params_success(self):
        """Test parse of a filter param successfully."""
        filter_params = {
            "resolution": "daily",
            "time_scope_value": "-10",
            "time_scope_units": "day",
            "account": FAKE.word(),
            "region": FAKE.uuid4(),
            "instance_type": FAKE.word(),
            "service": FAKE.word(),
        }
        serializer = OCPGCPFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_filter_params_no_time(self):
        """Test parse of a filter param no time filter."""
        filter_params = {"account": FAKE.word(), "region": FAKE.uuid4(), "instance_type": FAKE.word()}
        serializer = OCPGCPFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_filter_params_invalid_fields(self):
        """Test parse of filter params for invalid fields."""
        filter_params = {"invalid": "param"}
        serializer = OCPGCPFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_time_scope_daily(self):
        """Test parse of filter params for invalid daily time_scope_units."""
        filter_params = {"resolution": "daily", "time_scope_value": "-1", "time_scope_units": "day"}
        serializer = OCPGCPFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_time_scope_monthly(self):
        """Test parse of filter params for invalid month time_scope_units."""
        filter_params = {"resolution": "monthly", "time_scope_value": "-10", "time_scope_units": "month"}
        serializer = OCPGCPFilterSerializer(data=filter_params)
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
        serializer = OCPGCPFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_limit_time_scope_resolution(self):
        """Test parse of filter params for invalid resolution time_scope_units."""
        filter_params = {"resolution": "monthly", "time_scope_value": "-10", "time_scope_units": "day"}
        serializer = OCPGCPFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ["valid_tag"]
        query_params = {"valid_tag": "value"}
        serializer = OCPGCPFilterSerializer(data=query_params, tag_keys=tag_keys)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"bad_tag": "value"}
        serializer = OCPGCPFilterSerializer(data=query_params, tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_parse_filter_project(self):
        """Test filter by project."""
        filter_params = {"project": ["*"]}
        serializer = OCPGCPFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_filter_cluster(self):
        """Test filter by cluster."""
        filter_params = {"cluster": ["*"]}
        serializer = OCPGCPFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_filter_node(self):
        """Test filter by node."""
        filter_params = {"node": ["*"]}
        serializer = OCPGCPFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_all_filter_op_fields(self):
        """Test that the allowed fields pass."""
        for field in OCPGCPFilterSerializer._opfields:
            field = "and:" + field
            filter_param = {field: ["1", "2"]}
            serializer = OCPGCPFilterSerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())
        for field in OCPGCPFilterSerializer._opfields:
            field = "or:" + field
            filter_param = {field: ["1", "2"]}
            serializer = OCPGCPFilterSerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())


class OCPGCPGroupBySerializerTest(TestCase):
    """Tests for the group_by serializer."""

    def test_parse_group_by_params_success(self):
        """Test parse of a group_by param successfully."""
        group_params = {"region": [FAKE.uuid4()]}
        serializer = OCPGCPGroupBySerializer(data=group_params)
        self.assertTrue(serializer.is_valid())

    def test_group_by_params_invalid_fields(self):
        """Test parse of group_by params for invalid fields."""
        group_params = {"account": [FAKE.word()], "invalid": "param"}
        serializer = OCPGCPGroupBySerializer(data=group_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_group_by_params_string_list_fields(self):
        """Test group_by params for handling string to list fields."""
        group_params = {"instance_type": FAKE.word()}
        serializer = OCPGCPGroupBySerializer(data=group_params)
        validation = serializer.is_valid()
        self.assertTrue(validation)
        result = serializer.data.get("instance_type")
        self.assertIsInstance(result, list)

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ["valid_tag"]
        query_params = {"valid_tag": "*"}
        serializer = OCPGCPGroupBySerializer(data=query_params, tag_keys=tag_keys)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"bad_tag": "*"}
        serializer = OCPGCPGroupBySerializer(data=query_params, tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_parse_group_by_project(self):
        """Test group by project."""
        group_params = {"project": ["*"]}
        serializer = OCPGCPGroupBySerializer(data=group_params)
        self.assertTrue(serializer.is_valid())

    def test_group_by_cluster(self):
        """Test group by cluster."""
        group_params = {"cluster": ["*"]}
        serializer = OCPGCPGroupBySerializer(data=group_params)
        self.assertTrue(serializer.is_valid())

    def test_group_by_node(self):
        """Test group by node."""
        group_params = {"node": ["*"]}
        serializer = OCPGCPGroupBySerializer(data=group_params)
        self.assertTrue(serializer.is_valid())

    def test_all_group_by_op_fields(self):
        """Test that the allowed fields pass."""
        for field in OCPGCPGroupBySerializer._opfields:
            field = "and:" + field
            filter_param = {field: ["1", "2"]}
            serializer = OCPGCPGroupBySerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())
        for field in OCPGCPGroupBySerializer._opfields:
            field = "or:" + field
            filter_param = {field: ["1", "2"]}
            serializer = OCPGCPGroupBySerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())


class OCPGCPOrderBySerializerTest(TestCase):
    """Tests for the order_by serializer."""

    def test_order_by_project(self):
        """Test order by project."""
        order_params = {"project": "asc"}
        serializer = OCPGCPOrderBySerializer(data=order_params)
        self.assertTrue(serializer.is_valid())

    def test_order_by_cluster(self):
        """Test order by cluster."""
        order_params = {"cluster": "asc"}
        serializer = OCPGCPOrderBySerializer(data=order_params)
        self.assertTrue(serializer.is_valid())

    def test_order_by_node(self):
        """Test order by node."""
        order_params = {"node": "asc"}
        serializer = OCPGCPOrderBySerializer(data=order_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_order_by_params_success(self):
        """Test parse of a order_by param successfully."""
        order_params = {"cost": "asc"}
        serializer = OCPGCPOrderBySerializer(data=order_params)
        self.assertTrue(serializer.is_valid())

    def test_order_by_params_invalid_fields(self):
        """Test parse of order_by params for invalid fields."""
        order_params = {"region": "asc", "invalid": "param"}
        serializer = OCPGCPOrderBySerializer(data=order_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class OCPGCPQueryParamSerializerTest(IamTestCase):
    """Tests for the handling query parameter parsing serializer."""

    def test_parse_query_gcp_params_success(self):
        """Test parse of a query params successfully."""
        query_params = {
            "group_by": {"instance_type": [FAKE.word()]},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "region": [FAKE.uuid4()],
            },
        }

        self.request_path = "/api/cost-management/v1/reports/openshift/infrastructures/gcp/costs/"
        serializer = OCPGCPQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid())

    def test_parse_query_ocp_params_success(self):
        """Test parse of a query params successfully."""
        query_params = {
            "group_by": {"project": ["account"]},
            "order_by": {"project": "asc"},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_scope": [],
            },
        }

        self.request_path = "/api/cost-management/v1/reports/openshift/infrastructures/gcp/costs/"
        serializer = OCPGCPQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid())

    def test_query_params_invalid_fields(self):
        """Test parse of query params for invalid fields."""
        query_params = {
            "group_by": {"instance_type": [FAKE.word()]},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "account": [FAKE.word()],
            },
            "invalid": "param",
        }

        self.request_path = "/api/cost-management/v1/reports/openshift/infrastructures/gcp/costs/"
        serializer = OCPGCPQueryParamSerializer(data=query_params, context=self.ctx_w_path)
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
                "region": [FAKE.uuid4()],
            },
        }

        self.request_path = "/api/cost-management/v1/reports/openshift/infrastructures/gcp/costs/"
        serializer = OCPGCPQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ["valid_tag"]
        query_params = {"filter": {"valid_tag": "value"}}

        self.request_path = "/api/cost-management/v1/reports/openshift/infrastructures/gcp/costs/"
        serializer = OCPGCPQueryParamSerializer(data=query_params, tag_keys=tag_keys, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"filter": {"bad_tag": "value"}}

        self.request_path = "/api/cost-management/v1/reports/openshift/infrastructures/gcp/costs/"
        serializer = OCPGCPQueryParamSerializer(data=query_params, tag_keys=tag_keys, context=self.ctx_w_path)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_valid_delta_costs(self):
        """Test successful handling of valid delta for cost requests."""
        query_params = {"delta": "cost"}
        self.request_path = "/api/cost-management/v1/reports/gcp/costs/"
        serializer = OCPGCPQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid())

    def test_valid_delta_usage(self):
        """Test successful handling of valid delta for usage requests."""
        query_params = {"delta": "usage"}
        self.request_path = "/api/cost-management/v1/reports/gcp/storage/"
        serializer = OCPGCPQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid())

    def test_invalid_delta_costs(self):
        """Test failure while handling invalid delta for cost requests."""
        query_params = {"delta": "cost_bad"}
        self.request_path = "/api/cost-management/v1/reports/gcp/storage/"
        serializer = OCPGCPQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_invalid_delta_usage(self):
        """Test failure while handling invalid delta for usage requests."""
        query_params = {"delta": "usage"}
        self.request_path = "/api/cost-management/v1/reports/gcp/costs/"
        serializer = OCPGCPQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_order_by_service_with_groupby(self):
        """Test that order_by[service] works with a matching group-by."""
        query_params = {"group_by": {"service": "asc"}, "order_by": {"service": "asc"}}

        self.request_path = "/api/cost-management/v1/reports/openshift/infrastructures/gcp/costs/"
        serializer = OCPGCPQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid())

    def test_order_by_service_without_groupby(self):
        """Test that order_by[service] fails without a matching group-by."""
        query_params = {"order_by": {"service": "asc"}}

        self.request_path = "/api/cost-management/v1/reports/openshift/infrastructures/gcp/costs/"
        serializer = OCPGCPQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_query_params_invalid_order_by_request(self):
        """Test parse of charge query params for invalid fields."""
        # Charge can't order by request or usage
        query_params = {
            "group_by": {"region": [FAKE.uuid4()]},
            "order_by": {"request": "asc"},
            "filter": {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day"},
            "invalid": "param",
        }
        self.request_path = "/api/cost-management/v1/reports/openshift/infrastructures/gcp/costs/"
        serializer = OCPGCPQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_query_params_invalid_order_by_usage(self):
        """Test parse of charge query params for invalid fields."""
        # Charge can't order by request or usage
        query_params = {
            "group_by": {"region": [FAKE.uuid4()]},
            "order_by": {"usage": "asc"},
            "filter": {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day"},
            "invalid": "param",
        }

        self.request_path = "/api/cost-management/v1/reports/openshift/infrastructures/gcp/costs/"
        serializer = OCPGCPQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_fail_without_group_by(self):
        """Test fail if filter[limit] and filter[offset] passed without group by."""
        param_failures_list = [
            {"filter": {"limit": "1", "offset": "1"}},
            {"filter": {"limit": "1"}},
            {"filter": {"offset": "1"}},
        ]
        self.request_path = "/api/cost-management/v1/reports/openshift/infrastructures/gcp/costs/"
        for param in param_failures_list:
            with self.subTest(param=param):
                with self.assertRaises(serializers.ValidationError):
                    serializer = OCPGCPQueryParamSerializer(data=param, context=self.ctx_w_path)
                    self.assertFalse(serializer.is_valid())
                    serializer.is_valid(raise_exception=True)
