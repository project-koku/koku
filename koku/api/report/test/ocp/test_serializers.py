#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Report serializers."""
from unittest import TestCase

from rest_framework import serializers

from api.iam.test.iam_test_case import IamTestCase
from api.report.ocp.serializers import OCPCostBreakdownExcludeSerializer
from api.report.ocp.serializers import OCPCostBreakdownFilterSerializer
from api.report.ocp.serializers import OCPCostBreakdownGroupBySerializer
from api.report.ocp.serializers import OCPCostBreakdownOrderBySerializer
from api.report.ocp.serializers import OCPCostBreakdownQueryParamSerializer
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


# =============================================================================
# Cost Breakdown Serializer Tests (Phase 4)
# =============================================================================


class OCPCostBreakdownGroupBySerializerTest(TestCase):
    """Tests for the cost breakdown group_by serializer."""

    def test_all_group_by_op_fields(self):
        """Test that cluster, project, node are all valid group_by fields."""
        for field in ("cluster", "project", "node"):
            data = {field: ["*"]}
            serializer = OCPCostBreakdownGroupBySerializer(data=data)
            self.assertTrue(serializer.is_valid(), f"{field} should be valid: {serializer.errors}")

    def test_invalid_group_by_field_rejected(self):
        """Test that fields not in _opfields are rejected."""
        serializer = OCPCostBreakdownGroupBySerializer(data={"account": ["test"]})
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class OCPCostBreakdownOrderBySerializerTest(TestCase):
    """Tests for the cost breakdown order_by serializer."""

    def test_valid_order_by_fields(self):
        """Test that path, depth, cost_value are valid order_by fields."""
        for field in ("path", "depth", "cost_value"):
            serializer = OCPCostBreakdownOrderBySerializer(data={field: "asc"})
            self.assertTrue(serializer.is_valid(), f"{field} should be valid: {serializer.errors}")

    def test_order_by_distributed_cost_valid(self):
        """Test that distributed_cost is a valid order_by field."""
        serializer = OCPCostBreakdownOrderBySerializer(data={"distributed_cost": "desc"})
        self.assertTrue(serializer.is_valid(), f"distributed_cost should be valid: {serializer.errors}")

    def test_invalid_order_by_field_rejected(self):
        """Test that unsupported order_by fields are rejected."""
        serializer = OCPCostBreakdownOrderBySerializer(data={"usage": "asc"})
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class OCPCostBreakdownFilterSerializerTest(TestCase):
    """Tests for the cost breakdown filter serializer."""

    def test_valid_filter_fields(self):
        """Test that all opfields are accepted."""
        for field in ("cluster", "project", "node"):
            data = {field: ["test-value"]}
            serializer = OCPCostBreakdownFilterSerializer(data=data)
            self.assertTrue(serializer.is_valid(), f"{field} should be valid: {serializer.errors}")

    def test_depth_filter_valid_range(self):
        """Test that depth filter accepts values 1-5 (as strings from URL params)."""
        for depth in ("1", "3", "5"):
            serializer = OCPCostBreakdownFilterSerializer(data={"depth": depth})
            self.assertTrue(serializer.is_valid(), f"depth={depth} should be valid: {serializer.errors}")

    def test_depth_filter_invalid_range(self):
        """Test that depth filter rejects values outside 1-5."""
        for depth in ("0", "6", "-1"):
            serializer = OCPCostBreakdownFilterSerializer(data={"depth": depth})
            self.assertFalse(serializer.is_valid(), f"depth={depth} should be invalid")

    def test_top_category_filter_valid(self):
        """Test that top_category accepts project, overhead, and total."""
        for cat in ("project", "overhead", "total"):
            serializer = OCPCostBreakdownFilterSerializer(data={"top_category": [cat]})
            self.assertTrue(serializer.is_valid(), f"top_category={cat} should be valid")

    def test_top_category_filter_invalid(self):
        """Test that top_category rejects invalid values."""
        serializer = OCPCostBreakdownFilterSerializer(data={"top_category": ["invalid"]})
        self.assertFalse(serializer.is_valid())

    def test_path_with_dashes_accepted(self):
        """[H3] Path filter must accept dashes — rate names contain them.

        e.g. 'project.usage_cost.cpu_core_usage_per_hour-Infrastructure'
        Regression test for H3: regex ^[a-zA-Z0-9_.]+$ rejects dashes.
        """
        dashed_path = "project.usage_cost.cpu_core_usage_per_hour-Infrastructure"
        serializer = OCPCostBreakdownFilterSerializer(data={"path": [dashed_path]})
        self.assertTrue(
            serializer.is_valid(),
            f"Path with dashes should be accepted but got: {serializer.errors}",
        )

    def test_path_rejects_injection_characters(self):
        """Path filter must reject SQL injection characters."""
        for bad_path in ("'; DROP TABLE--", "path OR 1=1", "test<script>"):
            serializer = OCPCostBreakdownFilterSerializer(data={"path": [bad_path]})
            self.assertFalse(serializer.is_valid(), f"Path '{bad_path}' should be rejected")

    def test_path_accepts_dotted_segments(self):
        """Path filter accepts normal dotted breakdown paths."""
        valid_paths = [
            "total_cost",
            "project.usage_cost",
            "overhead.platform_distributed.infrastructure",
            "overhead.worker_distributed.usage_cost.memory_gb_usage_per_hour",
        ]
        for path in valid_paths:
            serializer = OCPCostBreakdownFilterSerializer(data={"path": [path]})
            self.assertTrue(serializer.is_valid(), f"Path '{path}' should be valid: {serializer.errors}")


