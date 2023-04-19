#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Resource Types views."""
from django.urls import reverse
from rest_framework import status
from tenant_schemas.utils import schema_context

from api.iam.test.iam_test_case import RbacPermissions
from api.report.test.util.constants import AWS_CONSTANTS
from masu.test import MasuTestCase
from reporting.provider.aws.models import AWSCategorySummary
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
        self.aws_category_tuple = AWS_CONSTANTS["cost_category"]
        with schema_context(self.schema):
            enabled_keys = AWSEnabledCategoryKeys.objects.filter(enabled=True).values_list("key", flat=True)
            self.enabled_keys = list(enabled_keys)
            row = AWSCategorySummary.objects.filter(account_alias__isnull=False).first()
            self.account_id = row.usage_account_id
            self.account_alias = row.account_alias.account_alias
        self.key_only_expected_keys = ["value"]
        self.expected_keys = ["key", "values", "enabled"]

    def check_data_return(self, data, expected_keys, expected_length):
        """Checks that the correct keys is as expected."""
        self.assertIsNotNone(data)
        self.assertIsInstance(data, list)
        if expected_length > 0:
            self.assertEqual(len(data), expected_length)
        for dikt in data:
            unexpected_keys = set(dikt.keys()) - set(expected_keys)
            self.assertFalse(unexpected_keys)

    @RbacPermissions({"aws.account": {"read": ["*"]}})
    def test_aws_categories_view_with_wildcard(self):
        """Test aws categories return."""
        url = reverse("aws-categories")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.check_data_return(json_result.get("data"), self.expected_keys, len(self.enabled_keys))

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
        self.check_data_return(json_result.get("data"), self.expected_keys, 0)

    @RbacPermissions({"aws.account": {"read": ["123456"]}})
    def test_aws_categories_filter_unauthorized_account(self):
        """Test aws categories return."""
        url = reverse("aws-categories") + "?account=9999999999999"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @RbacPermissions({"aws.account": {"read": ["*"]}})
    def test_aws_categories_limit_filter(self):
        """Test aws categories return."""
        limit = 1
        url = reverse("aws-categories") + f"?limit={limit}"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.check_data_return(json_result.get("data"), self.expected_keys, limit)

    @RbacPermissions({"aws.account": {"read": ["*"]}})
    def test_aws_categories_key_filter(self):
        """Test aws categories return."""
        aws_cat_dict = self.aws_category_tuple[0]
        aws_cat_key = list(aws_cat_dict.keys())[0]
        url = reverse("aws-categories") + f"?key={aws_cat_key}"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.check_data_return(json_result.get("data"), self.expected_keys, 1)
        for item in json_result.get("data"):
            self.assertEqual(item.get("key"), aws_cat_key)

    def test_aws_categories_value_filter(self):
        """Test aws categories return."""
        aws_cat_dict = self.aws_category_tuple[0]
        aws_cat_value = list(aws_cat_dict.values())[0]
        url = reverse("aws-categories") + f"?value={aws_cat_value}"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.check_data_return(json_result.get("data"), self.expected_keys, 1)
        for item in json_result.get("data"):
            self.assertIn(aws_cat_value, item.get("values"))

    def test_aws_categories_account_filter(self):
        """Test aws categories return."""
        for account in [self.account_alias, self.account_id]:
            with self.subTest(account=account):
                url = reverse("aws-categories") + f"?account={account}"
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                json_result = response.json()
                self.assertIsNotNone(json_result.get("data"))
                self.assertIsInstance(json_result.get("data"), list)
                self.assertNotEqual(len(json_result.get("data")), 0)

    @RbacPermissions({"aws.account": {"read": ["*"]}})
    def test_aws_categories_view_with_wildcard_key_only(self):
        """Test aws categories return."""
        url = reverse("aws-categories") + "?key_only=True"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.check_data_return(json_result.get("data"), self.key_only_expected_keys, len(self.enabled_keys))

    @RbacPermissions({"aws.account": {"read": ["4567"]}})
    def test_aws_categories_view_with_wildcard_key_only_rbac(self):
        """Test aws categories return."""
        url = reverse("aws-categories") + "?key_only=True"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.check_data_return(json_result.get("data"), self.key_only_expected_keys, 0)

    @RbacPermissions({"aws.account": {"read": ["*"]}})
    def test_aws_categories_key_only_filter_account(self):
        """Test aws categories return."""
        for account in [self.account_alias, self.account_id]:
            url = reverse("aws-categories") + f"?key_only=True&account={account}"
            response = self.client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            json_result = response.json()
            self.assertIsNotNone(json_result.get("data"))
            self.assertIsInstance(json_result.get("data"), list)
            self.assertNotEqual(len(json_result.get("data")), 0)

    @RbacPermissions({"aws.account": {"read": ["*"]}})
    def test_aws_categories_key_only_bad_param(self):
        """Test aws categories return."""
        disabled_filters = ["value", "key", "search"]
        for disabled_filter in disabled_filters:
            with self.subTest(disabled_filter=disabled_filter):
                url = reverse("aws-categories")
                url = url + f"?key_only=true&{disabled_filter}=value"
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
