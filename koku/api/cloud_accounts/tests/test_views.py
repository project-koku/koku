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

    def testCloudAccountViewSet(self):
        """Test that /cloud_accounts endpoint returns 200 HTTP_OK."""
        url = reverse("cloud-accounts")
        client = APIClient()

        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def testCloudAccounViewSetWithSecondCloudAccount(self):
        """
        Test that /cloud_account endpoint returns HTTP 200 OK.

        Adds an account to CloudAccounts.
        """
        url = reverse("cloud-accounts")
        client = APIClient()

        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def testCloudAccountPagination(self):
        """
        Test contents of cloud account.

        This test creates a cloud account with test values.
        """
        url = reverse("cloud-accounts")
        client = APIClient()
        # actual_name = response.data["data"]["name"]
        actual_name = client.get(url, **self.headers).data["data"][0]["name"]
        expected_name = "AWS"
        self.assertEqual(expected_name, actual_name)
        expected_value = client.get(url, **self.headers).data["data"][0]["value"]
        expected_value = "589173575009"
        self.assertEqual(expected_value, expected_value)
        second_page_name = client.get(url + "?limit=1&offset=1", **self.headers).data["data"][0]["name"]
        self.assertEqual("AWS_LOCAL", second_page_name)

    def testCloudAccountPagination2(self):
        """
        Test contents of cloud account.

        This test creates a cloud account with test values.
        """
        url = reverse("cloud-accounts")
        client = APIClient()
        # actual_name = response.data["data"]["name"]
        actual_name = client.get(url, **self.headers).data["data"][0]["name"]
        expected_name = "AWS"
        self.assertEqual(expected_name, actual_name)
        expected_value = client.get(url, **self.headers).data["data"][0]["value"]
        expected_value = "589173575009"
        self.assertEqual(expected_value, expected_value)
        second_page_name = client.get(url + "?offset=-1", **self.headers).data["data"][0]["name"]
        self.assertEqual("AWS", second_page_name)

    def testLimitGreaterThanTotalSize(self):
        """
        Test contents of cloud account.

        Test that when limit is greater than the number of cloud accounts, return all cloud accounts.
        """
        url = reverse("cloud-accounts")
        client = APIClient()
        actual_name = client.get(url, **self.headers).data["data"][0]["name"]
        expected_name = "AWS"
        expected_value = "589173575009"
        self.assertEqual(expected_value, expected_value)
        self.assertEqual(expected_name, actual_name)
        actual_name = client.get(url, **self.headers).data["data"][1]["name"]
        expected_name = "AWS_LOCAL"
        self.assertEqual(expected_value, expected_value)
        self.assertEqual(expected_name, actual_name)
