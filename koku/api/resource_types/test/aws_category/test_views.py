#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Resource Types views."""
from django.urls import reverse
from rest_framework import status
from tenant_schemas.utils import schema_context

from api.iam.test.iam_test_case import RbacPermissions
from api.utils import DateHelper
from masu.test import MasuTestCase
from reporting.provider.aws.models import AWSEnabledCategoryKeys


class ResourceTypesViewTestAWSCategory(MasuTestCase):
    """Tests the resource types views."""

    @classmethod
    def setUpClass(cls):
        """Set up the customer view tests."""
        super().setUpClass()

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()
        self.dh = DateHelper()
        self.start_date = self.dh.this_month_start
        self.end_date = self.dh.this_month_end

    @RbacPermissions({"aws.account": {"read": ["*"]}})
    def test_aws_categories_view_with_wildcard(self):
        """Test aws categories return."""
        with schema_context(self.schema):
            expected = AWSEnabledCategoryKeys.objects.filter(enabled=True).values_list("key", flat=True)
            url = reverse("aws-categories")
            response = self.client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            json_result = response.json()
            self.assertIsNotNone(json_result.get("data"))
            self.assertIsInstance(json_result.get("data"), list)
            self.assertEqual(len(json_result.get("data")), len(expected))

    @RbacPermissions({"aws.account": {"read": ["*"]}})
    def test_aws_categories_view_with_bad_param(self):
        """Test aws categories return."""
        url = reverse("aws-categories")
        url = url + "?bad_param"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @RbacPermissions({"aws.account": {"read": ["123456"]}})
    def test_aws_categories_unauthorized_account(self):
        """Test aws categories return."""
        url = reverse("aws-categories")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), 0)
