#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import json
from unittest.mock import patch
from urllib.parse import quote_plus
from urllib.parse import urlencode

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
from reporting.provider.ocp.models import OpenshiftCostCategoryNamespace


class FailedToPopulateDummyProjects(Exception):
    pass


class TestCostGroupsAPI(IamTestCase):
    def setUp(self):
        """Set up the account settings view tests."""
        super().setUp()
        self.client = APIClient()

    @property
    def url(self):
        return reverse("settings-cost-groups")

    def test_get_cost_groups(self):
        """Basic test to exercise the API endpoint"""
        with schema_context(self.schema_name):
            response = self.client.get(self.url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_cost_groups_filters(self):
        """Basic test to exercise the API endpoint"""
        parameters = [{"group": "Platform"}, {"default": True}, {"project_name": OCP_PLATFORM_NAMESPACE}]
        for parameter in parameters:
            with self.subTest(parameter=parameter):
                for filter_option, filter_value in parameter.items():
                    param = {f"filter[{filter_option}]": filter_value}
                    url = self.url + "?" + urlencode(param, quote_via=quote_plus)
                    with schema_context(self.schema_name):
                        response = self.client.get(url, **self.headers)
                    self.assertEqual(response.status_code, status.HTTP_200_OK)
                    data = response.data.get("data")
                    for item in data:
                        self.assertEqual(item.get(filter_option), filter_value)

    def test_get_cost_groups_order(self):
        """Basic test to exercise the API endpoint"""

        def spotcheck_first_data_element(option, value):
            param = {f"order_by[{option}]": value}
            url = self.url + "?" + urlencode(param, quote_via=quote_plus)
            with schema_context(self.schema_name):
                response = self.client.get(url, **self.headers)
            return response.status_code, response.data.get("data")[0]

        order_by_options = ["group", "default", "project_name"]
        for order_by_option in order_by_options:
            with self.subTest(order_by_option=order_by_option):
                asc_status_code, spotcheck_asc = spotcheck_first_data_element(order_by_option, "asc")
                self.assertEqual(asc_status_code, status.HTTP_200_OK)
                desc_status_code, spotcheck_desc = spotcheck_first_data_element(order_by_option, "desc")
                self.assertEqual(desc_status_code, status.HTTP_200_OK)
                self.assertNotEqual(spotcheck_asc, spotcheck_desc)

    def test_get_cost_groups_exclude_functionality(self):
        """Test that values can be excluded in the return."""
        parameters = [{"group": "Platform"}, {"default": True}, {"project_name": "koku"}]
        for parameter in parameters:
            with self.subTest(parameter=parameter):
                for exclude_option, exclude_value in parameter.items():
                    param = {f"exclude[{exclude_option}]": exclude_value}
                    url = self.url + "?" + urlencode(param, quote_via=quote_plus)
                    with schema_context(self.schema_name):
                        response = self.client.get(url, **self.headers)
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

        def _add_additional_projects(schema_name, testing_prefix):
            with schema_context(schema_name):
                current_rows = OpenshiftCostCategoryNamespace.objects.count()
                additional_project_names = [f"{testing_prefix}project_{i}" for i in range(3)]
                expected_count = current_rows + len(additional_project_names)
                put_openshift_namespaces(additional_project_names)
                current_count = OpenshiftCostCategoryNamespace.objects.count()
                if current_count != expected_count:
                    raise FailedToPopulateDummyProjects("Failed to populate dummy data for deletion testing.")
                return additional_project_names

        testing_prefix = "TESTING_"
        dummy_projects = _add_additional_projects(self.schema_name, testing_prefix)
        body = json.dumps({"projects": dummy_projects})
        with schema_context(self.schema_name):
            response = self.client.delete(self.url, body, content_type="application/json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            current_count = OpenshiftCostCategoryNamespace.objects.filter(namespace__startswith=testing_prefix).count()
            self.assertEqual(current_count, 0)
            mock_summarize_current_month.assert_called()

    def test_query_handler_remove_default_projects(self):
        """Test that you can not delete a default project."""
        with schema_context(self.schema_name):
            self.assertEqual(_remove_default_projects([OCP_PLATFORM_NAMESPACE]), [])

    def test_put_catch_integrity_error(self):
        """Test that we catch integrity errors on put."""
        projects = ["project1", "project1"]
        with self.assertLogs(logger="api.settings.cost_groups.query_handler", level="WARNING") as log_warning:
            with schema_context(self.schema_name):
                put_openshift_namespaces(projects)
        self.assertEqual(len(log_warning.records), 1)  # Check that a warning log was generated
        self.assertIn("IntegrityError", log_warning.records[0].getMessage())

    @patch("api.settings.cost_groups.view.OCPProject.objects.filter")
    @patch("api.settings.cost_groups.view.update_summary_tables")
    @patch("api.settings.cost_groups.view.is_customer_large", return_value=False)
    def test_put_new_records(self, mock_is_customer_large, mock_update, mock_project):
        mock_provider_uuid = "fake_uuid_1"
        mock_values_list = mock_project.return_value.values_list.return_value
        mock_values_list.distinct.return_value = [mock_provider_uuid]
        namespace = "Test"
        body = json.dumps({"projects": [namespace]})
        with schema_context(self.schema_name):
            response = self.client.put(self.url, body, content_type="application/json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            current_count = OpenshiftCostCategoryNamespace.objects.filter(namespace__startswith=namespace).count()
            self.assertEqual(current_count, 1)
            mock_is_customer_large.assert_called_once_with(self.schema_name)
            mock_update.s.assert_called_with(
                self.schema_name,
                provider_type=Provider.PROVIDER_OCP,
                provider_uuid=mock_provider_uuid,
                start_date=DateHelper().this_month_start,
            )