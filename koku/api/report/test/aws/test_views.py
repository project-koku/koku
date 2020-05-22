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
"""Test the AWS Report views."""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.iam.test.iam_test_case import RbacPermissions
from api.report.view import _convert_units
from api.utils import UnitConverter


def _calculate_accounts(data):
    """Returns list of accounts in the input data."""
    accounts = []
    for dictionary in data:
        for _, value in dictionary.items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        if "account" in item.keys():
                            account = item["account"]
                            accounts.append(account)
    return list(set(accounts))


class AWSReportViewTest(IamTestCase):
    """Tests the report view."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.client = APIClient()

        self.report = {
            "group_by": {"account": ["*"]},
            "filter": {
                "resolution": "monthly",
                "time_scope_value": -1,
                "time_scope_units": "month",
                "resource_scope": [],
            },
            "data": [
                {
                    "date": "2018-07",
                    "accounts": [
                        {
                            "account": "4418636104713",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "account": "4418636104713",
                                    "total": 1826.74238146924,
                                }
                            ],
                        },
                        {
                            "account": "8577742690384",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "account": "8577742690384",
                                    "total": 1137.74036198065,
                                }
                            ],
                        },
                        {
                            "account": "3474227945050",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "account": "3474227945050",
                                    "total": 1045.80659412797,
                                }
                            ],
                        },
                        {
                            "account": "7249815104968",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "account": "7249815104968",
                                    "total": 807.326470618818,
                                }
                            ],
                        },
                        {
                            "account": "9420673783214",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "account": "9420673783214",
                                    "total": 658.306642830709,
                                }
                            ],
                        },
                    ],
                }
            ],
            "total": {"value": 5475.922451027388, "units": "GB-Mo"},
        }

    def test_execute_query_w_delta_total(self):
        """Test that delta=total returns deltas."""
        qs = "delta=cost"
        url = reverse("reports-aws-costs") + "?" + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_execute_query_w_delta_bad_choice(self):
        """Test invalid delta value."""
        bad_delta = "Invalid"
        expected = f'"{bad_delta}" is not a valid choice.'
        qs = f"group_by[account]=*&filter[limit]=2&delta={bad_delta}"
        url = reverse("reports-aws-costs") + "?" + qs

        response = self.client.get(url, **self.headers)
        result = str(response.data.get("delta")[0])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(result, expected)

    def test_convert_units_success(self):
        """Test unit conversion succeeds."""
        converter = UnitConverter()
        to_unit = "byte"
        expected_unit = f"{to_unit}-Mo"
        report_total = self.report.get("total", {}).get("value")

        result = _convert_units(converter, self.report, to_unit)
        result_unit = result.get("total", {}).get("units")
        result_total = result.get("total", {}).get("value")

        self.assertEqual(expected_unit, result_unit)
        self.assertEqual(report_total * 1e9, result_total)

    def test_convert_units_list(self):
        """Test that the list check is hit."""
        converter = UnitConverter()
        to_unit = "byte"
        expected_unit = f"{to_unit}-Mo"
        report_total = self.report.get("total", {}).get("value")

        report = [self.report]
        result = _convert_units(converter, report, to_unit)
        result_unit = result[0].get("total", {}).get("units")
        result_total = result[0].get("total", {}).get("value")

        self.assertEqual(expected_unit, result_unit)
        self.assertEqual(report_total * 1e9, result_total)

    def test_convert_units_total_not_dict(self):
        """Test that the total not dict block is hit."""
        converter = UnitConverter()
        to_unit = "byte"
        expected_unit = f"{to_unit}-Mo"

        report = self.report["data"][0]["accounts"][0]["values"][0]
        report_total = report.get("total")
        result = _convert_units(converter, report, to_unit)
        result_unit = result.get("units")
        result_total = result.get("total")

        self.assertEqual(expected_unit, result_unit)
        self.assertEqual(report_total * 1e9, result_total)

    @RbacPermissions({"aws.account": {"read": ["*"]}})
    def test_execute_query_w_group_by_rbac_no_restriction(self):
        """Test that total access results in all accounts associated with org_unit_id."""
        qs = "group_by[org_unit_id]=OU_001"
        url = reverse("reports-aws-costs") + "?" + qs
        response = self.client.get(url, **self.headers)
        accounts = _calculate_accounts(response.data.get("data"))
        # These accounts are tied to this org unit inside of the
        # aws_org_tree.yml that populates the data for tests
        for account in ["9999999999991", "9999999999992"]:
            self.assertIn(account, accounts)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions({"aws.account": {"read": ["9999999999991"]}})
    def test_execute_query_w_group_by_rbac_restriction(self):
        """Test limited access results in only the account that the user can see."""
        qs = "group_by[org_unit_id]=OU_001"
        url = reverse("reports-aws-costs") + "?" + qs
        response = self.client.get(url, **self.headers)
        accounts = _calculate_accounts(response.data.get("data"))
        self.assertEqual(accounts, ["9999999999991"])
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions({"aws.account": {"read": []}})
    def test_execute_query_w_group_by_rbac_no_accounts(self):
        """Test that no read access results in a 403."""
        qs = "?group_by[org_unit_id]=OU_001"
        url = reverse("reports-aws-costs") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_group_by_org_unit_non_costs_reports(self):
        """Test that grouping by org unit on non costs reports raises a validation error."""
        qs = "?group_by[org_unit_id]=*"
        url = reverse("reports-aws-storage") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
