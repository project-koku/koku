#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Report serializers."""
from unittest import TestCase

from rest_framework import serializers

from api.iam.test.iam_test_case import IamTestCase
from api.report.ocp.serializers import OCPCostQueryParamSerializer
from api.report.ocp.serializers import OCPExcludeSerializer
from api.report.ocp.serializers import OCPFilterSerializer
from api.report.ocp.serializers import OCPGpuFilterSerializer
from api.report.ocp.serializers import OCPGpuGroupBySerializer
from api.report.ocp.serializers import OCPGpuOrderBySerializer
from api.report.ocp.serializers import OCPGpuQueryParamSerializer
from api.report.ocp.serializers import OCPGroupBySerializer
from api.report.ocp.serializers import OCPInventoryQueryParamSerializer
from api.report.ocp.serializers import OCPOrderBySerializer
from api.report.ocp.serializers import OCPQueryParamSerializer


class OCPExcludeSerializerTest(TestCase):
    """Tests for the exclude serializer."""

    def test_exclude_params_invalid_fields(self):
        """Test parse of exclude params for invalid fields."""
        exclude_params = {
            "invalid": "param",
        }
        serializer = OCPExcludeSerializer(data=exclude_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ["valid_tag"]
        query_params = {"valid_tag": "value"}
        serializer = OCPExcludeSerializer(data=query_params, tag_keys=tag_keys)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"bad_tag": "value"}
        serializer = OCPExcludeSerializer(data=query_params, tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_infrastructure_field_validation_success(self):
        """Test that infrastructure exclude are validated for aws."""
        query_params = {"infrastructures": "aws"}
        serializer = OCPExcludeSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_infrastructure_field_validation_failure(self):
        """Test that infrastructure exclude are validated for non-aws."""
        query_params = {"infrastructures": "notaws"}
        serializer = OCPExcludeSerializer(data=query_params)
        self.assertFalse(serializer.is_valid())

    def test_all_exclude_op_fields(self):
        """Test that the allowed fields pass."""
        for field in OCPExcludeSerializer._opfields:
            field = "and:" + field
            exclude_param = {field: ["1", "2"]}
            serializer = OCPExcludeSerializer(data=exclude_param)
            self.assertTrue(serializer.is_valid())
        for field in OCPExcludeSerializer._opfields:
            field = "or:" + field
            exclude_param = {field: ["1", "2"]}
            serializer = OCPExcludeSerializer(data=exclude_param)
            self.assertTrue(serializer.is_valid())


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
        serializer = OCPFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_filter_params_no_time(self):
        """Test parse of a filter param no time filter."""
        filter_params = {"resource_scope": ["S3"]}
        serializer = OCPFilterSerializer(data=filter_params)
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
        serializer = OCPFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_time_scope_daily(self):
        """Test parse of filter params for invalid daily time_scope_units."""
        filter_params = {"resolution": "daily", "time_scope_value": "-1", "time_scope_units": "day"}
        serializer = OCPFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_time_scope_monthly(self):
        """Test parse of filter params for invalid month time_scope_units."""
        filter_params = {"resolution": "monthly", "time_scope_value": "-10", "time_scope_units": "month"}
        serializer = OCPFilterSerializer(data=filter_params)
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
        serializer = OCPFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_limit_time_scope_resolution(self):
        """Test parse of filter params for invalid resolution time_scope_units."""
        filter_params = {"resolution": "monthly", "time_scope_value": "-10", "time_scope_units": "day"}
        serializer = OCPFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ["valid_tag"]
        query_params = {"valid_tag": "value"}
        serializer = OCPFilterSerializer(data=query_params, tag_keys=tag_keys)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"bad_tag": "value"}
        serializer = OCPFilterSerializer(data=query_params, tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_infrastructure_field_validation_success(self):
        """Test that infrastructure filter are validated for aws."""
        query_params = {"infrastructures": "aws"}
        serializer = OCPFilterSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_infrastructure_field_validation_failure(self):
        """Test that infrastructure filter are validated for non-aws."""
        query_params = {"infrastructures": "notaws"}
        serializer = OCPFilterSerializer(data=query_params)
        self.assertFalse(serializer.is_valid())

    def test_all_filter_op_fields(self):
        """Test that the allowed fields pass."""
        for field in OCPFilterSerializer._opfields:
            field = "and:" + field
            filter_param = {field: ["1", "2"]}
            serializer = OCPFilterSerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())
        for field in OCPFilterSerializer._opfields:
            field = "or:" + field
            filter_param = {field: ["1", "2"]}
            serializer = OCPFilterSerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())