class OCPCostBreakdownExcludeSerializerTest(TestCase):
    """Tests for the cost breakdown exclude serializer."""

    def test_cluster_exclude_valid(self):
        """Test that cluster exclude is valid."""
        serializer = OCPCostBreakdownExcludeSerializer(data={"cluster": ["test-cluster"]})
        self.assertTrue(serializer.is_valid())

    def test_invalid_exclude_field_rejected(self):
        """Test that non-cluster exclude fields are rejected."""
        serializer = OCPCostBreakdownExcludeSerializer(data={"invalid": "param"})
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class OCPCostBreakdownQueryParamSerializerTest(IamTestCase):
    """Tests for the cost breakdown query parameter serializer."""

    def test_valid_flat_view(self):
        """Test that view=flat is accepted."""
        query_params = {
            "filter": {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day"},
        }
        self.request_path = "/api/cost-management/v1/breakdown/openshift/cost/"
        serializer = OCPCostBreakdownQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data.get("view"), "flat")

    def test_valid_tree_view(self):
        """Test that view=tree is accepted."""
        query_params = {
            "view": "tree",
            "filter": {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day"},
        }
        self.request_path = "/api/cost-management/v1/breakdown/openshift/cost/"
        serializer = OCPCostBreakdownQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_invalid_view_rejected(self):
        """Test that view=invalid is rejected."""
        query_params = {
            "view": "graph",
            "filter": {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day"},
        }
        self.request_path = "/api/cost-management/v1/breakdown/openshift/cost/"
        serializer = OCPCostBreakdownQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertFalse(serializer.is_valid())

    def test_group_by_cluster(self):
        """Test that group_by[cluster] is accepted."""
        query_params = {
            "group_by": {"cluster": ["*"]},
            "filter": {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day"},
        }
        self.request_path = "/api/cost-management/v1/breakdown/openshift/cost/"
        serializer = OCPCostBreakdownQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_order_by_with_group_by(self):
        """Test that order_by[cost_value] is accepted when paired with group_by."""
        query_params = {
            "group_by": {"cluster": ["*"]},
            "order_by": {"cost_value": "desc"},
            "filter": {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day"},
        }
        self.request_path = "/api/cost-management/v1/breakdown/openshift/cost/"
        serializer = OCPCostBreakdownQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_order_by_allowlist_no_group_by(self):
        """Test that allowlisted order_by fields work without group_by."""
        query_params = {
            "order_by": {"cost_value": "desc"},
            "filter": {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day"},
        }
        self.request_path = "/api/cost-management/v1/breakdown/openshift/cost/"
        serializer = OCPCostBreakdownQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_order_by_distributed_cost_no_group_by(self):
        """Test that distributed_cost in allowlist works without group_by."""
        query_params = {
            "order_by": {"distributed_cost": "desc"},
            "filter": {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day"},
        }
        self.request_path = "/api/cost-management/v1/breakdown/openshift/cost/"
        serializer = OCPCostBreakdownQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_breakdown_tag_filter_dropped(self):
        """Tag filter keys are dropped so breakdown API accepts request without error."""
        query_params = {
            "filter": {"cluster": ["test-cluster"], "tag:application": ["Istio"]},
            "group_by": {"cluster": ["*"]},
        }
        self.request_path = "/api/cost-management/v1/breakdown/openshift/cost/"
        serializer = OCPCostBreakdownQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn("tag:application", serializer.validated_data.get("filter", {}))
        self.assertIn("cluster", serializer.validated_data.get("filter", {}))


# =============================================================================
# Tree Builder Unit Tests (Phase 4 — OCPCostBreakdownView._build_tree)
# =============================================================================


class OCPCostBreakdownTreeBuilderTest(TestCase):
    """Unit tests for _build_tree and _transform_to_tree (pure logic, no DB)."""

    def _make_flat_breakdown(self):
        """Produce a minimal valid flat breakdown matching the population SQL output."""
        return [
            {
                "path": "total_cost",
                "parent_path": "",
                "depth": 1,
                "custom_name": "total_cost",
                "cost_value": 100,
                "distributed_cost": 50,
                "metric_type": "aggregate",
            },
            {
                "path": "project",
                "parent_path": "total_cost",
                "depth": 2,
                "custom_name": "project",
                "cost_value": 60,
                "distributed_cost": None,
                "metric_type": "aggregate",
            },
            {
                "path": "overhead",
                "parent_path": "total_cost",
                "depth": 2,
                "custom_name": "overhead",
                "cost_value": None,
                "distributed_cost": 50,
                "metric_type": "aggregate",
            },
            {
                "path": "project.usage_cost",
                "parent_path": "project",
                "depth": 3,
                "custom_name": "usage_cost",
                "cost_value": 60,
                "distributed_cost": None,
                "metric_type": "aggregate",
            },
            {
                "path": "project.usage_cost.cpu_rate",
                "parent_path": "project.usage_cost",
                "depth": 4,
                "custom_name": "cpu_rate",
                "cost_value": 60,
                "distributed_cost": None,
                "metric_type": "cpu",
            },
            {
                "path": "overhead.platform_distributed",
                "parent_path": "overhead",
                "depth": 3,
                "custom_name": "platform_distributed",
                "cost_value": None,
                "distributed_cost": 50,
                "metric_type": "aggregate",
            },
            {
                "path": "overhead.platform_distributed.usage_cost",
                "parent_path": "overhead.platform_distributed",
                "depth": 4,
                "custom_name": "usage_cost",
                "cost_value": None,
                "distributed_cost": 50,
                "metric_type": "aggregate",
            },
            {
                "path": "overhead.platform_distributed.usage_cost.cpu_rate",
                "parent_path": "overhead.platform_distributed.usage_cost",
                "depth": 5,
                "custom_name": "cpu_rate",
                "cost_value": None,
                "distributed_cost": 50,
                "metric_type": "cpu",
            },
        ]

    def test_build_tree_root_is_depth_1(self):
        """Tree root must be the depth-1 node."""
        from api.report.ocp.view import OCPCostBreakdownView

        tree = OCPCostBreakdownView._build_tree(self._make_flat_breakdown())
        self.assertEqual(tree["depth"], 1)
        self.assertEqual(tree["path"], "total_cost")

    def test_build_tree_children_count(self):
        """Root should have exactly 2 children: project and overhead."""
        from api.report.ocp.view import OCPCostBreakdownView

        tree = OCPCostBreakdownView._build_tree(self._make_flat_breakdown())
        self.assertEqual(len(tree["children"]), 2)
        child_names = {c["custom_name"] for c in tree["children"]}
        self.assertEqual(child_names, {"project", "overhead"})

    def test_build_tree_leaf_has_no_children(self):
        """Leaf nodes (depth 4/5) should have empty children lists."""
        from api.report.ocp.view import OCPCostBreakdownView

        tree = OCPCostBreakdownView._build_tree(self._make_flat_breakdown())
        project = next(c for c in tree["children"] if c["custom_name"] == "project")
        usage_cost = project["children"][0]
        cpu_rate = usage_cost["children"][0]
        self.assertEqual(cpu_rate["children"], [])

    def test_build_tree_empty_values_returns_empty_dict(self):
        """Empty input returns empty dict."""
        from api.report.ocp.view import OCPCostBreakdownView

        tree = OCPCostBreakdownView._build_tree([])
        self.assertEqual(tree, {})

    def test_transform_to_tree_replaces_values_key(self):
        """_transform_to_tree replaces 'values' with 'tree' key."""
        from api.report.ocp.view import OCPCostBreakdownView

        data_item = {"values": self._make_flat_breakdown()}
        OCPCostBreakdownView._transform_to_tree(data_item)
        self.assertNotIn("values", data_item)
        self.assertIn("tree", data_item)
        self.assertEqual(data_item["tree"]["depth"], 1)

    def test_transform_to_tree_nested_list(self):
        """_transform_to_tree recursively processes lists of dicts."""
        from api.report.ocp.view import OCPCostBreakdownView

        data = [{"values": self._make_flat_breakdown()}, {"other_key": "untouched"}]
        OCPCostBreakdownView._transform_to_tree(data)
        self.assertIn("tree", data[0])
        self.assertNotIn("tree", data[1])

    def test_build_tree_duplicate_paths_last_wins(self):
        """When duplicate paths exist, last item's data should be used."""
        from api.report.ocp.view import OCPCostBreakdownView

        values = [
            {"path": "total_cost", "parent_path": "", "depth": 1, "cost_value": 100},
            {"path": "total_cost", "parent_path": "", "depth": 1, "cost_value": 200},
        ]
        tree = OCPCostBreakdownView._build_tree(values)
        self.assertEqual(tree["cost_value"], 200)

    def test_build_tree_orphan_nodes_excluded(self):
        """Nodes whose parent_path is not in the set should not appear in any children list."""
        from api.report.ocp.view import OCPCostBreakdownView

        values = [
            {"path": "total_cost", "parent_path": "", "depth": 1, "cost_value": 100},
            {"path": "orphan.child", "parent_path": "nonexistent", "depth": 3, "cost_value": 10},
        ]
        tree = OCPCostBreakdownView._build_tree(values)
        self.assertEqual(tree["children"], [])

    def test_build_tree_single_root_only(self):
        """A single depth-1 node returns correctly with empty children."""
        from api.report.ocp.view import OCPCostBreakdownView

        values = [{"path": "total_cost", "parent_path": "", "depth": 1, "cost_value": 50}]
        tree = OCPCostBreakdownView._build_tree(values)
        self.assertEqual(tree["path"], "total_cost")
        self.assertEqual(tree["children"], [])
