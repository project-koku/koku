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
from reporting.provider.all.models import TagMapping


class TagsSettings(IamTestCase):
    def setUp(self):
        # Populate the reporting_enabledtagkeys table with data
        self.keys = ("Project", "Name", "Business Unit", "app", "Environment", "spend", "env", "zoo")
        self.providers = (
            Provider.PROVIDER_AWS,
            Provider.PROVIDER_AZURE,
            Provider.PROVIDER_GCP,
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
        self.assertTrue({"enabled_tags_count", "enabled_tags_limit"}.issubset(meta))
        self.assertTrue(len(data) > 0)
        self.assertTrue(returned_keys == set(self.keys))

    def test_get_tags_null_param_value(self):
        test_matrix = (
            # Custom syntax
            {"filter": "filter[source_type]"},
            {"filter": "filter[provider_type]"},
            {"filter": "filter[key]"},
            {"filter": "filter[uuid]"},
            {"filter": "filter[enabled]", "expected_status": status.HTTP_200_OK},
            # Standard syntax
            {"filter": "source_type"},
            {"filter": "provider_type"},
            {"filter": "key"},
            {"filter": "uuid"},
            {"filter": "enabled", "expected_status": status.HTTP_200_OK},
        )
        tags_url = reverse("settings-tags")
        for test_case in test_matrix:
            with schema_context(self.schema_name):
                client = rest_framework.test.APIClient()
                response = client.get(tags_url, {test_case["filter"]: "\x00"}, **self.headers)

            expected_status = test_case.get("expected_status", status.HTTP_400_BAD_REQUEST)
            self.assertEqual(response.status_code, expected_status, response.data)

    def test_get_tags_filtering(self):
        test_matrix = (
            # Custom syntax
            {"filter": {"filter[source_type]": "AWS"}, "key": "source_type", "expected": {"AWS"}},
            {"filter": {"filter[source_type]": ["AWS", "GCP"]}, "key": "source_type", "expected": {"AWS", "GCP"}},
            {"filter": {"filter[key]": "env"}, "key": "key", "expected": {"env", "Environment"}},
            {"filter": {"filter[enabled]": True}, "key": "enabled", "expected": {True}},
            {"filter": {"filter[enabled]": "true"}, "key": "enabled", "expected": {True}},
            {"filter": {"filter[enabled]": "false"}, "key": "enabled", "expected": {False}},
            # DRF Syntax
            {"filter": {"source_type": "AWS"}, "key": "source_type", "expected": {"AWS"}},
            {"filter": {"provider_type": ["AWS", "GCP"]}, "key": "source_type", "expected": {"AWS", "GCP"}},
            {"filter": {"key": "env"}, "key": "key", "expected": {"env", "Environment"}},
            {"filter": {"enabled": True}, "key": "enabled", "expected": {True}},
            {"filter": {"enabled": "true"}, "key": "enabled", "expected": {True}},
            {"filter": {"enabled": "false"}, "key": "enabled", "expected": {False}},
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
        """Test one or more order_by parameters using two syntaxes.

        Standard Django ordering:
            No prefix is ascending order. A '-' prefix is descending order.

            /?order_by=field&order_by=-other_field


        Cost Management style ordering:
            'asc' and 'desc' indicate ascending or descending order.

            /?order_by[field]=asc&order_by[other_field]=desc
        """

        tags_url = reverse("settings-tags")
        test_matrix = (
            # DRF syntax
            {"order": {"order_by": "enabled"}, "key": "enabled", "expected": False},
            {"order": {"order_by": "-enabled"}, "key": "enabled", "expected": True},
            {"order": {"order_by": "provider_type"}, "key": "source_type", "expected": "AWS"},
            {"order": {"order_by": "source_type"}, "key": "source_type", "expected": "AWS"},
            {"order": {"order_by": ["source_type", "key"]}, "key": "source_type", "expected": "AWS"},
            {"order": {"order_by": "-key"}, "key": "key", "expected": "zoo"},
            # Custom syntax
            {"order": {"order_by[key]": "desc"}, "key": "key", "expected": "zoo"},
            {
                "order": {"order_by[source_type]": "asc", "order_by[key]": "desc"},
                "keys": ("source_type", "key"),
                "expected": ("AWS", "zoo"),
            },
            {
                "order": {"order_by[provider_type]": "asc", "order_by[key]": "desc"},
                "keys": ("source_type", "key"),
                "expected": ("AWS", "zoo"),
            },
        )
        for test_case in test_matrix:
            with self.subTest():
                with schema_context(self.schema_name):
                    client = rest_framework.test.APIClient()
                    response = client.get(tags_url, test_case["order"] | {"limit": 100}, **self.headers)

            data = response.data["data"]
            important_values = data[0].get(test_case.get("key"))
            if test_case.get("keys"):
                important_values = tuple(data[0].get(key) for key in test_case["keys"])

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(important_values, test_case["expected"])

    def test_tags_order_by_invalid(self):
        test_cases = (
            {"description": "Standard DRF syntax", "params": {"order_by": "NOPE"}},
            {"description": "Custom order_by syntax", "params": {"order_by[NOPE]": "asc"}},
        )
        tags_url = reverse("settings-tags")
        for case in test_cases:
            with self.subTest(case["description"]):
                with schema_context(self.schema_name):
                    client = rest_framework.test.APIClient()
                    response = client.get(tags_url, case["params"], **self.headers)

                error_message = response.data.get("errors", [{}])[0].get("detail")

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("cannot resolve keyword", error_message.lower())

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

        error_details = enable_response.data["errors"][0]["detail"].lower()

        self.assertEqual(enable_response.status_code, status.HTTP_400_BAD_REQUEST, enable_response.data)
        self.assertIn("this list may not be empty", error_details)

    def test_enable_tags_bad_uuid(self):
        """Given an invalid UUID, ensure a 400 is returned"""

        tags_enable_url = reverse("tags-enable")

        with schema_context(self.schema_name):
            client = rest_framework.test.APIClient()
            enable_response = client.put(tags_enable_url, {"ids": ["bad-uuid"]}, format="json", **self.headers)

        error_details = enable_response.data["errors"][0]["detail"].lower()

        self.assertEqual(enable_response.status_code, status.HTTP_400_BAD_REQUEST, enable_response.data)
        self.assertIn("invalid uuid supplied", error_details)

    def test_get_tags_bad_filter_key(self):
        tags_url = reverse("settings-tags")

        with schema_context(self.schema_name):
            client = rest_framework.test.APIClient()
            response = client.get(tags_url, {"filter[NOPE]": "aws"}, **self.headers)

        error_detail = response.data.get("errors", [{}])[0].get("detail").lower()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("unsupported parameter or invalid value", error_detail)

    def test_get_tags_bad_filter_value(self):
        tags_url = reverse("settings-tags")

        with schema_context(self.schema_name):
            client = rest_framework.test.APIClient()
            response = client.get(tags_url, {"filter[source_type]": "aws"}, **self.headers)

        error_detail = response.data.get("errors", [{}])[0].get("detail", "").lower()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("select a valid choice", error_detail)

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

        try:
            error = enable_response.data.get("error", "").lower()
        except AttributeError:
            error = {"data": {}}

        expected_keys = {"error", "enabled", "limit"}

        self.assertEqual(enable_response.status_code, status.HTTP_412_PRECONDITION_FAILED)
        self.assertIn("maximum number of enabled tags", error)
        self.assertEqual(expected_keys, enable_response.data.keys())

    def test_enable_tags_would_exceed_limit(self):
        """With fewer tags enabled than the limit, try to enable more than the limit"""

        tags_enable_url = reverse("tags-enable")
        uuids = [obj.uuid for obj in self.disabled_objs]

        # Set the limit slightly more than the current number of enabled tags
        with patch("api.settings.tags.view.Config", ENABLED_TAG_LIMIT=len(self.enabled_objs) + 4):
            with schema_context(self.schema_name):
                client = rest_framework.test.APIClient()
                enable_response = client.put(tags_enable_url, {"ids": uuids}, format="json", **self.headers)

        try:
            error = enable_response.data.get("error", "").lower()
        except AttributeError:
            error = {"data": {}}

        expected_keys = {"error", "enabled", "limit"}

        self.assertEqual(enable_response.status_code, status.HTTP_412_PRECONDITION_FAILED)
        self.assertIn("maximum number of enabled tags", error)
        self.assertEqual(expected_keys, enable_response.data.keys())

    def test_enable_tags_mixed_tags_would_not_exceed_limit(self):
        """With fewer tags enabled than the limit, try to enable some tags that
        are already enabled and some tags that are currently disabled where the
        total will not exceed the limit.

        This tests that only tags that would be enabled, not currently enabled tags,
        count towards the future total enabled tags.
        """

        tags_enable_url = reverse("tags-enable")
        tags_url = reverse("settings-tags")
        count_to_limit = 4
        new_limit = len(self.enabled_objs) + count_to_limit
        uuids = [obj.uuid for obj in self.disabled_objs[:count_to_limit]]

        # Set the limit slightly more than the current number of enabled tags
        with patch("api.settings.tags.view.Config", ENABLED_TAG_LIMIT=new_limit):
            with schema_context(self.schema_name):
                client = rest_framework.test.APIClient()
                enable_response = client.put(tags_enable_url, {"ids": uuids}, format="json", **self.headers)
                get_response = client.get(tags_url, {"enabled": True}, **self.headers)

        self.assertEqual(enable_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(get_response.data["meta"]["count"], new_limit)

    def test_enable_tags_mixed_tags_would_exceed_limit(self):
        """With fewer tags enabled than the limit, try to enable some tags that
        are already enabled and some tags that are currently disabled where the
        total will exceed the limit.
        """

        tags_enable_url = reverse("tags-enable")
        count_to_limit = 4
        new_limit = len(self.enabled_objs) + count_to_limit
        uuids = [obj.uuid for obj in self.disabled_objs[: count_to_limit + 1]]

        # Set the limit slightly more than the current number of enabled tags
        with patch("api.settings.tags.view.Config", ENABLED_TAG_LIMIT=new_limit):
            with schema_context(self.schema_name):
                client = rest_framework.test.APIClient()
                enable_response = client.put(tags_enable_url, {"ids": uuids}, format="json", **self.headers)

        try:
            error = enable_response.data.get("error", "").lower()
        except AttributeError:
            error = {"data": {}}

        expected_keys = {"error", "enabled", "limit"}

        self.assertEqual(enable_response.status_code, status.HTTP_412_PRECONDITION_FAILED)
        self.assertIn("maximum number of enabled tags", error)
        self.assertEqual(expected_keys, enable_response.data.keys())

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

        self.assertEqual(enable_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(get_response.data["meta"]["count"], self.total_record_length)

    def test_disabling_a_mapped_tag(self):
        """Test that you can not disable a tag that is mapped."""
        tags_disable_url = reverse("tags-disable")
        child_row = self.enabled_objs[0]
        parent_row = self.enabled_objs[1]
        with schema_context(self.schema_name):
            TagMapping.objects.create(child=child_row, parent=parent_row)
            test_matrix = [str(child_row.uuid), str(parent_row.uuid)]
        for uuid in test_matrix:
            with self.subTest(uuid=uuid):
                client = rest_framework.test.APIClient()
                disable_response = client.put(tags_disable_url, {"ids": [uuid]}, format="json", **self.headers)
                self.assertEqual(disable_response.status_code, status.HTTP_412_PRECONDITION_FAILED)
