#
# Copyright 2019 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Test the Settings views."""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
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
        ocp_subform_fields = primary_object.get("fields")
        self.assertIsNotNone(ocp_subform_fields)
        self.assertEqual(len(ocp_subform_fields), 2)
        return ocp_subform_fields[1]

    def test_get_settings_ocp_tag_enabled(self):
        """Test that a GET settings call returns expected format."""
        response = self.get_settings()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        duallist = self.get_duallist_from_response(response)
        all_keys = duallist.get("options")
        self.assertIsNotNone(all_keys)
        all_key_values = [key_obj.get("value") for key_obj in all_keys]
        url = (
            "?filter[time_scope_units]=month&filter[time_scope_value]=-1"
            "&filter[resolution]=monthly&key_only=True&filter[enabled]=False"
        )
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        query_output = handler.execute_query()
        tag = query_output.get("data")[0]
        self.assertIn(tag, all_key_values)

    def test_post_settings_ocp_tag_enabled(self):
        """Test setting OCP tags as enabled."""
        url = (
            "?filter[time_scope_units]=month&filter[time_scope_value]=-1"
            "&filter[resolution]=monthly&key_only=True&filter[enabled]=False"
        )
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        query_output = handler.execute_query()
        tag = query_output.get("data")[0]

        body = {"api": {"settings": {"openshift": {"tag-management": {"enabled": [tag]}}}}}
        response = self.post_settings(body)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.get_settings()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        duallist = self.get_duallist_from_response(response)
        enabled = duallist.get("initialValue")
        self.assertIn(tag, enabled)

    def test_post_settings_ocp_tag_enabled_invalid_tag(self):
        """Test setting OCP tags as enabled with invalid tag key."""
        tag = "Invalid_tag_key_test"

        body = {"api": {"settings": {"openshift": {"tag-management": {"enabled": [tag]}}}}}
        response = self.post_settings(body)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_settings_bad_format(self):
        """Test settings with bad post format."""
        body = []
        response = self.post_settings(body)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
