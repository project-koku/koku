#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AWS Report views."""
import copy
import logging

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_csv.renderers import CSVRenderer

from api.iam.test.iam_test_case import IamTestCase
from api.iam.test.iam_test_case import RbacPermissions
from api.report.view import _convert_units
from api.utils import DateHelper
from api.utils import UnitConverter

LOG = logging.getLogger(__name__)


def _calculate_accounts_and_subous(data):
    """Returns list of accounts and sub_ous in the input data."""
    accounts_and_subous = []
    if data:
        for day in data:
            org_entities = day.get("org_entities", [])
            for dictionary in org_entities:
                for key, value in dictionary.items():
                    if key == "id":
                        accounts_and_subous.append(value)
    return list(set(accounts_and_subous))


class AWSReportViewTest(IamTestCase):
    """Tests the report view."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.client = APIClient()
        self.dh = DateHelper()
        self.ten_days_ago = self.dh.n_days_ago(self.dh.today, 9)

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

    @RbacPermissions(
        {
            "aws.account": {"read": ["*"]},
            "aws.organizational_unit": {"read": ["R_001", "OU_001", "OU_002", "OU_003", "OU_004", "OU_005"]},
        }
    )
    def test_execute_query_csv_w_multi_group_by_rbac_explicit_access(self):
        """Test that a csv will be returned with an account group-by AND an org_unit group-by."""
        qs = "?group_by[org_unit_id]=OU_001&group_by[account]=9999999999990"
        url = reverse("reports-aws-costs") + qs
        client = APIClient(HTTP_ACCEPT="text/csv")
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.accepted_media_type, "text/csv")
        self.assertIsInstance(response.accepted_renderer, CSVRenderer)
        self.assertTrue(0 < len(response.data))

    @RbacPermissions(
        {
            "aws.account": {"read": ["*"]},
            "aws.organizational_unit": {"read": ["R_001", "OU_001", "OU_002", "OU_003", "OU_004", "OU_005"]},
        }
    )
    def test_execute_query_w_group_by_rbac_explicit_access(self):
        """Test that explicit access results in all accounts/orgs listed."""
        ou_to_account_subou_map = {
            "R_001": {"accounts": ["9999999999990"], "org_units": ["OU_001"]},
            "OU_001": {"accounts": ["9999999999991", "9999999999992"], "org_units": []},
            "OU_002": {"accounts": [], "org_units": ["OU_003"]},
            "OU_003": {"accounts": ["9999999999993"], "org_units": []},
            "OU_004": {"accounts": [], "org_units": []},
            "OU_005": {"accounts": [], "org_units": []},
        }
        for org_unit in list(ou_to_account_subou_map):
            qs = f"?group_by[org_unit_id]={org_unit}"
            url = reverse("reports-aws-costs") + qs
            response = self.client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            accounts_and_subous = _calculate_accounts_and_subous(response.data.get("data"))
            # These accounts are tied to this org unit inside of the
            # aws_org_tree.yml that populates the data for tests
            for account in ou_to_account_subou_map.get(org_unit).get("accounts"):
                self.assertIn(account, accounts_and_subous)
            for ou in ou_to_account_subou_map.get(org_unit).get("org_units"):
                self.assertIn(ou, accounts_and_subous)

    @RbacPermissions({"aws.account": {"read": ["*"]}, "aws.organizational_unit": {"read": ["R_001"]}})
    def test_rbac_org_unit_root_node_provides_access_to_tree(self):
        """Test that total account access/restricted org results in all accounts/ accessible orgs."""
        ou_to_account_subou_map = {
            "R_001": {"accounts": ["9999999999990"], "org_units": ["OU_001", "OU_002"]},
            "OU_001": {"accounts": ["9999999999991", "9999999999992"], "org_units": ["OU_005"]},
            "OU_002": {"accounts": [], "org_units": ["OU_003"]},
            "OU_003": {"accounts": ["9999999999993"], "org_units": []},
            "OU_005": {"accounts": [], "org_units": []},
        }
        for org_unit in list(ou_to_account_subou_map):
            qs = f"?group_by[org_unit_id]={org_unit}"
            url = reverse("reports-aws-costs") + qs
            response = self.client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            accounts_and_subous = _calculate_accounts_and_subous(response.data.get("data"))
            # These accounts are tied to this org unit inside of the
            # aws_org_tree.yml that populates the data for tests
            for account in ou_to_account_subou_map.get(org_unit).get("accounts"):
                self.assertIn(account, accounts_and_subous)
            for ou in ou_to_account_subou_map.get(org_unit).get("org_units"):
                self.assertIn(ou, accounts_and_subous)

    @RbacPermissions({"aws.account": {"read": ["*"]}, "aws.organizational_unit": {"read": ["OU_001"]}})
    def test_rbac_org_unit_limited_access(self):
        """Test that total account access/restricted org results in all accounts/ accessible orgs."""
        ou_to_account_subou_map = {
            "OU_001": {"accounts": ["9999999999991", "9999999999992"], "org_units": ["OU_005"]},
            "OU_005": {"accounts": [], "org_units": []},
        }
        for org_unit in list(ou_to_account_subou_map):
            qs = f"?group_by[org_unit_id]={org_unit}"
            url = reverse("reports-aws-costs") + qs
            response = self.client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            accounts_and_subous = _calculate_accounts_and_subous(response.data.get("data"))
            for account in ou_to_account_subou_map.get(org_unit).get("accounts"):
                self.assertIn(account, accounts_and_subous)
            for ou in ou_to_account_subou_map.get(org_unit).get("org_units"):
                self.assertIn(ou, accounts_and_subous)

        access_denied_list = ["R_001", "OU_002", "OU_003"]
        for ou_id in access_denied_list:
            qs = f"?group_by[org_unit_id]={ou_id}"
            url = reverse("reports-aws-costs") + qs
            response = self.client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @RbacPermissions({"aws.account": {"read": ["*"]}, "aws.organizational_unit": {"read": ["R_001"]}})
    def test_rbac_org_unit_root_node_multiple_group_by(self):
        """Test that total account access/restricted org results in all accounts/ accessible orgs."""
        expected_combined_accounts = ["9999999999991", "9999999999992"]
        expected_combined_ous = ["OU_003", "OU_005"]
        qs = "?group_by[or:org_unit_id]=OU_001&group_by[or:org_unit_id]=OU_002"
        url = reverse("reports-aws-costs") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        accounts_and_subous = _calculate_accounts_and_subous(response.data.get("data"))
        # These accounts are tied to this org unit inside of the
        # aws_org_tree.yml that populates the data for tests
        for account in expected_combined_accounts:
            self.assertIn(account, accounts_and_subous)
        for ou in expected_combined_ous:
            self.assertIn(ou, accounts_and_subous)

    @RbacPermissions({"aws.account": {"read": ["*"]}, "aws.organizational_unit": {"read": ["OU_001", "OU_003"]}})
    def test_rbac_org_unit_limited_access_multiple_group_by(self):
        """Test that total account access/restricted org results in all accounts/ accessible orgs."""
        expected_combined_accounts = ["9999999999991", "9999999999992", "9999999999993"]
        expected_combined_ous = ["OU_005"]
        qs = "?group_by[or:org_unit_id]=OU_001&group_by[or:org_unit_id]=OU_003"
        url = reverse("reports-aws-costs") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        accounts_and_subous = _calculate_accounts_and_subous(response.data.get("data"))
        # These accounts are tied to this org unit inside of the
        # aws_org_tree.yml that populates the data for tests
        for account in expected_combined_accounts:
            self.assertIn(account, accounts_and_subous)
        for ou in expected_combined_ous:
            self.assertIn(ou, accounts_and_subous)

    @RbacPermissions({"aws.account": {"read": ["*"]}, "aws.organizational_unit": {"read": ["OU_001", "OU_003"]}})
    def test_rbac_org_unit_access_denied_with_multiple_group_by(self):
        """Test that total account access/restricted org results in all accounts/ accessible orgs."""
        qs = "?group_by[or:org_unit_id]=OU_001&group_by[or:org_unit_id]=OU_002"
        url = reverse("reports-aws-costs") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @RbacPermissions({"aws.account": {"read": ["*"]}, "aws.organizational_unit": {"read": ["*"]}})
    def test_execute_query_w_group_by_rbac_no_restrictions(self):
        """Test that total access results in all accounts and orgs."""
        ou_to_account_subou_map = {
            "R_001": {"accounts": ["9999999999990"], "org_units": ["OU_001"]},
            "OU_001": {"accounts": ["9999999999991", "9999999999992"], "org_units": []},
            "OU_002": {"accounts": [], "org_units": ["OU_003"]},
            "OU_003": {"accounts": ["9999999999993"], "org_units": []},
            "OU_004": {"accounts": [], "org_units": []},
            "OU_005": {"accounts": [], "org_units": []},
        }
        for org_unit in list(ou_to_account_subou_map):
            qs = f"?group_by[org_unit_id]={org_unit}"
            url = reverse("reports-aws-costs") + qs
            response = self.client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            accounts_and_subous = _calculate_accounts_and_subous(response.data.get("data"))
            # These accounts are tied to this org unit inside of the
            # aws_org_tree.yml that populates the data for tests
            for account in ou_to_account_subou_map.get(org_unit).get("accounts"):
                self.assertIn(account, accounts_and_subous)
            for ou in ou_to_account_subou_map.get(org_unit).get("org_units"):
                self.assertIn(ou, accounts_and_subous)

            # test filter
            qs = f"?filter[org_unit_id]={org_unit}"
            url = reverse("reports-aws-costs") + qs
            response = self.client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions({"aws.account": {"read": ["9999999999990"]}, "aws.organizational_unit": {"read": ["*"]}})
    def test_execute_query_w_group_by_rbac_account_restrictions(self):
        """Test that restricted access results in the accessible orgs/accounts."""
        ou_to_account_subou_map = {"R_001": {"accounts": ["9999999999990"], "org_units": []}}
        # since we only have access to the account directly under root - no org units will show up
        # because they only show up when they have costs associated with the accounts under them
        for org_unit in list(ou_to_account_subou_map):
            qs = f"?group_by[org_unit_id]={org_unit}"
            url = reverse("reports-aws-costs") + qs
            response = self.client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            accounts_and_subous = _calculate_accounts_and_subous(response.data.get("data"))
            # These accounts are tied to this org unit inside of the
            # aws_org_tree.yml that populates the data for tests
            for account in ou_to_account_subou_map.get(org_unit).get("accounts"):
                self.assertIn(account, accounts_and_subous)
            for ou in ou_to_account_subou_map.get(org_unit).get("org_units"):
                self.assertIn(ou, accounts_and_subous)

    @RbacPermissions({"aws.account": {"read": ["9999999999991"]}, "aws.organizational_unit": {"read": ["*"]}})
    def test_execute_query_w_group_by_rbac_restriction(self):
        """Test limited access results in only the account that the user can see."""
        qs = "group_by[org_unit_id]=OU_001"
        url = reverse("reports-aws-costs") + "?" + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        accounts_and_subous = _calculate_accounts_and_subous(response.data.get("data"))
        self.assertEqual(accounts_and_subous, ["9999999999991"])

    @RbacPermissions({"aws.account": {"read": ["fakeaccount"]}, "aws.organizational_unit": {"read": ["fake_org"]}})
    def test_execute_query_w_group_by_rbac_no_accounts_or_orgs(self):
        """Test that no access to relevant results in a 403."""
        for org in ["R_001", "OU_001", "OU_002", "OU_003", "OU_004", "OU_005"]:
            qs = f"?group_by[org_unit_id]={org}"
            url = reverse("reports-aws-costs") + qs
            response = self.client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            # test filters
            qs = f"?filter[org_unit_id]={org}"
            url = reverse("reports-aws-costs") + qs
            response = self.client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_group_by_org_unit_non_costs_reports(self):
        """Test that grouping by org unit on non costs reports raises a validation error."""
        qs = "?group_by[org_unit_id]=*"
        url = reverse("reports-aws-storage") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_group_by_org_unit_wildcard_costs_reports(self):
        """Test that grouping by org unit with a wildcard raises a validation error."""
        qs = "?group_by[org_unit_id]=*"
        url = reverse("reports-aws-costs") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ou_group_by_default_pagination(self):
        """Test that the default pagination works."""
        qs = "?group_by[org_unit_id]=R_001&filter[resolution]=monthly&filter[time_scope_value]=-1&filter[time_scope_units]=month"  # noqa: E501
        url = reverse("reports-aws-costs") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response_data = response.json()
        data = response_data.get("data", [])
        meta = response_data.get("meta", {})
        count = meta.get("count", 0)

        self.assertIn("total", meta)
        self.assertIn("filter", meta)
        self.assertIn("count", meta)

        for entry in data:
            org_entities = entry.get("org_entities", [])
            self.assertEqual(len(org_entities), count)

    def test_ou_group_by_filter_limit_offset_pagination(self):
        """Test that the ranked group pagination works."""
        limit = 1
        offset = 0

        qs = f"?group_by[org_unit_id]=R_001&filter[resolution]=monthly&filter[time_scope_value]=-1&filter[time_scope_units]=month&filter[limit]={limit}&filter[offset]={offset}"  # noqa: E501
        url = reverse("reports-aws-costs") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response_data = response.json()
        data = response_data.get("data", [])
        meta = response_data.get("meta", {})
        count = meta.get("count", 0)

        self.assertIn("total", meta)
        self.assertIn("filter", meta)
        self.assertIn("count", meta)

        for entry in data:
            org_entities = entry.get("org_entities", [])
            if limit + offset > count:
                self.assertEqual(len(org_entities), max((count - offset), 0))
            else:
                self.assertEqual(len(org_entities), limit)

    def test_ou_group_by_filter_limit_high_offset_pagination(self):
        """Test that high offset pagination works."""
        limit = 1
        offset = 10

        qs = f"?group_by[org_unit_id]=R_001&filter[resolution]=monthly&filter[time_scope_value]=-1&filter[time_scope_units]=month&filter[limit]={limit}&filter[offset]={offset}"  # noqa: E501
        url = reverse("reports-aws-costs") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response_data = response.json()
        data = response_data.get("data", [])
        meta = response_data.get("meta", {})
        count = meta.get("count", 0)

        self.assertIn("total", meta)
        self.assertIn("filter", meta)
        self.assertIn("count", meta)

        for entry in data:
            org_entities = entry.get("org_entities", [])
            if limit + offset > count:
                self.assertEqual(len(org_entities), max((count - offset), 0))
            else:
                self.assertEqual(len(org_entities), limit)

    def test_group_by_org_unit_order_by_cost_asc(self):
        """Test that ordering by cost=asc works as expected"""
        qs = "?group_by[org_unit_id]=R_001&order_by[cost]=asc"
        url = reverse("reports-aws-costs") + qs
        response = self.client.get(url, **self.headers)
        data = response.data.get("data", [])
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Now we need to loop through the results and make sure that
        # the org units are in asc order according to cost
        for entry in data:
            org_entities = entry.get("org_entities", [])
            sorted_org_entities = copy.deepcopy(org_entities)
            sorted_org_entities.sort(key=lambda e: e["values"][0]["cost"]["total"]["value"], reverse=False)
            self.assertEqual(org_entities, sorted_org_entities)

    def test_group_by_org_unit_order_by_cost_desc(self):
        """Test that ordering by cost=descworks as expected"""
        qs = "?group_by[org_unit_id]=R_001&order_by[cost]=desc"
        url = reverse("reports-aws-costs") + qs
        response = self.client.get(url, **self.headers)
        data = response.data.get("data")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Now we need to loop through the results and make sure that
        # the org units are in desc order according to cost
        for entry in data:
            org_entities = entry.get("org_entities", [])
            sorted_org_entities = copy.deepcopy(org_entities)
            sorted_org_entities.sort(key=lambda e: e["values"][0]["cost"]["total"]["value"], reverse=True)
            self.assertEqual(org_entities, sorted_org_entities)

    def test_multiple_and_group_by_org_unit_bad_request(self):
        """Test that grouping by org unit on non costs reports raises a validation error."""
        qs = "?group_by[org_unit_id]=R_001&group_by[org_unit_id]=OU_001"
        url = reverse("reports-aws-costs") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_multiple_mixed_group_by_org_unit_bad_request(self):
        """Test that grouping by org unit on non costs reports raises a validation error."""
        qs = "?group_by[org_unit_id]=R_001&group_by[or:org_unit_id]=OU_001"
        url = reverse("reports-aws-costs") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_group_by_org_unit_or_wildcard_bad_request(self):
        """Test that grouping by org unit on non costs reports raises a validation error."""
        qs = "?group_by[or:org_unit_id]=*"
        url = reverse("reports-aws-costs") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_group_by_org_unit_id_and_wildcard_region(self):
        """Test multiple group by with org unit id and region."""
        # The ui team uses these to populate graphs
        qs = "?group_by[or:org_unit_id]=R_001&group_by[region]=*"
        url = reverse("reports-aws-costs") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_group_by_org_unit_id_and_wildcard_account(self):
        """Test multiple group by with org unit id and account."""
        qs = "?group_by[or:org_unit_id]=R_001&group_by[account]=*"
        # The ui team uses these to populate graphs
        url = reverse("reports-aws-costs") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_order_by_delta(self):
        """Test that the order_by delta with pagination does not error."""
        qs_list = [
            "?filter[limit]=5&filter[offset]=0&order_by[delta]=asc&delta=usage",
            "?order_by[delta]=asc&delta=usage",
        ]
        for qs in qs_list:
            url = reverse("reports-aws-instance-type") + qs
            response = self.client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            response_data = response.json()
            data = response_data.get("data", [])
            meta = response_data.get("meta", {})

            self.assertIn("total", meta)
            self.assertIn("filter", meta)
            self.assertIn("count", meta)

            compared_deltas = False
            for day in data:
                previous_delta = None
                for instance_type in day.get("instance_types", []):
                    values = instance_type.get("values", [])
                    if values:
                        current_delta = values[0].get("delta_value")
                        if previous_delta:
                            self.assertLessEqual(previous_delta, current_delta)
                            compared_deltas = True
                            previous_delta = current_delta
                        else:
                            previous_delta = current_delta
            self.assertTrue(compared_deltas)

    def test_others_count(self):
        """Test that the others count works with a small limit."""
        qs_list = ["?filter[limit]=1"]
        for qs in qs_list:
            url = reverse("reports-aws-instance-type") + qs
            response = self.client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            response_data = response.json()
            meta = response_data.get("meta", {})
            self.assertNotEqual(meta.get("others"), 0)

    def test_order_by_delta_no_delta(self):
        """Test that the order_by delta with no delta passed in triggers 400."""
        qs_list = ["?filter[limit]=5&filter[offset]=0&order_by[delta]=asc", "?order_by[delta]=asc"]
        for qs in qs_list:
            url = reverse("reports-aws-instance-type") + qs
            response = self.client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_start_end_parameters_monthly_resolution(self):
        """Test that a validation error is raised for monthly resolution with start/end parameters."""
        qs_list = ["?start_date=2021-04-01&end_date=2021-04-13&filter[resolution]=monthly"]
        for qs in qs_list:
            url = reverse("reports-aws-instance-type") + qs
            response = self.client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_start_end_parameters_with_delta(self):
        """Test that a validation error is raised for monthly resolution with start/end parameters."""
        qs_list = [
            "?start_date=2021-04-01&end_date=2021-04-13&delta=usage",
            "?start_date=2021-04-01&delta=usage",
            "?end_date=2021-04-13&delta=usage",
        ]
        for qs in qs_list:
            url = reverse("reports-aws-instance-type") + qs
            response = self.client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
