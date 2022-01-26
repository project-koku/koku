#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCP on Cloud Report serializers."""
from rest_framework import serializers

from api.iam.test.iam_test_case import IamTestCase
from api.report.all.openshift.serializers import OCPAllQueryParamSerializer


class OCPAllQueryParamSerializerTest(IamTestCase):
    """Tests for the handling query parameter parsing serializer."""

    def setUp(self):
        """setting up a user to test with."""
        self.user_data = self._create_user_data()
        self.alt_request_context = self._create_request_context(
            {"account_id": "10001", "schema_name": self.schema_name}, self.user_data, create_tenant=True, path=""
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
        serializer = OCPAllQueryParamSerializer(data=query_params, context=self.alt_request_context)
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
        serializer = OCPAllQueryParamSerializer(data=query_params)
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
        serializer = OCPAllQueryParamSerializer(data=query_params, context=self.alt_request_context)
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
        context = self._create_request_context(
            {"account_id": "10001", "schema_name": self.schema_name},
            self._create_user_data(),
            create_tenant=True,
            path="/api/cost-management/v1/reports/openshift/infrastructures/all/costs/",
        )
        serializer = OCPAllQueryParamSerializer(data=query_params, context=context)
        serializer.is_valid(raise_exception=True)
        query_params["delta"] = "cost_total"
        serializer = OCPAllQueryParamSerializer(data=query_params, context=context)
        serializer.is_valid(raise_exception=True)

    def test_query_params_valid_cost_type(self):
        """Test parse of valid cost_type param."""
        query_params = {"cost_type": "blended_cost"}
        serializer = OCPAllQueryParamSerializer(data=query_params, context=self.alt_request_context)
        serializer.is_valid(raise_exception=True)

    def test_query_params_invalid_cost_type(self):
        """Test parse of invalid cost_type param."""
        query_params = {"cost_type": "invalid_cost"}
        serializer = OCPAllQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)
