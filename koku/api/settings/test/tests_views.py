#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Settings views."""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.tags.aws.queries import AWSTagQueryHandler
from api.tags.aws.view import AWSTagView
from api.tags.azure.queries import AzureTagQueryHandler
from api.tags.azure.view import AzureTagView
from api.tags.gcp.queries import GCPTagQueryHandler
from api.tags.gcp.view import GCPTagView
from api.tags.ocp.queries import OCPTagQueryHandler
from api.tags.ocp.view import OCPTagView
from api.utils import DateHelper
from koku.database import get_model


class SettingsViewTest(IamTestCase):
    """Tests for the settings view."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        cls.dh = DateHelper()

    def get_settings(self):
        """Request settings from API."""
        url = reverse("settings")
        client = APIClient()
        response = client.get(url, **self.headers)
        return response

    def post_settings(self, body):
        """Request settings from API."""
        url = reverse("settings")
        client = APIClient()
        response = client.post(url, data=body, format="json", **self.headers)
        return response

    def get_duallist_from_response(self, response):
        """Utility to get dual list object from response."""
        data = response.data
        self.assertIsNotNone(data)
        self.assertEqual(len(data), 1)
        primary_object = data[0]
        tg_mngmnt_subform_fields = primary_object.get("fields")
        self.assertIsNotNone(tg_mngmnt_subform_fields)
        fields_len = 2
        self.assertEqual(len(tg_mngmnt_subform_fields), fields_len)
        for element in tg_mngmnt_subform_fields:
            component_name = element.get("component")
            if component_name == f'{"dual-list-select"}':
                return element

    def test_get_settings_tag_enabled(self):
        """Test that a GET settings call returns expected format."""
        test_matrix = [
            {"handler": OCPTagQueryHandler, "view": OCPTagView, "name": "openshift", "label": "OpenShift labels"},
            {"handler": AWSTagQueryHandler, "view": AWSTagView, "name": "aws", "label": "Amazon Web Services tags"},
            {"handler": AzureTagQueryHandler, "view": AzureTagView, "name": "azure", "label": "Azure tags"},
            {"handler": GCPTagQueryHandler, "view": GCPTagView, "name": "gcp", "label": "Google Cloud Platform tags"},
        ]

        response = self.get_settings()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        duallist = self.get_duallist_from_response(response)
        for test in test_matrix:
            children = []
            for option in duallist.get("options"):
                if option.get("label") == test.get("label"):
                    children = option.get("children")

            all_key_values = [key_obj.get("label") for key_obj in children]
            url = (
                "?filter[time_scope_units]=month&filter[time_scope_value]=-1"
                "&filter[resolution]=monthly&key_only=True&filter[enabled]=True"
            )
            query_params = self.mocked_query_params(url, test.get("view"))
            handler = test.get("handler")(query_params)
            query_output = handler.execute_query()
            tag = query_output.get("data")[0]
            self.assertIn(tag, all_key_values)

    def test_post_settings_ocp_tag_enabled(self):
        """Test setting OCP tags as enabled."""
        test_matrix = [
            {"handler": OCPTagQueryHandler, "view": OCPTagView, "name": "openshift", "label": "OpenShift labels"},
            {"handler": AWSTagQueryHandler, "view": AWSTagView, "name": "aws", "label": "Amazon Web Services tags"},
            {"handler": AzureTagQueryHandler, "view": AzureTagView, "name": "azure", "label": "Azure tags"},
        ]
        for test in test_matrix:
            url = (
                "?filter[time_scope_units]=month&filter[time_scope_value]=-1"
                "&filter[resolution]=monthly&key_only=True&filter[enabled]=True"
            )
            query_params = self.mocked_query_params(url, test.get("view"))
            handler = test.get("handler")(query_params)
            query_output = handler.execute_query()
            tag = "".join([test.get("name"), "-", query_output.get("data")[0]])

            body = {"api": {"settings": {"tag-management": {test.get("name"): {"enabled": [tag]}}}}}
            response = self.post_settings(body)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            response = self.get_settings()
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            duallist = self.get_duallist_from_response(response)
            enabled = duallist.get("initialValue")

            self.assertIn(tag, enabled)
            tag = query_output.get("data")[1]

            body = {"api": {"settings": {"tag-management": {test.get("name"): {"enabled": [tag]}}}}}
            response = self.post_settings(body)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            response = self.get_settings()
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            duallist = self.get_duallist_from_response(response)
            enabled = duallist.get("initialValue")
            self.assertIn(tag, enabled)

    def test_post_settings_ocp_tag_disabled(self):
        """Test setting OCP tags get disabled."""
        test_matrix = [
            {"handler": OCPTagQueryHandler, "view": OCPTagView, "name": "openshift", "label": "OpenShift labels"},
            {"handler": AWSTagQueryHandler, "view": AWSTagView, "name": "aws", "label": "Amazon Web Services tags"},
            {"handler": AzureTagQueryHandler, "view": AzureTagView, "name": "azure", "label": "Azure tags"},
        ]
        for test in test_matrix:
            if test["handler"] == AzureTagQueryHandler:
                # Azure has been a difficult case. Make sure that one of the tags is
                # disabled
                azure_tag = get_model("reporting_azureenabledtagkeys").objects.first()
                if azure_tag:
                    azure_tag.delete()
            url = (
                "?filter[time_scope_units]=month&filter[time_scope_value]=-2"
                "&filter[resolution]=monthly&key_only=True&filter[enabled]=False"
            )
            query_params = self.mocked_query_params(url, test.get("view"))
            handler = test.get("handler")(query_params)
            query_output = handler.execute_query()
            tag = query_output.get("data")[0]

            # Init test with enabled tag
            body = {"api": {"settings": {"tag-management": {test.get("name"): {"enabled": [tag]}}}}}
            response = self.post_settings(body)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            # Verify that disabling tags for a different source type does not clear openshift tags.
            opposite_name = "openshift"
            if test.get("name") == "openshift":
                opposite_name = "aws"
            body = {"api": {"settings": {"tag-management": {opposite_name: {"enabled": []}}}}}
            response = self.post_settings(body)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            response = self.get_settings()
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            duallist = self.get_duallist_from_response(response)
            enabled = duallist.get("initialValue")
            self.assertIn(test.get("name") + "-" + tag, enabled)
            body = {"api": {"settings": {"tag-management": {test.get("name"): {}}}}}
            response = self.post_settings(body)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            response = self.get_settings()
            expected = [
                "azure-app",
                "azure-environment",
                "azure-storageclass",
                "azure-version",
                "gcp-test_storage_key",
                "gcp-vm_key_proj2",
            ]
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            duallist = self.get_duallist_from_response(response)
            enabled = duallist.get("initialValue")
            self.assertEqual(expected, enabled)

            # DDF will give an empty dictionary when disabling all
            body = {"api": {"settings": {"tag-management": {test.get("name"): {}}}}}
            response = self.post_settings(body)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            response = self.get_settings()
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            duallist = self.get_duallist_from_response(response)
            enabled = duallist.get("initialValue")
            self.assertEqual([], enabled)

    def test_post_settings_ocp_tag_enabled_invalid_tag(self):
        """Test setting OCP tags as enabled with invalid tag key."""
        tag = "Invalid_tag_key_test"

        body = {"api": {"settings": {"tag-management": {"openshift": {"enabled": [tag]}}}}}
        response = self.post_settings(body)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_settings_bad_format(self):
        """Test settings with bad post format."""
        body = []
        response = self.post_settings(body)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