class OCPGroupBySerializerTest(TestCase):
    """Tests for the group_by serializer."""

    def test_parse_group_by_params_success(self):
        """Test parse of a group_by param successfully."""
        group_params = {"cluster": ["cluster1"]}
        serializer = OCPGroupBySerializer(data=group_params)
        self.assertTrue(serializer.is_valid())

    def test_group_by_params_invalid_fields(self):
        """Test parse of group_by params for invalid fields."""
        group_params = {"account": ["account1"], "invalid": "param"}
        serializer = OCPGroupBySerializer(data=group_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_group_by_params_string_list_fields(self):
        """Test group_by params for handling string to list fields."""
        group_params = {"node": "localhost"}
        serializer = OCPGroupBySerializer(data=group_params)
        validation = serializer.is_valid()
        self.assertTrue(validation)
        node_result = serializer.data.get("node")
        self.assertIsInstance(node_result, list)

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ["valid_tag"]
        query_params = {"valid_tag": "*"}
        serializer = OCPGroupBySerializer(data=query_params, tag_keys=tag_keys)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"bad_tag": "*"}
        serializer = OCPGroupBySerializer(data=query_params, tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_all_group_by_op_fields(self):
        """Test that the allowed fields pass."""
        for field in OCPGroupBySerializer._opfields:
            field = "and:" + field
            filter_param = {field: ["1", "2"]}
            serializer = OCPGroupBySerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())
        for field in OCPGroupBySerializer._opfields:
            field = "or:" + field
            filter_param = {field: ["1", "2"]}
            serializer = OCPGroupBySerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())


