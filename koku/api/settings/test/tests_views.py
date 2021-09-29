#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Settings views."""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
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
            {"name": "openshift", "label": "OpenShift labels"},
            {"name": "aws", "label": "Amazon Web Services tags"},
            {"name": "azure", "label": "Azure tags"},
            {"name": "gcp", "label": "Google Cloud Platform tags"},
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

    def test_post_settings_tag_enabled(self):
        """Test settings POST calls change enabled tags"""
        test_matrix = [
            {
                "name": "test01",
                "enabled_tags": [
                    "aws-app",
                    "aws-environment",
                    "openshift-environment",
                    "openshift-storageclass",
                    "openshift-version",
                ],
            },
            {"name": "test02", "enabled_tags": ["aws-environment", "openshift-storageclass", "openshift-version"]},
            {"name": "test03", "enabled_tags": ["openshift-storageclass", "openshift-version"]},
            {"name": "test04", "enabled_tags": ["openshift-version"]},
        ]

        for test in test_matrix:
            enabled_tags = test.get("enabled_tags")

            body = {"api": {"settings": {"tag-management": {"enabled": enabled_tags}}}}
            response = self.post_settings(body)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            response = self.get_settings()
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            duallist = self.get_duallist_from_response(response)
            resp_enabled_tags = duallist.get("initialValue")
            self.assertEqual(len(resp_enabled_tags), len(enabled_tags))

            for tag in enabled_tags:
                self.assertIn(tag, resp_enabled_tags)

    def test_post_settings_ocp_tag_enabled_invalid_tag(self):
        """Test setting OCP tags as enabled with invalid tag key."""
        tag = "gcp-Invalid_tag_key_test"

        body = {"api": {"settings": {"tag-management": {"enabled": [tag]}}}}
        response = self.post_settings(body)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_settings_bad_format(self):
        """Test settings with bad post format."""
        body = []
        response = self.post_settings(body)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
