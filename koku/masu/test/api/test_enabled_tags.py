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
from reporting.models import AWSTagsSummary
from reporting.models import AzureTagsSummary
from reporting.models import GCPTagsSummary
from reporting.models import OCPUsagePodLabelSummary
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.all.models import TagMapping


@override_settings(ROOT_URLCONF="masu.urls")
class EnabledTagsTest(MasuTestCase):
    """Test Cases for the enabled_tags endpoint."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        cls.provider_type_to_table = {
            Provider.PROVIDER_AWS.lower(): EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AWS),
            Provider.PROVIDER_AZURE.lower(): EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AZURE),
            Provider.PROVIDER_GCP.lower(): EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_GCP),
            Provider.PROVIDER_OCP.lower(): EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_OCP),
        }

        cls.provider_type_options = set(cls.provider_type_to_table.keys())
        super().setUpClass()

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_enabled_tags(self, _):
        """Test the GET enabled_tags endpoint."""
        for provider_type in self.provider_type_options:
            with self.subTest(provider_type=provider_type):
                with schema_context(self.schema):
                    enabled_table_objects = EnabledTagKeys.objects.filter(
                        provider_type=Provider.PROVIDER_CASE_MAPPING[provider_type]
                    )
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
                with schema_context(self.schema):
                    enabled_table_objects = EnabledTagKeys.objects.filter(
                        provider_type=Provider.PROVIDER_CASE_MAPPING[provider_type]
                    )
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
                with schema_context(self.schema):
                    enabled_table_objects = EnabledTagKeys.objects.filter(
                        provider_type=Provider.PROVIDER_CASE_MAPPING[provider_type]
                    )
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
        """Test remove stale enabled keys."""
        testing_metadata = {
            Provider.PROVIDER_AWS: AWSTagsSummary,
            Provider.PROVIDER_AZURE: AzureTagsSummary,
            Provider.PROVIDER_GCP: GCPTagsSummary,
        }

        for provider_type, tag_model in testing_metadata.items():
            with self.subTest(provider_type=provider_type, tag_model=tag_model):
                with schema_context(self.schema):
                    summary_keys = list(tag_model.objects.all().values_list("key", flat=True))
                    potentially_stale = []
                    queryset = EnabledTagKeys.objects.filter(key__in=summary_keys, provider_type=provider_type)[:3]
                    if len(queryset) < 3:
                        self.fail("Not enough testing data. Expects 3 elements.")
                    child, parent, expected_delete = queryset
                    potentially_stale = [child.key, parent.key, expected_delete.key]
                    TagMapping.objects.create(child=child, parent=parent)
                    tag_model.objects.filter(key__in=potentially_stale).delete()
                    expected_count = EnabledTagKeys.objects.all().count() - 1
                    post_data = {
                        "schema": "org1234567",
                        "action": "remove_stale",
                        "provider_type": provider_type.lower(),
                    }
                    response = self.client.post(reverse("enabled_tags"), post_data, content_type="application/json")
                # Loosing schema context after the post.
                with schema_context(self.schema):
                    self.assertTrue(expected_count, EnabledTagKeys.objects.all().count())
                    self.assertEqual(response.status_code, 200)

    @patch("koku.middleware.MASU", return_value=True)
    def test_post_enabled_tags_remove_stale_ocp(self, _):
        """Test remove stale enabled keys."""
        with schema_context(self.schema):
            summary_obj = OCPUsagePodLabelSummary.objects.first()
            summary_obj.delete()
            expected_count = EnabledTagKeys.objects.all().count() - 1
            post_data = {
                "schema": "org1234567",
                "action": "remove_stale",
                "provider_type": "ocp",
            }
            response = self.client.post(reverse("enabled_tags"), post_data, content_type="application/json")
        # Loosing schema context after the post.
        with schema_context(self.schema):
            self.assertTrue(expected_count, EnabledTagKeys.objects.all().count())
            self.assertEqual(response.status_code, 200)

    @patch("koku.middleware.MASU", return_value=True)
    def test_post_enabled_tags_remove_stale_ocp_tag_mapped(self, _):
        """Test remove stale enabled keys."""
        with schema_context(self.schema):
            parent = EnabledTagKeys.objects.exclude(provider_type=Provider.PROVIDER_OCP).first()
            summary_obj = OCPUsagePodLabelSummary.objects.first()
            child = EnabledTagKeys.objects.get(key=summary_obj.key, provider_type=Provider.PROVIDER_OCP)
            TagMapping.objects.create(parent=parent, child=child)
            expected_count = EnabledTagKeys.objects.all().count()
            summary_obj.delete()
            post_data = {
                "schema": "org1234567",
                "action": "remove_stale",
                "provider_type": "ocp",
            }
            response = self.client.post(reverse("enabled_tags"), post_data, content_type="application/json")
        # Loosing schema context after the post.
        with schema_context(self.schema):
            self.assertTrue(expected_count, EnabledTagKeys.objects.all().count())
            self.assertEqual(response.status_code, 200)

    @patch("koku.middleware.MASU", return_value=True)
    def test_post_enabled_tags_no_schema(self, _):
        """Test the GET enabled_tags endpoint."""
        with schema_context(self.schema):
            EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_OCP).delete()

        post_data = {"action": "create", "tag_keys": ["tag1", "tag2"], "provider_type": Provider.PROVIDER_AWS}
        response = self.client.post(reverse("enabled_tags"), post_data)
        self.assertEqual(response.status_code, 400)

    @patch("koku.middleware.MASU", return_value=True)
    def test_post_enabled_tags_no_action(self, _):
        """Test the GET enabled_tags endpoint."""
        with schema_context(self.schema):
            EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_OCP).delete()

        post_data = {"schema": "org1234567", "tag_keys": ["tag1", "tag2"], "provider_type": Provider.PROVIDER_AWS}
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
