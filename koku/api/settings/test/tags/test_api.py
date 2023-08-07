#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import itertools
from unittest.mock import patch

import rest_framework.test
from django.urls import reverse
from django_tenants.utils import schema_context
from rest_framework import status

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from reporting.provider.all.models import EnabledTagKeys


class TagsSettings(IamTestCase):
    def setUp(self):
        # Populate the reporting_enabledtagkeys table with data
        self.keys = ("Project", "Name", "Business Unit", "app", "Environment", "spend", "env")
        self.providers = (
            Provider.PROVIDER_AWS,
            Provider.PROVIDER_AZURE,
            Provider.PROVIDER_GCP,
            Provider.PROVIDER_OCI,
        )
        combo = tuple(itertools.product(self.providers, self.keys))
        self.total_record_length = len(combo)
        self.expected_records = [
            {"key": key, "provider_type": provider_type, "enable": True} for key, provider_type in combo
        ]

        with schema_context(self.schema_name):
            # Delete any existing records to start a with clean test environment
            EnabledTagKeys.objects.all().delete()

            split = len(combo) // 2

            # Create some enabled records
            enabled_records = (
                EnabledTagKeys(key=key, provider_type=provider, enabled=True) for provider, key in combo[:split]
            )
            self.enabled_objs = EnabledTagKeys.objects.bulk_create(enabled_records)

            # Create some disabled records
            disabled_records = (
                EnabledTagKeys(key=key, provider_type=provider, enabled=False) for provider, key in combo[split:]
            )
            self.disabled_objs = EnabledTagKeys.objects.bulk_create(disabled_records)

    def test_get_tags(self):
        """Test basic GET of tags"""

        url = reverse("settings-tags")
        with schema_context(self.schema_name):
            client = rest_framework.test.APIClient()
            response = client.get(url, **self.headers)

        meta = response.data["meta"]
        data = response.data["data"]
        returned_keys = {item["key"] for item in data}

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.total_record_length, meta["count"])
        self.assertTrue(len(data) > 0)
        self.assertTrue(returned_keys == set(self.keys))

    def test_get_tags_filtering(self):
        test_matrix = (
            {"filter": {"filter[provider_type]": "AWS"}, "key": "provider_type", "expected": {"AWS"}},
            {"filter": {"filter[provider_type]": ["AWS", "GCP"]}, "key": "provider_type", "expected": {"AWS", "GCP"}},
            {"filter": {"filter[key]": "env"}, "key": "key", "expected": {"env", "Environment"}},
        )
        tags_url = reverse("settings-tags")

        for test_case in test_matrix:
            with self.subTest():
                with schema_context(self.schema_name):
                    client = rest_framework.test.APIClient()
                    response = client.get(tags_url, test_case["filter"] | {"limit": 100}, **self.headers)

                data = response.data["data"]
                providers = {item[test_case["key"]] for item in data}
                count = response.data["meta"]["count"]

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(providers, test_case["expected"])
                self.assertLessEqual(count, self.total_record_length)

    def test_tags_order_by(self):
        tags_url = reverse("settings-tags")
        test_matrix = (
            {"order": "enabled", "key": "enabled", "expected": False},
            {"order": "-enabled", "key": "enabled", "expected": True},
            {"order": ["-provider_type", "key"], "key": "provider_type", "expected": "OCI"},
        )

        for test_case in test_matrix:
            with self.subTest():
                with schema_context(self.schema_name):
                    client = rest_framework.test.APIClient()
                    response = client.get(tags_url, {"order_by": test_case["order"], "limit": 100}, **self.headers)

            data = response.data["data"]

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(data[0].get(test_case["key"]), test_case["expected"])

    def test_enable_tags(self):
        """PUT a list of UUIDs and ensure they are enabled"""

        tags_url = reverse("settings-tags")
        tags_enable_url = reverse("tags-enable")
        slice_size = 5

        with schema_context(self.schema_name):
            client = rest_framework.test.APIClient()
            ids_to_enable = [str(obj.uuid) for obj in self.disabled_objs[:slice_size]]
            enable_response = client.put(tags_enable_url, {"ids": ids_to_enable}, format="json", **self.headers)
            get_response = client.get(tags_url, {"filter[enabled]": True, "limit": 100}, **self.headers)

        enabled_uuids = {item["uuid"] for item in get_response.data["data"]}
        self.assertEqual(enable_response.status_code, status.HTTP_204_NO_CONTENT, enable_response.data)
        self.assertEqual(get_response.data["meta"]["count"], len(self.enabled_objs) + slice_size)
        self.assertTrue(set(ids_to_enable).issubset(enabled_uuids))

    def test_disable_tags(self):
        """PUT a list of UUIDs and ensure they are disabled"""
        tags_url = reverse("settings-tags")
        tags_disable_url = reverse("tags-disable")
        slice_size = 5

        with schema_context(self.schema_name):
            client = rest_framework.test.APIClient()
            ids_to_disable = [str(obj.uuid) for obj in self.enabled_objs[:slice_size]]
            disable_response = client.put(tags_disable_url, {"ids": ids_to_disable}, format="json", **self.headers)
            get_response = client.get(tags_url, {"filter[enabled]": False, "limit": 100}, **self.headers)

        disabled_uuids = {item["uuid"] for item in get_response.data["data"]}
        self.assertEqual(disable_response.status_code, status.HTTP_204_NO_CONTENT, disable_response.data)
        self.assertEqual(get_response.data["meta"]["count"], len(self.enabled_objs) + slice_size)
        self.assertTrue(set(ids_to_disable).issubset(disabled_uuids))

    def test_enable_tags_empty_id_list(self):
        """Given an empty list of UUIDs, ensure a 400 is returned"""

        tags_enable_url = reverse("tags-enable")

        with schema_context(self.schema_name):
            client = rest_framework.test.APIClient()
            enable_response = client.put(tags_enable_url, {"ids": []}, format="json", **self.headers)

        error_details = enable_response.data.get("errors", [{}])[0].get("detail", "").lower()

        self.assertEqual(enable_response.status_code, status.HTTP_400_BAD_REQUEST, enable_response.data)
        self.assertIn("this list may not be empty", error_details)

    def test_enable_tags_bad_uuid(self):
        """Given an invalid UUID, ensure a 400 is returned"""

        tags_enable_url = reverse("tags-enable")

        with schema_context(self.schema_name):
            client = rest_framework.test.APIClient()
            enable_response = client.put(tags_enable_url, {"ids": ["bad-uuid"]}, format="json", **self.headers)

        error_details = enable_response.data.get("errors", [{}])[0].get("detail", "").lower()

        self.assertEqual(enable_response.status_code, status.HTTP_400_BAD_REQUEST, enable_response.data)
        self.assertIn("invalid uuid supplied", error_details)

    @patch("api.settings.tags.view.Config", ENABLED_TAG_LIMIT=1)
    def test_enable_tags_over_limit(self, mock_enabled_limit):
        """Given more tags enabled than are allowed by the limit,
        ensure no more tags are enabled and an error is returned.
        """

        tags_enable_url = reverse("tags-enable")
        uuids = [obj.uuid for obj in self.disabled_objs[:4]]

        with schema_context(self.schema_name):
            client = rest_framework.test.APIClient()
            enable_response = client.put(tags_enable_url, {"ids": uuids}, format="json", **self.headers)

        error = enable_response.data.get("error", "").lower()
        self.assertEqual(enable_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("maximum number of enabled tags exceeded", error)

    @patch("api.settings.tags.view.Config", ENABLED_TAG_LIMIT=-1)
    def test_enable_tags_limit_disabled(self, mock_enabled_limit):
        """Test that enabling tags is not limited if the limit is disabled."""

        tags_enable_url = reverse("tags-enable")
        tags_url = reverse("settings-tags")
        uuids = [obj.uuid for obj in self.disabled_objs]

        with schema_context(self.schema_name):
            client = rest_framework.test.APIClient()
            enable_response = client.put(tags_enable_url, {"ids": uuids}, format="json", **self.headers)
            get_response = client.get(tags_url, {"filter[enabled]": True, "limit": 100}, **self.headers)

        self.assertEqual(enable_response.status_code, status.HTTP_204_NO_CONTENT, enable_response.data)
        self.assertEqual(get_response.data["meta"]["count"], self.total_record_length)
