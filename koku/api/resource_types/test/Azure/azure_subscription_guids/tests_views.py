#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Resource Types views for azure subscription guids endpoint."""
from django.urls import reverse
from rest_framework import status

from api.iam.test.iam_test_case import RbacPermissions
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.test import MasuTestCase


class ResourceTypesViewTestAzureSubscriptionGuids(MasuTestCase):
    """Tests the resource types views."""

    @classmethod
    def setUpClass(cls):
        """Set up the customer view tests."""
        super().setUpClass()
        cls.accessor = AzureReportDBAccessor(schema=cls.schema)

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()

    @RbacPermissions({"azure.subscription_guid": {"read": ["*"]}})
    def test_azure_subscriptions_guids_ocp_view(self):
        """Test endpoint runs with a customer owner."""
        qs = "?openshift=true"
        url = reverse("azure-subscription-guids") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
