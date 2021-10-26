#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCP on AWS Report serializers."""
from unittest import TestCase
from unittest.mock import Mock

from rest_framework import serializers

from api.iam.test.iam_test_case import IamTestCase
from api.report.aws.openshift.serializers import OCPAWSFilterSerializer
from api.report.aws.openshift.serializers import OCPAWSGroupBySerializer
from api.report.aws.openshift.serializers import OCPAWSOrderBySerializer
from api.report.aws.openshift.serializers import OCPAWSQueryParamSerializer


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
        self.user_data = self._create_user_data()
        self.alt_request_context = self._create_request_context(
            self.create_mock_customer_data(), self.user_data, create_tenant=True, path=""
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
            "units": "byte",
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
        serializer = OCPAWSQueryParamSerializer(data=query_params, context=self.alt_request_context)
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
        req = Mock(path="/api/cost-management/v1/reports/openshift/infrastructures/aws/costs/")
        serializer = OCPAWSQueryParamSerializer(data=query_params, context={"request": req})
        serializer.is_valid(raise_exception=True)
        query_params["delta"] = "cost_total"
        req = Mock(path="/api/cost-management/v1/reports/openshift/infrastructures/aws/costs/")
        serializer = OCPAWSQueryParamSerializer(data=query_params, context={"request": req})
        serializer.is_valid(raise_exception=True)

    def test_query_params_valid_cost_type(self):
        """Test parse of valid cost_type param."""
        query_params = {"cost_type": "blended_cost"}
        serializer = OCPAWSQueryParamSerializer(data=query_params, context=self.alt_request_context)
        serializer.is_valid(raise_exception=True)

    def test_query_params_invalid_cost_type(self):
        """Test parse of invalid cost_type param."""
        query_params = {"cost_type": "invalid_cost"}
        serializer = OCPAWSQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)
