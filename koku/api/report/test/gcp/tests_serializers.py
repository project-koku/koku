#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test GCP Serializer."""
from unittest import TestCase
from unittest.mock import Mock

from faker import Faker
from rest_framework import serializers

from api.report.gcp.serializers import GCPFilterSerializer
from api.report.gcp.serializers import GCPGroupBySerializer
from api.report.gcp.serializers import GCPOrderBySerializer
from api.report.gcp.serializers import GCPQueryParamSerializer

FAKE = Faker()


class GCPFilterSerializerTest(TestCase):
    """Tests for the filter serializer."""

    def test_parse_filter_params_success(self):
        """Test parse of a filter param successfully."""
        filter_params = {
            "resolution": "daily",
            "time_scope_value": "-10",
            "time_scope_units": "day",
            "region": FAKE.word(),
            "account": FAKE.uuid4(),
            "gcp_project": FAKE.word(),
            "service": FAKE.word(),
        }
        serializer = GCPFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_filter_params_no_time(self):
        """Test parse of a filter param no time filter."""
        filter_params = {"region": FAKE.word(), "account": FAKE.uuid4(), "service": FAKE.word()}
        serializer = GCPFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_filter_params_invalid_fields(self):
        """Test parse of filter params for invalid fields."""
        filter_params = {"invalid": "param"}
        serializer = GCPFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_time_scope_daily(self):
        """Test parse of filter params for invalid daily time_scope_units."""
        filter_params = {"resolution": "daily", "time_scope_value": "-1", "time_scope_units": "day"}
        serializer = GCPFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_time_scope_monthly(self):
        """Test parse of filter params for invalid month time_scope_units."""
        filter_params = {"resolution": "monthly", "time_scope_value": "-10", "time_scope_units": "month"}
        serializer = GCPFilterSerializer(data=filter_params)
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
        serializer = GCPFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_limit_time_scope_resolution(self):
        """Test parse of filter params for invalid resolution time_scope_units."""
        filter_params = {"resolution": "monthly", "time_scope_value": "-10", "time_scope_units": "day"}
        serializer = GCPFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ["valid_tag"]
        query_params = {"valid_tag": "value"}
        serializer = GCPFilterSerializer(data=query_params, tag_keys=tag_keys)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"bad_tag": "value"}
        serializer = GCPFilterSerializer(data=query_params, tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_all_filter_op_fields(self):
        """Test that the allowed fields pass."""
        for field in GCPFilterSerializer._opfields:
            field = "and:" + field
            filter_param = {field: ["1", "2"]}
            serializer = GCPFilterSerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())
        for field in GCPFilterSerializer._opfields:
            field = "or:" + field
            filter_param = {field: ["1", "2"]}
            serializer = GCPFilterSerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())


class GCPGroupBySerializerTest(TestCase):
    """Tests for the group_by serializer."""

    def test_parse_group_by_params_success(self):
        """Test parse of a group_by param successfully."""
        group_by_options = ["account", "region", "service", "gcp_project"]
        for group_by in group_by_options:
            group_params = {group_by: [FAKE.uuid4()]}
            serializer = GCPGroupBySerializer(data=group_params)
            self.assertTrue(serializer.is_valid())

    def test_group_by_params_invalid_fields(self):
        """Test parse of group_by params for invalid fields."""
        group_params = {"resource_location": [FAKE.word()], "invalid": "param"}
        serializer = GCPGroupBySerializer(data=group_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_group_by_params_string_list_fields(self):
        """Test group_by params for handling string to list fields."""
        group_params = {"gcp_project": FAKE.word()}
        serializer = GCPGroupBySerializer(data=group_params)
        validation = serializer.is_valid()
        self.assertTrue(validation)
        result = serializer.data.get("gcp_project")
        self.assertIsInstance(result, list)

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ["valid_tag"]
        query_params = {"valid_tag": "*"}
        serializer = GCPGroupBySerializer(data=query_params, tag_keys=tag_keys)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"bad_tag": "*"}
        serializer = GCPGroupBySerializer(data=query_params, tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_all_group_by_op_fields(self):
        """Test that the allowed fields pass."""
        for field in GCPGroupBySerializer._opfields:
            field = "and:" + field
            filter_param = {field: ["1", "2"]}
            serializer = GCPGroupBySerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())
        for field in GCPGroupBySerializer._opfields:
            field = "or:" + field
            filter_param = {field: ["1", "2"]}
            serializer = GCPGroupBySerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())


