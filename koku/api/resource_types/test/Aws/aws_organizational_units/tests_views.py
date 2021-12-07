#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Resource Types views for aws organizational units endpoint."""
from django.urls import reverse
from rest_framework import status

from api.iam.test.iam_test_case import RbacPermissions
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.test import MasuTestCase


class ResourceTypesViewTestAwsOrganizationalUnits(MasuTestCase):
    """Tests the resource types views."""

    @classmethod
    def setUpClass(cls):
        """Set up the customer view tests."""
        super().setUpClass()
        cls.accessor = AWSReportDBAccessor(schema=cls.schema)

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()

    @RbacPermissions({"aws.organizational_unit": {"read": ["OU_001"]}})
    def test_rbacpermissions_aws_org_unit_data(self):
        """Test that AWS endpoints accept valid AWS permissions."""
        url = reverse("aws-organizational-units")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertTrue(len(json_result.get("data")) > 0)
