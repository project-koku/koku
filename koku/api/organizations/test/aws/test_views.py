#
# Copyright 2020 Red Hat, Inc.
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
"""Test the AWS Organization views."""
from django.urls import reverse
from rest_framework import status

from api.iam.test.iam_test_case import IamTestCase
from api.organizations.test.utils import GenerateOrgTestData


class AWSReportViewTest(IamTestCase):
    """Tests the organizations view."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.generate_data = GenerateOrgTestData(self.schema_name)
        self.url = reverse("aws-org-unit")

    def test_execute(self):
        """Test that our url endpoint returns 200."""
        expected = self.generate_data.insert_data()
        response = self.client.get(self.url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result = response.data.get("data")
        self.assertIsNotNone(result)
        self.assertEqual(len(result), len(expected.keys()))
        for ou in result:
            accounts = ou.get("accounts")
            ou_id = ou.get("org_unit_id")
            path = ou.get("org_unit_path")
            name = ou.get("org_unit_name")
            self.assertIsNotNone(accounts)
            self.assertIsNotNone(ou_id)
            self.assertEqual(len(accounts), expected[ou_id]["account_num"])
            self.assertEqual(path, expected[ou_id]["data"][0]["path"])
            self.assertEqual(name, expected[ou_id]["data"][0]["ou"]["Name"])

    def test_execute_with_filter(self):
        """Test filter with time intervals."""
        expected = self.generate_data.insert_data()
        url = self.url + "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data.get("data")), len(expected))

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
        expected = f"Unsupported parameter or invalid value"
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
        """Test that you can filter by org_id"""
        metadata = self.generate_data.insert_data()
        expected_org_id = list(metadata)[0]
        url = self.url + f"?filter[org_id]={expected_org_id}"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data.get("data"))
        self.assertEqual(len(response.data.get("data")), 1)
        data_row = response.data.get("data")[0]
        self.assertEqual(data_row["org_unit_id"], expected_org_id)

    def test_filter_by_or_org_id_filter(self):
        """Test that you can filter by org_id"""
        metadata = self.generate_data.insert_data()
        org_id_0 = list(metadata)[0]
        org_id_1 = list(metadata)[1]
        url = self.url + f"?filter[or:org_id]={org_id_0}&filter[or:org_id]={org_id_1}"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data.get("data"))
        self.assertEqual(len(response.data.get("data")), 2)
        expected_org_ids = [org_id_0, org_id_1]
        for data_row in response.data.get("data"):
            self.assertIn(data_row["org_unit_id"], expected_org_ids)

    def test_filter_by_and_org_id_filter(self):
        """Test that you can filter by org_id"""
        metadata = self.generate_data.insert_data()
        org_id_0 = list(metadata)[0]
        org_id_1 = list(metadata)[1]
        url = self.url + f"?filter[and:org_id]={org_id_0}&filter[and:org_id]={org_id_1}"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data.get("data"))
        self.assertEqual(len(response.data.get("data")), 0)
