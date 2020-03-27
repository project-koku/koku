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
"""TestCase for Cloud Account Model."""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase


class CloudAccountViewTest(IamTestCase):
    """Test Cases for CloudAccountViewSet."""

    def test_http_status_code_200_ok(self):
        """Test that /cloud_accounts endpoint returns 200 HTTP_OK."""
        url = reverse("cloud_accounts-list")
        client = APIClient()

        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_cloud_account_values(self):
        """
        Test contents of cloud account.

        Test getting the cloud accounts from the API.
        """
        url = reverse("cloud_accounts-list")
        client = APIClient()
        response = client.get(url, **self.headers).data["data"]
        actual_name = response[0].get("name", "")
        expected_name = "AWS"
        self.assertEqual(expected_name, actual_name)
        actual_value = response[0].get("value", "")
        expected_value = "589173575009"
        self.assertEqual(expected_value, actual_value)
