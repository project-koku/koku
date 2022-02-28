#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""TestCase for Cloud Account Model."""
from urllib.parse import quote_plus
from urllib.parse import urlencode

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.cloud_accounts import CLOUD_ACCOUNTS
from api.iam.test.iam_test_case import IamTestCase


class CloudAccountViewTest(IamTestCase):
    """Test Cases for CloudAccountViewSet."""

    def test_http_status_code_200_ok(self):
        """Test that /cloud_accounts endpoint returns 200 HTTP_OK."""
        url = reverse("cloud-accounts")
        client = APIClient()

        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_cloud_account_values(self):
        """
        Test contents of cloud account.

        Test getting the cloud accounts from the API.
        """
        url = reverse("cloud-accounts")
        client = APIClient()
        response = client.get(url, **self.headers).data["data"]
        actual_name = response[0].get("name", "")
        expected_name = CLOUD_ACCOUNTS[0].get("name")
        self.assertEqual(expected_name, actual_name)
        actual_value = response[0].get("value", "")
        expected_value = CLOUD_ACCOUNTS[0].get("value")
        self.assertEqual(expected_value, actual_value)

    def test_delete_cloud_accounts(self):
        """Test that DELETE call does not work for the Cloud Accounts."""
        url = reverse("cloud-accounts")
        client = APIClient()
        response = client.delete(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_limit_1_offset_1(self):
        """
        Test accessing the second element in the array.
        """
        url = reverse("cloud-accounts")
        client = APIClient()
        data = client.get(url + "?limit=1&offset=1", **self.headers).data["data"]
        if len(data) > 0:
            self.assertEqual(data[0].get("name"), CLOUD_ACCOUNTS[1].get("name"))
            self.assertEqual(1, len(data))
        else:
            self.assertFalse(data)

    def test_invalid_query_params(self):
        """
        Test invalid query parameters, for example ?limit=foo
        """
        url = reverse("cloud-accounts")
        client = APIClient()

        params = {"limit": "foo"}
        url = url + "?" + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_json_500_response(self):
        """Test that the CLOUD_ACCOUNTS constant contains the required keys"""
        required_keys = ["name", "value", "description", "updated_timestamp"]
        for cloud_account in CLOUD_ACCOUNTS:
            self.assertListEqual(list(cloud_account.keys()), required_keys)
