#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AWS Organization views."""
from django.urls import reverse
from rest_framework import status

from api.iam.test.iam_test_case import IamTestCase
from reporting.provider.aws.models import AWSOrganizationalUnit


class AWSReportViewTest(IamTestCase):
    """Tests the organizations view."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.url = reverse("aws-org-unit")

    def test_execute(self):
        """Test that our url endpoint returns 200."""
        response = self.client.get(self.url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result = response.data.get("data")
        self.assertIsNotNone(result)
        self.assertNotEqual(len(result), 0)
        for ou in result:
            self.assertIsNotNone(ou.get("org_unit_id"))
            self.assertNotEqual(ou.get("accounts"), 0)
            self.assertIsNotNone(ou.get("org_unit_path"))
            self.assertIsNotNone(ou.get("org_unit_name"))

    def test_execute_with_filter(self):
        """Test filter with time intervals."""
        url = self.url + "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotEqual(len(response.data.get("data")), 0)

    def test_time_filters_errors(self):
        """Test time filter errors with time intervals"""
        url = self.url + "?filter[time_scope_units]=day&filter[time_scope_value]=-1&filter[resolution]=daily"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        url = self.url + "?filter[time_scope_units]=month&filter[time_scope_value]=-10&filter[resolution]=daily"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_execute_query_w_delta_bad_choice(self):
        """Test invalid delta value."""
        bad_delta = "Invalid"
        expected = "Unsupported parameter or invalid value"
        qs = f"?filter[limit]=2&delta={bad_delta}"
        url = self.url + qs

        response = self.client.get(url, **self.headers)
        result = str(response.data.get("delta")[0])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(result, expected)

    def test_with_limit_params(self):
        """Test the _get_group_by method with limit and group by params."""
        url = self.url + "?filter[limit]=1"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_filter_by_org_id(self):
        """Test that you can filter by org_unit_id"""
        data_info = AWSOrganizationalUnit.objects.first()
        expected_org_id = data_info.org_unit_id
        url = self.url + f"?filter[org_unit_id]={expected_org_id}"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data.get("data"))
        self.assertNotEqual(len(response.data.get("data")), 0)
        data_row = response.data.get("data")[0]
        self.assertEqual(data_row["org_unit_id"], expected_org_id)

    def test_filter_by_or_org_id_filter(self):
        """Test that you can filter by org_unit_id"""
        org_id_0 = "OU_001"
        org_id_1 = "OU_002"
        url = self.url + f"?filter[or:org_unit_id]={org_id_0}&filter[or:org_unit_id]={org_id_1}"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data.get("data"))
        self.assertEqual(len(response.data.get("data")), 2)
        expected_org_ids = [org_id_0, org_id_1]
        for data_row in response.data.get("data"):
            self.assertIn(data_row["org_unit_id"], expected_org_ids)

    def test_filter_by_and_org_id_filter(self):
        """Test that you can filter by org_unit_id"""
        org_id_0 = "OU_001"
        org_id_1 = "OU_002"
        url = self.url + f"?filter[and:org_unit_id]={org_id_0}&filter[and:org_unit_id]={org_id_1}"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data.get("data"))
        self.assertEqual(len(response.data.get("data")), 0)
        url = self.url + f"?filter[and:org_unit_id]={org_id_0}&filter[and:org_unit_id]={org_id_0}"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data.get("data"))
        self.assertEqual(len(response.data.get("data")), 1)

    def test_moved_account(self):
        """Test that the moved account only shows up in new location."""
        moved_account = "account 003"
        previous_ou = "OU_002"
        previous_url = self.url + f"?filter[org_unit_id]={previous_ou}"
        response = self.client.get(previous_url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data_row = response.data.get("data")[0]
        self.assertNotIn(moved_account, data_row.get("accounts"))

        current_ou = "OU_003"
        current_url = self.url + f"?filter[org_unit_id]={current_ou}"
        response = self.client.get(current_url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data_row = response.data.get("data")[0]
        self.assertIn(moved_account, data_row.get("accounts"))

    def test_moved_ou(self):
        """Test that the move ou only shows up in new location."""
        moved_child_ou = "OU_005"
        previous_parent = "OU_002"
        previous_url = self.url + f"?filter[org_unit_id]={previous_parent}"
        response = self.client.get(previous_url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data_row = response.data.get("data")[0]
        self.assertNotIn(moved_child_ou, data_row.get("sub_orgs"))

        new_parent = "OU_001"
        new_parent_url = self.url + f"?filter[org_unit_id]={new_parent}"
        response = self.client.get(new_parent_url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data_row = response.data.get("data")[0]
        self.assertIn(moved_child_ou, data_row.get("sub_orgs"))
