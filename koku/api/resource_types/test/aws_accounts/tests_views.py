#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Resource Types views for aws accounts endpoint."""
from django.urls import reverse
from rest_framework import status

from api.iam.test.iam_test_case import RbacPermissions
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.test import MasuTestCase


class ResourceTypesViewTestAwsAccounts(MasuTestCase):
    """Tests the resource types views."""

    @classmethod
    def setUpClass(cls):
        """Set up the customer view tests."""
        super().setUpClass()
        cls.accessor = AWSReportDBAccessor(schema=cls.schema)

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()

    @RbacPermissions({"aws.account": {"read": ["1234", "6789"]}})
    def test_rbacpermissions_aws_account_data(self):
        """Test that AWS endpoints accept valid AWS permissions."""
        url = reverse("aws-accounts")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(json_result.get("data"), [])

    @RbacPermissions({"aws.account": {"read": ["*"]}})
    def test_aws_accounts_ocp_view(self):
        """Test endpoint runs with a customer owner."""
        qs = "?openshift=true"
        url = reverse("aws-accounts") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
