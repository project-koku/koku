#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCP on AWS Report serializers."""
from unittest import TestCase

from rest_framework import serializers

from api.iam.test.iam_test_case import IamTestCase
from api.report.aws.openshift.serializers import OCPAWSExcludeSerializer
from api.report.aws.openshift.serializers import OCPAWSFilterSerializer
from api.report.aws.openshift.serializers import OCPAWSGroupBySerializer
from api.report.aws.openshift.serializers import OCPAWSOrderBySerializer
from api.report.aws.openshift.serializers import OCPAWSQueryParamSerializer


class OCPAWSExcludeSerializerTest(TestCase):
    """Tests for the exclude serializer."""

    def test_parse_exclude_project(self):
        """Test exclude by project."""
        exclude_params = {"project": ["*"]}
        serializer = OCPAWSExcludeSerializer(data=exclude_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_exclude_cluster(self):
        """Test exclude by cluster."""
        exclude_params = {"cluster": ["*"]}
        serializer = OCPAWSExcludeSerializer(data=exclude_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_exclude_node(self):
        """Test exclude by node."""
        exclude_params = {"node": ["*"]}
        serializer = OCPAWSExcludeSerializer(data=exclude_params)
        self.assertTrue(serializer.is_valid())

    def test_all_exclude_op_fields(self):
        """Test that the allowed fields pass."""
        for field in OCPAWSExcludeSerializer._opfields:
            field = "and:" + field
            exclude_param = {field: ["1", "2"]}
            serializer = OCPAWSExcludeSerializer(data=exclude_param)
            self.assertTrue(serializer.is_valid())
        for field in OCPAWSExcludeSerializer._opfields:
            field = "or:" + field
            exclude_param = {field: ["1", "2"]}
            serializer = OCPAWSExcludeSerializer(data=exclude_param)
            self.assertTrue(serializer.is_valid())


class OCPAWSFilterSerializerTest(TestCase):
    """Tests for the filter serializer."""

    def test_parse_filter_params_success(self):
        """Test parse of a filter param successfully."""
        filter_params = {
            "resolution": "daily",
            "time_scope_value": "-10",
            "time_scope_units": "day",
            "resource_scope": [],
        }
        serializer = OCPAWSFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_filter_project(self):
        """Test filter by project."""
        filter_params = {"project": ["*"]}
        serializer = OCPAWSFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_filter_cluster(self):
        """Test filter by cluster."""
        filter_params = {"cluster": ["*"]}
        serializer = OCPAWSFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_filter_node(self):
        """Test filter by node."""
        filter_params = {"node": ["*"]}
        serializer = OCPAWSFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_all_filter_op_fields(self):
        """Test that the allowed fields pass."""
        for field in OCPAWSFilterSerializer._opfields:
            field = "and:" + field
            filter_param = {field: ["1", "2"]}
            serializer = OCPAWSFilterSerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())
        for field in OCPAWSFilterSerializer._opfields:
            field = "or:" + field
            filter_param = {field: ["1", "2"]}
            serializer = OCPAWSFilterSerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())


class OCPAWSGroupBySerializerTest(TestCase):
    """Tests for the group_by serializer."""

    def test_parse_group_by_project(self):
        """Test group by project."""
        group_params = {"project": ["*"]}
        serializer = OCPAWSGroupBySerializer(data=group_params)
        self.assertTrue(serializer.is_valid())

    def test_group_by_cluster(self):
        """Test group by cluster."""
        group_params = {"cluster": ["*"]}
        serializer = OCPAWSGroupBySerializer(data=group_params)
        self.assertTrue(serializer.is_valid())

    def test_group_by_node(self):
        """Test group by node."""
        group_params = {"node": ["*"]}
        serializer = OCPAWSGroupBySerializer(data=group_params)
        self.assertTrue(serializer.is_valid())

    def test_all_group_by_op_fields(self):
        """Test that the allowed fields pass."""
        for field in OCPAWSGroupBySerializer._opfields:
            field = "and:" + field
            filter_param = {field: ["1", "2"]}
            serializer = OCPAWSGroupBySerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())
        for field in OCPAWSGroupBySerializer._opfields:
            field = "or:" + field
            filter_param = {field: ["1", "2"]}
            serializer = OCPAWSGroupBySerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())


