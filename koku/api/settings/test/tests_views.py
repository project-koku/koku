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
        fields_len = 3
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
        all_enabled_tags = duallist.get("initialValue")

        for test in test_matrix:
            available = []
            enabled_tags = []

            # get available tags
            for option in duallist.get("options"):
                if option.get("label") == test.get("label"):
                    children = option.get("children")
                    available = [key_obj.get("label") for key_obj in children]

            for enabled in all_enabled_tags:
                if enabled.split("-")[0] == test.get("name"):
                    enabled_tags.append(enabled.split("-")[1])
                    self.assertIn(enabled.split("-")[1], available)

    # @TODO: Additional tests needed
