#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Organization views."""
from django.test import RequestFactory
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_csv.renderers import CSVRenderer

from api.common.pagination import ReportPagination
from api.common.pagination import ReportRankedPagination
from api.iam.test.iam_test_case import IamTestCase
from api.iam.test.iam_test_case import RbacPermissions
from api.report.view import get_paginator


def _calculate_accounts_and_subous(data):
    """Returns list of accounts and sub_ous in the input data."""
    accounts = []
    sub_ous = []
    if data:
        for dictionary in data:
            if "org_unit_id" in dictionary.keys():
                sub_ou = dictionary["org_unit_id"]
                sub_ous.append(sub_ou)
            if "accounts" in dictionary.keys():
                accounts_list = dictionary["accounts"]
                accounts += accounts_list
            if "sub_orgs" in dictionary.keys():
                sub_orgs = dictionary["sub_orgs"]
                sub_ous += sub_orgs
    return (list(set(accounts)), list(set(sub_ous)))


class OrganizationsViewTest(IamTestCase):
    """Tests the organizations view."""

    ENDPOINTS = ["aws-org-unit"]

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.client = APIClient()
        self.factory = RequestFactory()

    def test_endpoint_view(self):
        """Test endpoint runs with a customer owner."""
        for endpoint in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                json_result = response.json()
                self.assertIsNotNone(json_result.get("data"))
                self.assertIsInstance(json_result.get("data"), list)
                self.assertTrue(len(json_result.get("data")) > 0)

    def test_endpoints_invalid_query_param(self):
        """Test endpoint runs with an invalid query param."""
        for endpoint in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                query = "group_by[invalid]=*"
                url = reverse(endpoint) + "?" + query
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_endpoint_csv(self):
        """Test CSV output of inventory endpoint reports."""
        self.client = APIClient(HTTP_ACCEPT="text/csv")
        for endpoint in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, content_type="text/csv", **self.headers)
                response.render()

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.accepted_media_type, "text/csv")
                self.assertIsInstance(response.accepted_renderer, CSVRenderer)

    def test_get_paginator_default(self):
        """Test that the standard report paginator is returned."""
        params = {}
        paginator = get_paginator(params, 0)
        self.assertIsInstance(paginator, ReportPagination)

    def test_get_paginator_for_filter_offset(self):
        """Test that the standard report paginator is returned."""
        params = {"offset": 5}
        paginator = get_paginator(params, 0)
        self.assertIsInstance(paginator, ReportRankedPagination)

    @RbacPermissions({"aws.account": {"read": ["*"]}, "aws.organizational_unit": {"read": ["R_001"]}})
    def test_endpoint_rbac_ou_restrictions_root_node(self):
        """Test limited access results in only the ous that the user can see."""
        # Note: if they have access to the root node then they should have access
        # to the entire tree.
        url = reverse("aws-org-unit")
        response = self.client.get(url, **self.headers)
        accounts, ous = _calculate_accounts_and_subous(response.data.get("data"))
        for org in ous:
            self.assertIn(org, ["R_001", "OU_001", "OU_002", "OU_003", "OU_005"])
        for account in ["account 002", "account 001", "Root A Test"]:
            self.assertIn(account, accounts)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions({"aws.account": {"read": ["*"]}, "aws.organizational_unit": {"read": ["OU_001"]}})
    def test_endpoint_rbac_ou_restrictions_child_node(self):
        """Test limited access results in only the ous that the user can see."""
        url = reverse("aws-org-unit")
        response = self.client.get(url, **self.headers)
        accounts, ous = _calculate_accounts_and_subous(response.data.get("data"))
        for org in ous:
            self.assertIn(org, ["OU_001", "OU_005"])
        for account in ["account 002", "account 001", "account 005"]:
            self.assertIn(account, accounts)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions({"aws.account": {"read": ["*"]}, "aws.organizational_unit": {"read": ["fake"]}})
    def test_endpoint_rbac_no_ous(self):
        """Test limited access results in only the account that the user can see."""
        url = reverse("aws-org-unit")
        response = self.client.get(url, **self.headers)
        accounts, ous = _calculate_accounts_and_subous(response.data.get("data"))
        self.assertEqual(ous, [])
        self.assertEqual(accounts, [])
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # test that filtering on a specific ou that we don't have access to results
        # in a 403 error
        qs = "?filter[org_unit_id]=OU_001"
        url = reverse("aws-org-unit") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @RbacPermissions({"aws.account": {"read": ["*"]}, "aws.organizational_unit": {"read": ["*"]}})
    def test_endpoint_no_restriction(self):
        """Test open access results in all of the accounts/orgs."""
        url = reverse("aws-org-unit")
        response = self.client.get(url, **self.headers)
        accounts, ous = _calculate_accounts_and_subous(response.data.get("data"))
        for org in ["OU_003", "R_001", "OU_002", "OU_001", "OU_005"]:
            self.assertIn(org, ous)
        for account in ["Root A Test", "account 003", "account 002", "account 001"]:
            self.assertIn(account, accounts)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions({"aws.account": {"read": ["9999999999991787878"]}, "aws.organizational_unit": {"read": ["*"]}})
    def test_endpoint_account_restriction(self):
        """Test restricted account access results in no accounts but all orgs."""
        url = reverse("aws-org-unit")
        response = self.client.get(url, **self.headers)
        accounts, ous = _calculate_accounts_and_subous(response.data.get("data"))
        self.assertEqual(accounts, [])
        for org in ["OU_003", "R_001", "OU_002", "OU_001", "OU_005"]:
            self.assertIn(org, ous)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