class OCPAWSOrderBySerializerTest(TestCase):
    """Tests for the order_by serializer."""

    def test_order_by_project(self):
        """Test order by project."""
        order_params = {"project": "asc"}
        serializer = OCPAWSOrderBySerializer(data=order_params)
        self.assertTrue(serializer.is_valid())

    def test_order_by_cluster(self):
        """Test order by cluster."""
        order_params = {"cluster": "asc"}
        serializer = OCPAWSOrderBySerializer(data=order_params)
        self.assertTrue(serializer.is_valid())

    def test_order_by_node(self):
        """Test order by node."""
        order_params = {"node": "asc"}
        serializer = OCPAWSOrderBySerializer(data=order_params)
        self.assertTrue(serializer.is_valid())


class OCPAWSQueryParamSerializerTest(IamTestCase):
    """Tests for the handling query parameter parsing serializer."""

    def setUp(self):
        """setting up a user to test with."""
        self.path = "/api/cost-management/v1/reports/openshift/infrastructures/aws/costs/"
        self.user_data = self._create_user_data()
        self.alt_request_context = self._create_request_context(
            {"account_id": "10001", "org_id": "1234567", "schema_name": self.schema_name},
            self.user_data,
            create_tenant=True,
            path=self.path,
        )

    def test_parse_query_params_success(self):
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
        }
        serializer = OCPAWSQueryParamSerializer(data=query_params, context=self.alt_request_context)
        self.assertTrue(serializer.is_valid())

    def test_query_params_invalid_delta(self):
        """Test parse of delta charge query params for invalid fields."""
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
        serializer = OCPAWSQueryParamSerializer(data=query_params)
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
            "delta": "usage",
        }
        context = self._create_request_context(
            {"account_id": "10001", "org_id": "1234567", "schema_name": self.schema_name},
            self._create_user_data(),
            create_tenant=True,
            path="",
        )
        serializer = OCPAWSQueryParamSerializer(data=query_params, context=context)
        serializer.is_valid(raise_exception=True)

    def test_query_params_valid_cost_delta(self):
        """Test parse of delta charge query params for valid fields."""
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
        serializer = OCPAWSQueryParamSerializer(data=query_params, context=self.alt_request_context)
        serializer.is_valid(raise_exception=True)
        query_params["delta"] = "cost_total"
        serializer = OCPAWSQueryParamSerializer(data=query_params, context=self.alt_request_context)
        serializer.is_valid(raise_exception=True)

    def test_query_params_invalid_cost_type(self):
        """Test that cost type is not allowed."""
        query_params = {"cost_type": "shplended_cost"}
        serializer = OCPAWSQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_fail_without_group_by(self):
        """Test fail if filter[limit] and filter[offset] passed without group by."""
        param_failures_list = [
            {"filter": {"limit": "1", "offset": "1"}},
            {"filter": {"limit": "1"}},
            {"filter": {"offset": "1"}},
        ]
        self.request_path = "/api/cost-management/v1/reports/openshift/infrastructures/aws/costs/"
        for param in param_failures_list:
            with self.subTest(param=param):
                with self.assertRaises(serializers.ValidationError):
                    serializer = OCPAWSQueryParamSerializer(data=param, context=self.ctx_w_path)
                    self.assertFalse(serializer.is_valid())
                    serializer.is_valid(raise_exception=True)

    def test_fail_with_max_group_by(self):
        """Test fail if more than 2 group bys given."""
        query_params = {
            "group_by": {"account": ["account1"], "service": ["ser"], "region": ["reg"]},
        }
        self.request_path = "/api/cost-management/v1/reports/openshift/infrastructures/aws/costs/"
        with self.assertRaises(serializers.ValidationError):
            serializer = OCPAWSQueryParamSerializer(data=query_params, context=self.ctx_w_path)
            self.assertFalse(serializer.is_valid())
            serializer.is_valid(raise_exception=True)
