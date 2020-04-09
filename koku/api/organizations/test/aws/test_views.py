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
from tenant_schemas.utils import schema_context

from api.iam.test.iam_test_case import IamTestCase
from masu.external.accounts.hierarchy.aws.aws_org_unit_crawler import AWSOrgUnitCrawler
from masu.test.external.downloader.aws import fake_arn


class AWSReportViewTest(IamTestCase):
    """Tests the report view."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.account = {
            "authentication": fake_arn(service="iam", generate_account_id=True),
            "schema_name": self.schema_name,
        }
        self.data_tree = {
            "r-id": {"data": [{"name": "root", "id": "r-id", "path": "r-id"}], "account_num": 0},
            "big_ou0": {
                "data": [
                    {"name": "big_ou", "id": "big_ou0", "path": "r-id&big_ou0"},
                    {"name": "big_ou", "id": "big_ou0", "path": "r-id&big_ou0", "account": "0"},
                    {"name": "big_ou", "id": "big_ou0", "path": "r-id&big_ou0", "account": "1"},
                ],
                "account_num": 2,
            },
            "sub_ou0": {
                "data": [{"name": "sub_ou", "id": "sub_ou0", "path": "r-id&big_ou0&sub_ou0"}],
                "account_num": 0,
            },
        }
        self.url = reverse("aws-org-unit")

    def _populate_test_db(self, tree):
        """Populates the test database with org unit tree information."""
        unit_crawler = AWSOrgUnitCrawler(self.account)
        with schema_context(self.schema_name):
            for _, data_info in tree.items():
                for insert_data in data_info["data"]:
                    if insert_data.get("account"):
                        unit_crawler._save_aws_org_method(
                            insert_data["name"], insert_data["id"], insert_data["path"], insert_data["account"]
                        )
                    else:
                        unit_crawler._save_aws_org_method(insert_data["name"], insert_data["id"], insert_data["path"])

    def test_execute(self):
        """Test that our url endpoint returns 200."""
        self._populate_test_db(self.data_tree)
        response = self.client.get(self.url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result = response.data.get("data")
        self.assertIsNotNone(result)
        self.assertEqual(len(result), len(self.data_tree))
        for ou in result:
            accounts = ou.get("accounts")
            ou_id = ou.get("org_unit_id")
            path = ou.get("org_unit_path")
            name = ou.get("org_unit_name")
            self.assertIsNotNone(accounts)
            self.assertIsNotNone(ou_id)
            self.assertEqual(len(accounts), self.data_tree[ou_id]["account_num"])
            self.assertEqual(path, self.data_tree[ou_id]["data"][0]["path"])
            self.assertEqual(name, self.data_tree[ou_id]["data"][0]["name"])

    def test_execute_with_filter(self):
        """Test filter with time intervals."""
        del self.data_tree["r-id"]
        del self.data_tree["sub_ou0"]
        self._populate_test_db(self.data_tree)
        url = self.url + "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_time_filters_errors(self):
        """Test time filter errors with time intervals"""
        self._populate_test_db(self.data_tree)
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
