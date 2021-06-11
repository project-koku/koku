#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCP on Cloud Report serializers."""
from unittest import TestCase
from unittest.mock import Mock

from rest_framework import serializers

from api.report.all.openshift.serializers import OCPAllQueryParamSerializer


class OCPAllQueryParamSerializerTest(TestCase):
    """Tests for the handling query parameter parsing serializer."""

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
        serializer = OCPAllQueryParamSerializer(data=query_params)
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
        serializer = OCPAllQueryParamSerializer(data=query_params)
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
        req = Mock(path="/api/cost-management/v1/reports/openshift/infrastructures/all/costs/")
        serializer = OCPAllQueryParamSerializer(data=query_params, context={"request": req})
        serializer.is_valid(raise_exception=True)
        query_params["delta"] = "cost_total"
        req = Mock(path="/api/cost-management/v1/reports/openshift/infrastructures/all/costs/")
        serializer = OCPAllQueryParamSerializer(data=query_params, context={"request": req})
        serializer.is_valid(raise_exception=True)
