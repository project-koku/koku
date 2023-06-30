#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the aws category settings views."""
from django.urls import reverse
from faker import Faker
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import RbacPermissions
from api.settings.test.aws_category_keys.utils import TestAwsCategoryClass

FAKE = Faker()


class AwsCategoryKeysSettingsViewTest(TestAwsCategoryClass):
    def test_expected_get_on_views(self):
        view_mapping = {
            "settings-aws-category-keys": status.HTTP_200_OK,
            "settings-aws-category-keys-enable": status.HTTP_405_METHOD_NOT_ALLOWED,
            "settings-aws-category-keys-disable": status.HTTP_405_METHOD_NOT_ALLOWED,
        }
        for view, expected in view_mapping.items():
            with self.subTest(view=view, expected=expected):
                url = reverse(view) + "?"
                client = APIClient()
                response = client.get(url, **self.headers)
                self.assertEqual(response.status_code, expected)

    def test_expected_put_on_views(self):
        view_mapping = {
            "settings-aws-category-keys": status.HTTP_405_METHOD_NOT_ALLOWED,
            "settings-aws-category-keys-disable": status.HTTP_204_NO_CONTENT,
            "settings-aws-category-keys-enable": status.HTTP_204_NO_CONTENT,
        }
        for view, expected in view_mapping.items():
            with self.subTest(view=view, expected=expected):
                url = reverse(view)
                client = APIClient()
                data = {"ids": [self.uuid]}
                response = client.put(url, data, format="json", **self.headers)
                self.assertEqual(response.status_code, expected)
                if view == "settings-aws-category-keys-disable":
                    self.assertFalse(self.check_key_enablement(self.key))
                if view == "settings-aws-category-keys-enable":
                    self.assertTrue(self.check_key_enablement(self.key))

    def test_filter_on_aws_category_view(self):
        params = [
            f"filter[uuid]={str(self.uuid)}",
            f"filter[key]={str(self.key)}",
            f"filter[enabled]={str(self.enabled)}",
        ]
        for param in params:
            with self.subTest(param=param):
                url = reverse("settings-aws-category-keys") + "?" + param
                client = APIClient()
                response = client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_put_bad_request(self):
        url = reverse("settings-aws-category-keys-disable")
        client = APIClient()
        data = {"ids": ["bad_uuid", FAKE.uuid4()]}
        response = client.put(url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class SettingsAWSCategoryRBACTest(TestAwsCategoryClass):
    """Test case for RBAC permissions to access settings."""

    NO_ACCESS = {"aws.account": {"read": ["*"]}, "aws.organizational_unit": {"read": ["*"]}}
    READ = {"settings": {"read": ["*"]}}
    WRITE = {"settings": {"write": ["*"]}}

    @RbacPermissions(NO_ACCESS)
    def test_no_access_to_get_request(self):
        url = reverse("settings-aws-category-keys") + "?" + f"filter[key]={str(self.key)}"
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @RbacPermissions(READ)
    def test_read_accesss_to_get_request(self):
        url = reverse("settings-aws-category-keys") + "?" + f"filter[key]={str(self.key)}"
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions(READ)
    def test_read_access_to_put_request(self):
        url = reverse("settings-aws-category-keys-disable")
        client = APIClient()
        data = {"ids": [self.uuid]}
        response = client.put(url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @RbacPermissions(WRITE)
    def test_write_on_put_request(self):
        url = reverse("settings-aws-category-keys-disable")
        client = APIClient()
        data = {"ids": [self.uuid]}
        response = client.put(url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    @RbacPermissions(WRITE)
    def test_write_on_get_request(self):
        url = reverse("settings-aws-category-keys") + "?" + f"filter[key]={str(self.key)}"
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