class OCPOrderBySerializerTest(IamTestCase):
    """Tests for the order_by serializer."""

    def test_parse_order_by_params_success(self):
        """Test parse of a order_by param successfully."""
        order_params = {"project": "asc"}
        serializer = OCPOrderBySerializer(data=order_params)
        self.assertTrue(serializer.is_valid())

    def test_order_by_params_invalid_fields(self):
        """Test parse of order_by params for invalid fields."""
        order_params = {"cost": "asc", "invalid": "param"}
        serializer = OCPOrderBySerializer(data=order_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_to_internal_value_invalid_data(self):
        serializer = OCPOrderBySerializer()
        with self.assertRaises(serializers.ValidationError):
            serializer.to_internal_value("")


class OCPQueryParamSerializerTest(IamTestCase):
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
        self.request_path = "/api/cost-management/v1/reports/openshift/costs/"
        serializer = OCPQueryParamSerializer(data=query_params, context=self.ctx_w_path)
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

        self.request_path = "/api/cost-management/v1/reports/openshift/costs/"
        serializer = OCPQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_query_params_invalid_multiple_group_bys_with_pvc(self):
        """Test parse of query params for invalid fields."""
        query_params = {
            "group_by": {"persistentvolumeclaim": ["*"], "node": ["*"]},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_scope": [],
            },
        }
        self.request_path = "/api/cost-management/v1/reports/openshift/volume/?filter[storage_class]=*"
        serializer = OCPQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid())

    def test_query_params_valid_multiple_group_bys_with_pvc(self):
        """Test parse of query params for invalid fields."""
        query_params = {
            "group_by": {"persistentvolumeclaim": ["*"], "project": ["*"]},
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "resource_scope": [],
            },
        }
        self.request_path = "/api/cost-management/v1/reports/openshift/volume/"
        serializer = OCPQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid())

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
        self.request_path = "/api/cost-management/v1/reports/openshift/costs/"
        serializer = OCPQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ["valid_tag"]
        query_params = {"filter": {"valid_tag": "value"}}

        self.request_path = "/api/cost-management/v1/reports/openshift/costs/"
        serializer = OCPQueryParamSerializer(data=query_params, tag_keys=tag_keys, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ["valid_tag"]
        query_params = {"filter": {"bad_tag": "value"}}

        self.request_path = "/api/cost-management/v1/reports/openshift/costs/"
        serializer = OCPQueryParamSerializer(data=query_params, tag_keys=tag_keys, context=self.ctx_w_path)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_fail_with_max_group_by(self):
        """Test fail if more than 2 group bys given."""
        query_params = {
            "group_by": {"cluster": ["cluster"], "node": ["node"], "project": ["project"]},
        }
        self.request_path = "/api/cost-management/v1/reports/openshift/infrastructures/aws/costs/"
        with self.assertRaises(serializers.ValidationError):
            serializer = OCPQueryParamSerializer(data=query_params, context=self.ctx_w_path)
            self.assertFalse(serializer.is_valid())
            serializer.is_valid(raise_exception=True)


class OCPInventoryQueryParamSerializerTest(IamTestCase):
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
        self.request_path = "/api/cost-management/v1/reports/openshift/costs/"
        serializer = OCPInventoryQueryParamSerializer(data=query_params, context=self.ctx_w_path)
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
        self.request_path = "/api/cost-management/v1/reports/openshift/costs/"
        serializer = OCPInventoryQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_delta_success(self):
        """Test that a proper delta value is serialized."""
        valid_deltas = ["cost", "usage", "request"]
        url_base = "/api/cost-management/v1/reports/openshift/costs/"
        for valid_delta in valid_deltas:
            with self.subTest(valid_delta=valid_delta):
                self.request_path = url_base + f"?delta={valid_delta}"
                query_params = {"delta": valid_delta}
                serializer = OCPInventoryQueryParamSerializer(data=query_params, context=self.ctx_w_path)
                self.assertTrue(serializer.is_valid())

    def test_distributed_cost_group_by_project(self):
        """Test the group by project requirement."""
        self.request_path = (
            "/api/cost-management/v1/reports/openshift/costs/?group_by[project]=*&order_by[distributed_cost=asc"
        )
        params = {"order_by": {"distributed_cost": "asc"}, "group_by": {"project": ["*"]}}
        serializer = OCPQueryParamSerializer(data=params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid())

    def test_storage_class_without_group_by(self):
        """Test the group by project requirement."""
        self.request_path = (
            "/api/cost-management/v1/reports/openshift/volume/?group_by[project]=*&order_by[distributed_cost=asc"
        )
        params = {"order_by": {"storage_class": "asc"}, "group_by": {}}
        serializer = OCPQueryParamSerializer(data=params, context=self.ctx_w_path)
        self.assertFalse(serializer.is_valid())

    def test_persistentvolumeclaim_without_group_by(self):
        """Test the group by project requirement."""
        self.request_path = (
            "/api/cost-management/v1/reports/openshift/volume/?group_by[project]=*&order_by[distributed_cost=asc"
        )
        params = {"order_by": {"persistentvolumeclaim": "asc"}, "group_by": {}}
        serializer = OCPQueryParamSerializer(data=params, context=self.ctx_w_path)
        self.assertFalse(serializer.is_valid())

    def test_persistentvolumeclaim_with_group_by_persistentvolumeclaim(self):
        """Test the group by project requirement."""
        self.request_path = (
            "/api/cost-management/v1/reports/openshift/volume/?group_by[project]=*&order_by[distributed_cost=asc"
        )
        params = {"order_by": {"persistentvolumeclaim": "asc"}, "group_by": {"persistentvolumeclaim": ["pvc1"]}}
        serializer = OCPQueryParamSerializer(data=params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid())

    def test_storage_class_with_group_by_persistentvolumeclaim(self):
        """Test the group by project requirement."""
        self.request_path = (
            "/api/cost-management/v1/reports/openshift/volume/?group_by[project]=*&order_by[distributed_cost=asc"
        )
        params = {"order_by": {"persistentvolumeclaim": "asc"}, "group_by": {"persistentvolumeclaim": ["pvc1"]}}
        serializer = OCPQueryParamSerializer(data=params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid())

    def test_delta_failure(self):
        """Test that a bad delta value is not serialized."""
        query_params = {"delta": "bad_delta"}
        self.request_path = "/api/cost-management/v1/reports/openshift/costs/?delta=bad_delta"
        serializer = OCPInventoryQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_current_month_delta_success(self):
        """Test that a proper current month delta value is serialized."""
        base_url = "/api/cost-management/v1/reports/openshift/costs/"
        valid_deltas = ["usage__request", "usage__capacity", "request__capacity"]
        for valid_delta in valid_deltas:
            with self.subTest(valid_delta=valid_delta):
                self.request_path = base_url + f"?delta={valid_delta}"
                query_params = {"delta": valid_delta}
                serializer = OCPInventoryQueryParamSerializer(data=query_params, context=self.ctx_w_path)
                self.assertTrue(serializer.is_valid())

    def test_current_month_delta_failure(self):
        """Test that a bad current month delta value is not serialized."""
        self.request_path = "/api/cost-management/v1/reports/openshift/costs/"
        query_params = {"delta": "bad__delta"}
        serializer = OCPInventoryQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

        query_params = {"delta": "usage__request__capacity"}
        serializer = OCPInventoryQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_order_by_delta_with_delta(self):
        """Test that order_by[delta] works with a delta param."""
        self.request_path = "/api/cost-management/v1/reports/openshift/costs/"
        query_params = {"delta": "usage__request", "order_by": {"delta": "asc"}}
        serializer = OCPInventoryQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid())

    def test_order_by_delta_without_delta(self):
        """Test that order_by[delta] does not work without a delta param."""
        self.request_path = "/api/cost-management/v1/reports/openshift/costs/"
        query_params = {"order_by": {"delta": "asc"}}
        serializer = OCPInventoryQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_order_by_distributed_cost_without_project(self):
        """Test that order_by[delta] does not work without a delta param."""
        self.request_path = "/api/cost-management/v1/reports/openshift/costs/"
        query_params = {"order_by": {"distributed_cost": "asc"}}
        serializers_list = [
            OCPInventoryQueryParamSerializer,
            OCPQueryParamSerializer,
            OCPCostQueryParamSerializer,
            OCPOrderBySerializer,
        ]
        for serializer_class in serializers_list:
            with self.subTest(serializer_class=serializer_class):
                serializer = serializer_class(data=query_params, context=self.ctx_w_path)
                with self.assertRaises(serializers.ValidationError):
                    serializer.is_valid(raise_exception=True)

    def test_delta_distributed_cost_without_project(self):
        """Test that order_by[delta] does not work without a delta param."""
        self.request_path = "/api/cost-management/v1/reports/openshift/costs/"
        query_params = {"delta": "distributed_cost"}
        serializers_list = [
            OCPInventoryQueryParamSerializer,
            OCPQueryParamSerializer,
            OCPCostQueryParamSerializer,
            OCPOrderBySerializer,
        ]
        for serializer_class in serializers_list:
            with self.subTest(serializer_class=serializer_class):
                serializer = serializer_class(data=query_params, context=self.ctx_w_path)
                with self.assertRaises(serializers.ValidationError):
                    serializer.is_valid(raise_exception=True)

    def test_order_by_node_with_groupby(self):
        """Test that order_by[node] works with a matching group-by."""
        self.request_path = "/api/cost-management/v1/reports/openshift/costs/"
        query_params = {"group_by": {"node": "asc"}, "order_by": {"node": "asc"}}
        serializer = OCPInventoryQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid())

    def test_order_by_node_without_groupby(self):
        """Test that order_by[node] fails without a matching group-by."""
        self.request_path = "/api/cost-management/v1/reports/openshift/costs/"
        query_params = {"order_by": {"node": "asc"}}
        serializer = OCPInventoryQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class OCPCostQueryParamSerializerTest(IamTestCase):
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
        self.request_path = "/api/cost-management/v1/reports/openshift/costs/"
        serializer = OCPCostQueryParamSerializer(data=query_params, context=self.ctx_w_path)
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
        self.request_path = "/api/cost-management/v1/reports/openshift/costs/"
        serializer = OCPCostQueryParamSerializer(data=query_params, context=self.ctx_w_path)
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
        self.request_path = "/api/cost-management/v1/reports/openshift/costs/"
        serializer = OCPCostQueryParamSerializer(data=query_params, context=self.ctx_w_path)
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
        self.request_path = "/api/cost-management/v1/reports/openshift/costs/"
        serializer = OCPCostQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_fail_without_group_by(self):
        """Test fail if filter[limit] and filter[offset] passed without group by."""
        param_failures_list = [
            {"filter": {"limit": "1", "offset": "1"}},
            {"filter": {"limit": "1"}},
            {"filter": {"offset": "1"}},
        ]
        self.request_path = "/api/cost-management/v1/reports/openshift/costs/"
        for param in param_failures_list:
            with self.subTest(param=param):
                with self.assertRaises(serializers.ValidationError):
                    serializer = OCPInventoryQueryParamSerializer(data=param, context=self.ctx_w_path)
                    self.assertFalse(serializer.is_valid())
                    serializer.is_valid(raise_exception=True)