class GCPOrderBySerializerTest(TestCase):
    """Tests for the order_by serializer."""

    def test_parse_order_by_params_success(self):
        """Test parse of a order_by param successfully."""
        order_params = {"cost": "asc"}
        serializer = GCPOrderBySerializer(data=order_params)
        self.assertTrue(serializer.is_valid())

    def test_order_by_params_invalid_fields(self):
        """Test parse of order_by params for invalid fields."""
        order_params = {"cost": "asc", "invalid": "param"}
        serializer = GCPOrderBySerializer(data=order_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class GCPQueryParamSerializerTest(TestCase):
    """Tests for the handling query parameter parsing serializer."""

    def test_parse_query_params_success(self):
        """Test parse of a query params successfully."""
        query_params = {
            "group_by": {"gcp_project": [FAKE.word()]},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "account": [FAKE.uuid4()],
            },
        }
        serializer = GCPQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_query_params_invalid_fields(self):
        """Test parse of query params for invalid fields."""
        query_params = {
            "group_by": {"account": [FAKE.word()]},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_location": [FAKE.word()],
            },
            "invalid": "param",
        }
        serializer = GCPQueryParamSerializer(data=query_params)
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
        serializer = GCPQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_parse_units(self):
        """Test pass while parsing units query params."""
        query_params = {"units": "bytes"}
        serializer = GCPQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_units_failure(self):
        """Test failure while parsing units query params."""
        query_params = {"units": "bites"}
        serializer = GCPQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ["valid_tag"]
        query_params = {"filter": {"valid_tag": "value"}}
        serializer = GCPQueryParamSerializer(data=query_params, tag_keys=tag_keys)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"filter": {"bad_tag": "value"}}
        serializer = GCPQueryParamSerializer(data=query_params, tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_valid_deltas(self):
        """Test successful handling of valid delta for cost requests."""
        valid_delta_map = {
            "/api/cost-management/v1/reports/gcp/costs/": ["cost", "cost_total"],
            "/api/cost-management/v1/reports/gcp/instance-types/": ["usage"],
            "/api/cost-management/v1/reports/gcp/storage/": ["usage"],
        }
        for url, delta_list in valid_delta_map.items():
            req = Mock(path=url)
            for valid_delta in delta_list:
                query_params = {"delta": valid_delta}
                serializer = GCPQueryParamSerializer(data=query_params, context={"request": req})
                self.assertTrue(serializer.is_valid())

    def test_invalid_deltas(self):
        """Test failure while handling invalid delta for gcp endpoints."""
        bad_delta_map = {
            "/api/cost-management/v1/reports/gcp/costs/": ["usage", "bad_delta"],
            "/api/cost-management/v1/reports/gcp/instance-types/": ["cost", "cost_total", "bad_delta"],
            "/api/cost-management/v1/reports/gcp/storage/": ["cost", "cost_total", "bad_delta"],
        }
        for url, delta_list in bad_delta_map.items():
            req = Mock(path=url)
            for bad_delta in delta_list:
                query_params = {"delta": bad_delta}
                serializer = GCPQueryParamSerializer(data=query_params, context={"request": req})
                with self.assertRaises(serializers.ValidationError):
                    serializer.is_valid(raise_exception=True)

    def test_order_by_service_with_groupby(self):
        """Test that order_by[service] works with a matching group-by."""
        query_params = {"group_by": {"service": "asc"}, "order_by": {"service": "asc"}}
        serializer = GCPQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_order_by_service_without_groupby(self):
        """Test that order_by[service_name] fails without a matching group-by."""
        query_params = {"order_by": {"service_name": "asc"}}
        serializer = GCPQueryParamSerializer(data=query_params)
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
        serializer = GCPQueryParamSerializer(data=query_params)
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
        serializer = GCPQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)
