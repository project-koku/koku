#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import itertools

import rest_framework.test
from django.urls import reverse
from django_tenants.utils import schema_context
from rest_framework import status

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from reporting.provider.all.models import EnabledTagKeys


class TagsTests(IamTestCase):
    def setUp(self):
        # Populate the reporting_enabledtagkeys table with data
        self.keys = ("Project", "Name", "Business Unit", "app", "environment", "spend")
        self.providers = (
            Provider.PROVIDER_AWS,
            Provider.PROVIDER_AZURE,
            Provider.PROVIDER_GCP,
            Provider.PROVIDER_OCI,
        )
        combo = tuple(itertools.product(self.providers, self.keys))
        self.expected_length = len(combo)
        self.expected_records = [
            {"key": key, "provider_type": provider_type, "enable": True} for key, provider_type in combo
        ]

        with schema_context(self.schema_name):
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

    def tearDown(self):
        print("nuke all the tags")

    def test_get_tags(self):
        """Test basic GET of tags"""

        url = reverse("settings-tags")
        with schema_context(self.schema_name):
            client = rest_framework.test.APIClient()
            response = client.get(url, **self.headers)

        meta = response.data["meta"]
        data = response.data["data"]
        returned_keys = {item["key"] for item in data}

        self.assertEqual(self.expected_length, meta["count"])
        self.assertTrue(len(data) > 0)
        self.assertTrue(returned_keys == set(self.keys))

    def test_enable_tags(self):
        tags_url = reverse("settings-tags")
        tags_enable_url = reverse("tags-enable")
        slice_size = 5

        with schema_context(self.schema_name):
            client = rest_framework.test.APIClient()
            ids_to_enable = [str(obj.uuid) for obj in self.disabled_objs[:slice_size]]
            enable_response = client.put(tags_enable_url, {"ids": ids_to_enable}, format="json", **self.headers)
            get_response = client.get(tags_url, {"filter[enabled]": True}, **self.headers)

        enabled_uuids = {item["uuid"] for item in get_response.data["data"]}

        self.assertEqual(enable_response.status_code, status.HTTP_204_NO_CONTENT, enable_response.data)
        self.assertEqual(get_response.data["meta"]["count"], len(self.enabled_objs) + slice_size)
        self.assertTrue(set(ids_to_enable).issubset(enabled_uuids))