class OCPGpuGroupBySerializerTest(TestCase):
    """Tests for the GPU group_by serializer."""

    def test_gpu_group_by_params_valid_fields(self):
        """Test parse of GPU group_by params with valid fields."""
        group_by_params = {
            "cluster": ["cluster1"],
            "project": ["project1"],
            "gpu_vendor": ["nvidia"],
            "gpu_model": ["Tesla T4"],
        }
        serializer = OCPGpuGroupBySerializer(data=group_by_params)
        self.assertTrue(serializer.is_valid())

    def test_gpu_group_by_params_invalid_fields(self):
        """Test parse of GPU group_by params with invalid fields."""
        group_by_params = {"invalid_field": ["value"]}
        serializer = OCPGpuGroupBySerializer(data=group_by_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class OCPGpuFilterSerializerTest(TestCase):
    """Tests for the GPU filter serializer."""

    def test_gpu_filter_params_valid_fields(self):
        """Test parse of GPU filter params with valid fields."""
        filter_params = {
            "cluster": ["cluster1"],
            "node": ["node1"],
            "project": ["project1"],
            "gpu_vendor": ["nvidia"],
            "gpu_model": ["Tesla T4"],
        }
        serializer = OCPGpuFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_gpu_filter_params_invalid_fields(self):
        """Test parse of GPU filter params with invalid fields."""
        filter_params = {"invalid_field": ["value"]}
        serializer = OCPGpuFilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class OCPGpuOrderBySerializerTest(TestCase):
    """Tests for the GPU order_by serializer."""

    def test_gpu_order_by_params_valid_fields(self):
        """Test parse of GPU order_by params with valid fields."""
        valid_fields = [
            "cluster",
            "node",
            "project",
            "gpu_vendor",
            "gpu_model",
            "cost_model_gpu_cost",
            "cost",
            "gpu_memory",
            "gpu_count",
        ]
        for field in valid_fields:
            serializer = OCPGpuOrderBySerializer(data={field: "asc"})
            self.assertTrue(serializer.is_valid(), f"Field {field} should be valid")

    def test_gpu_order_by_params_invalid_fields(self):
        """Test that uptime and usage are NOT valid."""
        invalid_params = [{"uptime": "asc"}, {"invalid_field": "asc"}, {"usage": "desc"}]
        for param in invalid_params:
            serializer = OCPGpuOrderBySerializer(data=param)
            with self.assertRaises(serializers.ValidationError):
                serializer.is_valid(raise_exception=True)
        # Verify invalid fields are not in _opfields
        self.assertNotIn("uptime", OCPGpuOrderBySerializer._opfields)
        self.assertNotIn("usage", OCPGpuOrderBySerializer._opfields)
        # Verify gpu_count IS in _opfields (now supported)
        self.assertIn("gpu_count", OCPGpuOrderBySerializer._opfields)


class OCPGpuQueryParamSerializerTest(IamTestCase):
    """Tests for the GPU query parameter serializer."""

    def test_gpu_query_params_valid(self):
        """Test GPU query params with valid input."""
        query_params = {
            "filter": {"gpu_vendor": ["nvidia"], "gpu_model": ["Tesla T4"]},
            "group_by": {"cluster": ["*"]},
            "order_by": {"cost": "desc"},
        }
        self.request_path = "/api/cost-management/v1/reports/openshift/gpu/"
        serializer = OCPGpuQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid())

    def test_gpu_order_by_allowlist_fields(self):
        """Test that memory, and gpu_count are in order_by_allowlist."""
        self.assertIn("gpu_memory", OCPGpuQueryParamSerializer.order_by_allowlist)
        self.assertIn("gpu_count", OCPGpuQueryParamSerializer.order_by_allowlist)

    def test_gpu_query_params_order_by_new_fields(self):
        """Test GPU query params with new order_by fields (gpu_memory, gpu_count)."""
        for field in ["gpu_memory", "gpu_count"]:
            query_params = {
                "filter": {"gpu_vendor": ["nvidia"]},
                "group_by": {"gpu_model": ["*"]},
                "order_by": {field: "desc"},
            }
            self.request_path = "/api/cost-management/v1/reports/openshift/gpu/"
            serializer = OCPGpuQueryParamSerializer(data=query_params, context=self.ctx_w_path)
            self.assertTrue(serializer.is_valid(), f"order_by with {field} should be valid")

    def test_gpu_query_params_combined(self):
        """Test GPU query params with combined filter, group_by, and order_by."""
        query_params = {
            "filter": {"gpu_vendor": ["nvidia"], "node": ["node1", "node2"]},
            "group_by": {"project": ["*"]},
            "order_by": {"cost": "desc"},
        }
        self.request_path = "/api/cost-management/v1/reports/openshift/gpu/"
        serializer = OCPGpuQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid())

    def test_gpu_order_by_model_with_group_by_model(self):
        """Test that order_by[gpu_model] works with group_by[gpu_model]."""
        query_params = {
            "group_by": {"gpu_model": ["*"]},
            "order_by": {"gpu_model": "asc"},
        }
        self.request_path = "/api/cost-management/v1/reports/openshift/gpu/"
        serializer = OCPGpuQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid())

    def test_gpu_order_by_vendor_with_group_by_vendor(self):
        """Test that order_by[gpu_vendor] works with group_by[gpu_vendor]."""
        query_params = {
            "group_by": {"gpu_vendor": ["*"]},
            "order_by": {"gpu_vendor": "desc"},
        }
        self.request_path = "/api/cost-management/v1/reports/openshift/gpu/"
        serializer = OCPGpuQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid())

    def test_gpu_query_params_tag_filter_dropped(self):
        """Tag filter keys are dropped so GPU API accepts request without error; GPU cannot filter by tag."""
        query_params = {
            "filter": {"gpu_vendor": ["nvidia"], "tag:application": ["Istio"]},
            "group_by": {"gpu_model": ["*"]},
        }
        self.request_path = "/api/cost-management/v1/reports/openshift/gpu/"
        serializer = OCPGpuQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn("tag:application", serializer.validated_data.get("filter", {}))
        self.assertIn("gpu_vendor", serializer.validated_data.get("filter", {}))
