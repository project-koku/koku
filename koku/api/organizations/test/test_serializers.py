#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the organizations serializer."""
from unittest import TestCase

from dateutil.relativedelta import relativedelta
from rest_framework import serializers

from api.iam.test.iam_test_case import IamTestCase
from api.organizations.serializers import AWSOrgFilterSerializer
from api.organizations.serializers import AWSOrgQueryParamSerializer
from api.utils import DateHelper
from api.utils import materialized_view_month_start


class AWSOrgFilterSerializerTest(TestCase):
    """Tests for the AWS filter serializer."""

    def test_parse_filter_params_w_project_success(self):
        """Test parse of a filter param with project successfully."""
        filter_params = {
            "resolution": "daily",
            "time_scope_value": "-10",
            "time_scope_units": "day",
            "org_unit_id": "r-id",
        }
        serializer = AWSOrgFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_filter_params_w_project_failure(self):
        """Test parse of a filter param with an invalid project."""
        filter_params = {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day", "account": 3}
        serializer = AWSOrgFilterSerializer(data=filter_params)
        self.assertFalse(serializer.is_valid())

    def test_parse_filter_params_type_fail(self):
        """Test parse of a filter param with type for invalid type."""
        types = ["aws_tags", "pod", "storage"]
        for tag_type in types:
            filter_params = {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day", "type": None}
            filter_params["type"] = tag_type
            serializer = AWSOrgFilterSerializer(data=filter_params)
            self.assertFalse(serializer.is_valid())


class AWSOrgExcludeSerializerTest(TestCase):
    """Tests for the AWS exclude serializer."""

    def test_parse_exclude_params_w_project_success(self):
        """Test parse of a exclude param with project successfully."""
        exculde_params = {
            "org_unit_id": "r-id",
        }
        serializer = AWSOrgFilterSerializer(data=exculde_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_exculde_params_w_project_failure(self):
        """Test parse of a exclude param with an invalid project."""
        exculde_params = {"account": 3}
        serializer = AWSOrgFilterSerializer(data=exculde_params)
        self.assertFalse(serializer.is_valid())

    def test_parse_exculde_params_type_fail(self):
        """Test parse of a filter param with type for invalid type."""
        types = ["aws_tags", "pod", "storage"]
        for tag_type in types:
            exculde_params = {"type": None}
            exculde_params["type"] = tag_type
            serializer = AWSOrgFilterSerializer(data=exculde_params)
            self.assertFalse(serializer.is_valid())


class AWSOrgQueryParamSerializerTest(IamTestCase):
    """Tests for the handling query parameter parsing serializer."""

    def test_parse_query_params_success(self):
        """Test parse of a query params successfully."""
        query_params = {
            "filter": {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day"},
            "limit": "5",
            "offset": "3",
        }
        self.request_path = "/api/cost-management/v1/organizations/aws/"
        serializer = AWSOrgQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid())

    def test_parse_query_params_filter_with_org_unit_id_success(self):
        """Test parse of a query params successfully."""
        query_params = {
            "filter": {
                "resolution": "daily",
                "time_scope_value": "-10",
                "time_scope_units": "day",
                "org_unit_id": "r-id",
            },
            "limit": "5",
            "offset": "3",
        }

        self.request_path = "/api/cost-management/v1/organizations/aws/"
        serializer = AWSOrgQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid(raise_exception=True))

    def test_parse_query_params_exclude_with_org_unit_id_success(self):
        """Test parse of a query params successfully."""
        query_params = {
            "filter": {"resolution": "daily", "time_scope_value": "-10", "time_scope_units": "day"},
            "exclude": {"org_unit_id": "r-id"},
            "limit": "5",
            "offset": "3",
        }
        self.request_path = "/api/cost-management/v1/organizations/aws/"
        serializer = AWSOrgQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        self.assertTrue(serializer.is_valid(raise_exception=True))

    def test_query_params_invalid_fields(self):
        """Test parse of query params for invalid fields."""
        query_params = {"invalid": "invalid"}
        self.request_path = "/api/cost-management/v1/organizations/aws/"
        serializer = AWSOrgQueryParamSerializer(data=query_params, context=self.ctx_w_path)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_parse_filter_dates_valid(self):
        """Test parse of a filter date-based param should succeed."""
        dh = DateHelper()
        self.request_path = "/api/cost-management/v1/organizations/aws/"
        scenarios = [
            {"start_date": dh.yesterday.date(), "end_date": dh.today.date()},
            {"start_date": dh.this_month_start.date(), "end_date": dh.today.date()},
            {"start_date": dh.tomorrow.date(), "end_date": dh.tomorrow.date()},
            {
                "start_date": dh.last_month_end.date(),
                "end_date": dh.this_month_start.date(),
                "filter": {"resolution": "daily"},
            },
            {
                "start_date": dh.last_month_start.date(),
                "end_date": dh.last_month_end.date(),
                "filter": {"resolution": "daily"},
            },
        ]

        for params in scenarios:
            with self.subTest(params=params):
                serializer = AWSOrgQueryParamSerializer(data=params, context=self.ctx_w_path)
                self.assertTrue(serializer.is_valid(raise_exception=True))

    def test_parse_filter_dates_invalid(self):
        """Test parse of invalid data for filter date-based param should not succeed."""
        dh = DateHelper()
        self.request_path = "/api/cost-management/v1/organizations/aws/"
        scenarios = [
            {"start_date": dh.today.date()},
            {"end_date": dh.today.date()},
            {"start_date": dh.yesterday.date(), "end_date": dh.tomorrow.date() + relativedelta(days=1)},
            {
                "start_date": dh.tomorrow.date() + relativedelta(days=1),
                "end_date": dh.tomorrow.date() + relativedelta(days=1),
            },
            {"start_date": dh.n_days_ago(materialized_view_month_start(dh), 1).date(), "end_date": dh.today.date()},
            {"start_date": "llamas", "end_date": dh.yesterday.date()},
            {"start_date": dh.yesterday.date(), "end_date": "alpacas"},
            {"start_date": "llamas", "end_date": "alpacas"},
            {
                "start_date": dh.last_month_start.date(),
                "end_date": dh.last_month_end.date(),
                "filter": {"time_scope_units": "day"},
            },
            {
                "start_date": dh.last_month_start.date(),
                "end_date": dh.last_month_end.date(),
                "filter": {"time_scope_value": "-1"},
            },
            {
                "start_date": dh.last_month_start.date(),
                "end_date": dh.last_month_end.date(),
                "filter": {"time_scope_units": "day", "time_scope_value": "-1"},
            },
        ]

        for params in scenarios:
            with self.subTest(params=params):
                serializer = AWSOrgQueryParamSerializer(data=params, context=self.ctx_w_path)
                self.assertFalse(serializer.is_valid())
