#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import json
from unittest.mock import patch

from django.urls import reverse
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.report.test.util.constants import OCP_PLATFORM_NAMESPACE
from api.settings.cost_groups.query_handler import _remove_default_projects
from api.settings.cost_groups.query_handler import put_openshift_namespaces
from api.utils import DateHelper
from common.queues import OCPQueue
from koku.koku_test_runner import OCP_ON_GCP_CLUSTER_ID
from reporting.provider.ocp.models import OCPProject
from reporting.provider.ocp.models import OpenshiftCostCategory
from reporting.provider.ocp.models import OpenshiftCostCategoryNamespace


class FailedToPopulateDummyProjects(Exception):
    pass


class TestCostGroupsAPI(IamTestCase):
    def setUp(self):
        """Set up the account settings view tests."""
        super().setUp()
        self.client = APIClient()
        self.default_cost_group = "Platform"
        with schema_context(self.schema_name):
            project_to_insert = (
                OCPProject.objects.exclude(project=OCP_PLATFORM_NAMESPACE)
                .values("cluster__provider__uuid", "project")
                .first()
            )

            self.custom_cost_group = OpenshiftCostCategory.objects.create(name="Overhead", label=[])

        self.project = project_to_insert.get("project")
        self.provider_uuid = project_to_insert.get("cluster__provider__uuid")
        self.body_format = [{"project": self.project, "group": self.default_cost_group}]

    @property
    def url(self):
        return reverse("settings-cost-groups")

    @property
    def add_url(self):
        return reverse("settings-cost-groups-add")

    @property
    def remove_url(self):
        return reverse("settings-cost-groups-remove")

    def test_get_cost_groups(self):
        """Basic test to exercise the API endpoint"""
        with schema_context(self.schema_name):
            response = self.client.get(self.url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_cost_groups_invalid(self):
        with schema_context(self.schema_name):
            response = self.client.get(self.url, {"nope": "nope"}, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_cost_groups_filters(self):
        """Basic test to exercise the API endpoint"""
        parameters = (
            {"group": self.default_cost_group},
            {"default": True},
            {"project": OCP_PLATFORM_NAMESPACE},
            {},
        )
        for parameter in parameters:
            with self.subTest(parameter=parameter):
                for filter_option, filter_value in parameter.items():
                    param = {f"filter[{filter_option}]": filter_value}
                    with schema_context(self.schema_name):
                        response = self.client.get(self.url, param, **self.headers)

                    data = response.data.get("data")

                    self.assertEqual(response.status_code, status.HTTP_200_OK)
                    for item in data:
                        self.assertEqual(item.get(filter_option), filter_value)

    def test_get_cost_groups_not_default(self):
        """Test that filtering for non-default groups returns only items with
        null and False values"""

        param = {"filter[default]": "0"}
        with schema_context(self.schema_name):
            response = self.client.get(self.url, param, **self.headers)

        data = response.data.get("data")
        result = {item.get("default") for item in data}

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(result.issubset((None, False)))

    def test_get_cost_groups_filter_cluster(self):
        """Basic test to exercise the API endpoint"""
        param = {"filter[cluster]": OCP_ON_GCP_CLUSTER_ID}
        with schema_context(self.schema_name):
            response = self.client.get(self.url, param, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data.get("data")
        for item in data:
            self.assertIn(OCP_ON_GCP_CLUSTER_ID, item.get("clusters"))

    def test_get_cost_groups_filters_multiple(self):
        """Test filtering with multiple values per field"""
        test_matrix = (
            {
                "field": "group",
                "value": ["Platform"],
                "expected": {"Platform"},
            },
            {
                "field": "project",
                "value": [OCP_PLATFORM_NAMESPACE, "-PrOd"],
                "expected": {"openshift-default", "koku-prod"},
            },
        )
        for case in test_matrix:
            with self.subTest(parameter=case["value"]):
                params = {f"filter[{case['field']}]": case["value"]}
                with schema_context(self.schema_name):
                    response = self.client.get(self.url, params, **self.headers)

                data = response.data.get("data")
                result = {}
                if data:
                    result = {item[case["field"]] for item in data}

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertTrue(result.issubset(case["expected"]))

    def test_get_cost_groups_order(self):
        """Basic test to exercise the API endpoint"""

        def spotcheck_first_data_element(option, value):
            param = {f"order_by[{option}]": value}
            with schema_context(self.schema_name):
                response = self.client.get(self.url, param, **self.headers)

            return response.status_code, response.data.get("data")[0]

        order_by_options = ["group", "default", "project"]
        for order_by_option in order_by_options:
            with self.subTest(order_by_option=order_by_option):
                asc_status_code, spotcheck_asc = spotcheck_first_data_element(order_by_option, "asc")
                self.assertEqual(asc_status_code, status.HTTP_200_OK)
                desc_status_code, spotcheck_desc = spotcheck_first_data_element(order_by_option, "desc")
                self.assertEqual(desc_status_code, status.HTTP_200_OK)
                self.assertNotEqual(spotcheck_asc, spotcheck_desc)

    def test_get_cost_groups_exclude_functionality(self):
        """Test that values can be excluded in the return."""
        parameters = [
            {"group": "Platform"},
            {"default": True},
            {"project": "koku"},
            {"cluster": OCP_ON_GCP_CLUSTER_ID},
        ]
        for parameter in parameters:
            with self.subTest(parameter=parameter):
                for exclude_option, exclude_value in parameter.items():
                    param = {f"exclude[{exclude_option}]": exclude_value}
                    with schema_context(self.schema_name):
                        response = self.client.get(self.url, param, **self.headers)
                    self.assertEqual(response.status_code, status.HTTP_200_OK)
                    data = response.data.get("data")
                    for item in data:
                        if exclude_option in ["group", "default"]:
                            self.assertNotEqual(item.get(exclude_option), exclude_value)
                        else:
                            self.assertNotIn(exclude_value, item.get(exclude_option))

    @patch("api.settings.cost_groups.view.CostGroupsView._summarize_current_month")
    def test_delete_cost_groups(self, mock_summarize_current_month):
        """Test that we can delete projects from the namespaces."""

        def _add_additional_projects(schema_name):
            with schema_context(schema_name):
                current_rows = OpenshiftCostCategoryNamespace.objects.count()
                expected_count = current_rows + 1
                put_openshift_namespaces(self.body_format)
                current_count = OpenshiftCostCategoryNamespace.objects.count()

            if current_count != expected_count:
                raise FailedToPopulateDummyProjects("Failed to populate dummy data for deletion testing.")

        _add_additional_projects(self.schema_name)
        body = json.dumps(self.body_format)
        with schema_context(self.schema_name):
            response = self.client.put(self.remove_url, body, content_type="application/json", **self.headers)
            current_count = OpenshiftCostCategoryNamespace.objects.filter(namespace=self.project).count()

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(current_count, 0)
        mock_summarize_current_month.assert_called()

    def test_query_handler_remove_default_projects(self):
        """Test that you can not delete a default project."""
        with schema_context(self.schema_name):
            body_format = [
                {
                    "project": OCP_PLATFORM_NAMESPACE,
                    "group": self.default_cost_group,
                },
                {
                    "project": "openshift",
                    "group": self.default_cost_group,
                },
            ]
            self.assertEqual(_remove_default_projects(body_format), [])

    def test_put_catch_integrity_error(self):
        """Test that we catch integrity errors when moving a project to a
        different Cost Group."""

        with schema_context(self.schema_name):
            # Create an entry with a project in the default Cost Group
            put_openshift_namespaces(self.body_format)

        with self.assertLogs(logger="api.settings.cost_groups.query_handler", level="WARNING") as log_warning:
            with schema_context(self.schema_name):
                # Move a project to another Cost Group
                put_openshift_namespaces([{"project": self.project, "group": self.custom_cost_group.name}])

        self.assertEqual(len(log_warning.records), 1)  # Check that a warning log was generated
        self.assertIn("IntegrityError", log_warning.records[0].getMessage())

    @patch("api.settings.cost_groups.view.update_summary_tables.s")
    @patch("api.settings.cost_groups.view.get_customer_queue")
    def test_add_new_records(self, mock_get_customer_queue, mock_update_schedule):
        mock_get_customer_queue.return_value = OCPQueue.DEFAULT
        with schema_context(self.schema_name):
            body = json.dumps(self.body_format)
            response = self.client.put(self.add_url, body, content_type="application/json", **self.headers)
            current_count = OpenshiftCostCategoryNamespace.objects.filter(namespace=self.project).count()

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(current_count, 1)
        mock_get_customer_queue.assert_called_once_with(self.schema_name, OCPQueue)
        mock_update_schedule.assert_any_call(
            self.schema_name,
            provider_type=Provider.PROVIDER_OCP,
            provider_uuid=self.provider_uuid,
            start_date=DateHelper().this_month_start,
        )
        mock_update_schedule.return_value.apply_async.assert_called_with(queue=OCPQueue.DEFAULT)

    @patch("api.settings.cost_groups.view.update_summary_tables.s")
    @patch("api.settings.cost_groups.view.get_customer_queue", return_value=False)
    def test_move_project_to_different_cost_group(self, mock_get_customer_queue, mock_update_schedule):
        """Test moving an existing project to a different Cost Group"""

        with schema_context(self.schema_name):
            # Add a project to the default Cost Group
            body = json.dumps(self.body_format)
            self.client.put(self.add_url, body, content_type="application/json", **self.headers)
            OpenshiftCostCategoryNamespace.objects.filter(namespace=self.project).count()

            # Move the project to a custom Cost Group
            body = json.dumps([{"project": self.project, "group": self.custom_cost_group.name}])
            response = self.client.put(self.add_url, body, content_type="application/json", **self.headers)
            current_count = OpenshiftCostCategoryNamespace.objects.filter(
                cost_category_id=self.custom_cost_group.id
            ).count()

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(current_count, 1)

    @patch("api.settings.cost_groups.view.update_summary_tables.s")
    @patch("api.settings.cost_groups.view.get_customer_queue")
    def test_add_new_records_large(self, mock_get_customer_queue, mock_update_schedule):
        mock_get_customer_queue.return_value = OCPQueue.XL
        with schema_context(self.schema_name):
            body = json.dumps(self.body_format)
            response = self.client.put(self.add_url, body, content_type="application/json", **self.headers)
            current_count = OpenshiftCostCategoryNamespace.objects.filter(namespace=self.project).count()

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(current_count, 1)
        mock_get_customer_queue.assert_called_once_with(self.schema_name, OCPQueue)
        mock_update_schedule.assert_any_call(
            self.schema_name,
            provider_type=Provider.PROVIDER_OCP,
            provider_uuid=self.provider_uuid,
            start_date=DateHelper().this_month_start,
        )
        mock_update_schedule.return_value.apply_async.assert_called_with(queue=OCPQueue.XL)
