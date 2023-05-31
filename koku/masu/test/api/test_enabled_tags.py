#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the enabled_tags endpoint view."""
from unittest.mock import patch

from django.test.utils import override_settings
from django.urls import reverse
from django_tenants.utils import schema_context

from api.provider.models import Provider
from masu.test import MasuTestCase
from reporting.provider.all.models import EnabledTagKeys


@override_settings(ROOT_URLCONF="masu.urls")
class EnabledTagsTest(MasuTestCase):
    """Test Cases for the enabled_tags endpoint."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        cls.provider_type_to_table = {
            Provider.PROVIDER_AWS.lower(): EnabledTagKeys.objects.filter(provider_type=Provider.PROIVDER_AWS),
            Provider.PROVIDER_AZURE.lower(): EnabledTagKeys.objects.filter(provider_type=Provider.PROIVDER_AZURE),
            Provider.PROVIDER_GCP.lower(): EnabledTagKeys.objects.filter(provider_type=Provider.PROIVDER_GCP),
            Provider.PROVIDER_OCI.lower(): EnabledTagKeys.objects.filter(provider_type=Provider.PROIVDER_OCI),
            Provider.PROVIDER_OCP.lower(): EnabledTagKeys.objects.filter(provider_type=Provider.PROIVDER_OCP),
        }

        cls.provider_type_options = set(cls.provider_type_to_table.keys())
        super().setUpClass()

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_enabled_tags(self, _):
        """Test the GET enabled_tags endpoint."""
        for provider_type in self.provider_type_options:
            with self.subTest(provider_type=provider_type):
                enabled_table_objects = self.provider_type_to_table.get(provider_type)
                with schema_context(self.schema):
                    expected_keys = enabled_table_objects.filter(enabled=True).values_list("key")
                    expected_keys = [key[0] for key in expected_keys]

                response = self.client.get(
                    reverse("enabled_tags") + f"?schema={self.schema}&provider_type={provider_type}"
                )
                body = response.json()

                self.assertEqual(response.status_code, 200)
                for key in expected_keys:
                    self.assertIn(key, body.get("tag_keys"))

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_enabled_tags_no_schema(self, _):
        """Test the GET enabled_tags endpoint."""
        response = self.client.get(reverse("enabled_tags") + "?provider_type=aws")
        self.assertEqual(response.status_code, 400)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_enabled_tags_no_provider_type(self, _):
        """Test the GET enabled_tags endpoint."""
        response = self.client.get(reverse("enabled_tags") + f"?schema={self.schema}")
        self.assertEqual(response.status_code, 400)

    @patch("koku.middleware.MASU", return_value=True)
    def test_post_enabled_tags_create(self, _):
        """Test the GET enabled_tags endpoint."""
        for provider_type in self.provider_type_options:
            with self.subTest(provider_type=provider_type):
                enabled_table_objects = self.provider_type_to_table.get(provider_type)
                with schema_context(self.schema):
                    enabled_table_objects.delete()

                post_data = {
                    "schema": "org1234567",
                    "action": "create",
                    "tag_keys": ["tag1", "tag2"],
                    "provider_type": provider_type,
                }
                response = self.client.post(reverse("enabled_tags"), post_data, content_type="application/json")
                body = response.json()

                self.assertEqual(response.status_code, 200)
                for key in post_data.get("tag_keys", []):
                    self.assertIn(key, body.get("tag_keys"))

    @patch("koku.middleware.MASU", return_value=True)
    def test_post_enabled_tags_delete(self, _):
        """Test the GET enabled_tags endpoint."""
        for provider_type in self.provider_type_options:
            with self.subTest(provider_type=provider_type):
                enabled_table_objects = self.provider_type_to_table.get(provider_type)
                with schema_context(self.schema):
                    keys = enabled_table_objects.values_list("key")
                    keys = [key[0] for key in keys]
                    print(keys)

                post_data = {
                    "schema": "org1234567",
                    "action": "delete",
                    "tag_keys": keys,
                    "provider_type": provider_type,
                }

                response = self.client.post(reverse("enabled_tags"), post_data, content_type="application/json")
                body = response.json()

                self.assertEqual(response.status_code, 200)
                for key in post_data.get("tag_keys", []):
                    self.assertIn(key, body.get("tag_keys"))

                with schema_context(self.schema):
                    self.assertEqual(enabled_table_objects.filter(enabled=True).count(), 0)

    @patch("koku.middleware.MASU", return_value=True)
    def test_post_enabled_tags_remove_stale(self, _):
        """Test the GET enabled_tags endpoint."""
        for provider_type in self.provider_type_options:
            with self.subTest(provider_type=provider_type):
                enabled_table_objects = self.provider_type_to_table.get(provider_type)
                with schema_context(self.schema):
                    keys = enabled_table_objects.values_list("key")
                    keys = [key[0] for key in keys]
                    print(keys)

                post_data = {
                    "schema": "org1234567",
                    "action": "remove_stale",
                    "provider_type": provider_type,
                }

                response = self.client.post(reverse("enabled_tags"), post_data, content_type="application/json")
                body = response.json()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(body.get("tag_keys"), [])

    @patch("koku.middleware.MASU", return_value=True)
    def test_post_enabled_tags_no_schema(self, _):
        """Test the GET enabled_tags endpoint."""
        with schema_context(self.schema):
            EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_OCP).delete()

        post_data = {"action": "create", "tag_keys": ["tag1", "tag2"], "provider_type": "aws"}
        response = self.client.post(reverse("enabled_tags"), post_data)
        self.assertEqual(response.status_code, 400)

    @patch("koku.middleware.MASU", return_value=True)
    def test_post_enabled_tags_no_action(self, _):
        """Test the GET enabled_tags endpoint."""
        with schema_context(self.schema):
            EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_OCP).delete()

        post_data = {"schema": "org1234567", "tag_keys": ["tag1", "tag2"], "provider_type": "aws"}
        response = self.client.post(reverse("enabled_tags"), post_data)
        self.assertEqual(response.status_code, 400)

    @patch("koku.middleware.MASU", return_value=True)
    def test_post_enabled_tags_no_provider_type(self, _):
        """Test the GET enabled_tags endpoint."""
        with schema_context(self.schema):
            EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_OCP).delete()

        post_data = {"schema": "org1234567", "tag_keys": ["tag1", "tag2"], "action": "create"}
        response = self.client.post(reverse("enabled_tags"), post_data)
        self.assertEqual(response.status_code, 400)
