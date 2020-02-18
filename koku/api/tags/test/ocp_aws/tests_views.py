#
# Copyright 2018 Red Hat, Inc.
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
"""Test the OCP-on-AWS tag view."""
from urllib.parse import quote_plus
from urllib.parse import urlencode

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase


class OCPAWSTagsViewTest(IamTestCase):
    """Tests the report view."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        serializer = UserSerializer(data=self.user_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            serializer.save()

        self.test_cases = [
            {"value": "-1", "unit": "month", "resolution": "monthly"},
            {"value": "-2", "unit": "month", "resolution": "monthly"},
        ]

    def test_keys_only(self):
        """Test that tag key data is for the correct time queries."""
        for case in self.test_cases:
            url = reverse("openshift-aws-tags")
            client = APIClient()
            params = {
                "filter[resolution]": case.get("resolution"),
                "filter[time_scope_value]": case.get("value"),
                "filter[time_scope_units]": case.get("unit"),
                "key_only": True,
            }
            url = url + "?" + urlencode(params, quote_via=quote_plus)
            response = client.get(url, **self.headers)

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()

            self.assertEqual(data.get("data"), [])
            self.assertTrue(isinstance(data.get("data"), list))

    def test_tags_queries(self):
        """Test that tag data is for the correct time queries."""
        for case in self.test_cases:
            url = reverse("openshift-aws-tags")
            client = APIClient()
            params = {
                "filter[resolution]": case.get("resolution"),
                "filter[time_scope_value]": case.get("value"),
                "filter[time_scope_units]": case.get("unit"),
                "key_only": False,
            }
            url = url + "?" + urlencode(params, quote_via=quote_plus)
            response = client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()

            self.assertEqual(data.get("data"), [])
            self.assertTrue(isinstance(data.get("data"), list))
