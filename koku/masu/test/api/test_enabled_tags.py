#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the enabled_tags endpoint view."""
from unittest.mock import patch

from django.test.utils import override_settings
from django.urls import reverse
from tenant_schemas.utils import schema_context

from masu.test import MasuTestCase
from reporting.models import OCPEnabledTagKeys

# from django.test import TestCase


@override_settings(ROOT_URLCONF="masu.urls")
class EnabledTagsTest(MasuTestCase):
    """Test Cases for the enabled_tags endpoint."""

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_enabled_tags(self, _):
        """Test the GET enabled_tags endpoint."""
        with schema_context(self.schema):
            expected_keys = OCPEnabledTagKeys.objects.values_list("key")
            expected_keys = [key[0] for key in expected_keys]

        response = self.client.get(reverse("enabled_tags") + f"?schema={self.schema}")
        body = response.json()

        self.assertEqual(response.status_code, 200)
        for key in expected_keys:
            self.assertIn(key, body.get("tag_keys"))

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_enabled_tags_no_schema(self, _):
        """Test the GET enabled_tags endpoint."""
        response = self.client.get(reverse("enabled_tags"))
        self.assertEqual(response.status_code, 400)

    @patch("koku.middleware.MASU", return_value=True)
    def test_post_enabled_tags_create(self, _):
        """Test the GET enabled_tags endpoint."""
        with schema_context(self.schema):
            OCPEnabledTagKeys.objects.all().delete()

        post_data = {"schema": "acct10001", "action": "create", "tag_keys": ["tag1", "tag2"]}
        response = self.client.post(reverse("enabled_tags"), post_data, content_type="application/json")
        body = response.json()

        self.assertEqual(response.status_code, 200)
        for key in post_data.get("tag_keys", []):
            self.assertIn(key, body.get("tag_keys"))

    @patch("koku.middleware.MASU", return_value=True)
    def test_post_enabled_tags_delete(self, _):
        """Test the GET enabled_tags endpoint."""
        with schema_context(self.schema):
            keys = OCPEnabledTagKeys.objects.values_list("key")
            keys = [key[0] for key in keys]
            print(keys)

        post_data = {"schema": "acct10001", "action": "delete", "tag_keys": keys}

        response = self.client.post(reverse("enabled_tags"), post_data, content_type="application/json")
        body = response.json()

        self.assertEqual(response.status_code, 200)
        for key in post_data.get("tag_keys", []):
            self.assertIn(key, body.get("tag_keys"))

        with schema_context(self.schema):
            self.assertEqual(OCPEnabledTagKeys.objects.count(), 0)

    @patch("koku.middleware.MASU", return_value=True)
    def test_post_enabled_tags_no_schema(self, _):
        """Test the GET enabled_tags endpoint."""
        with schema_context(self.schema):
            OCPEnabledTagKeys.objects.all().delete()

        post_data = {"action": "create", "tag_keys": ["tag1", "tag2"]}
        response = self.client.post(reverse("enabled_tags"), post_data)
        self.assertEqual(response.status_code, 400)

    @patch("koku.middleware.MASU", return_value=True)
    def test_post_enabled_tags_no_action(self, _):
        """Test the GET enabled_tags endpoint."""
        with schema_context(self.schema):
            OCPEnabledTagKeys.objects.all().delete()

        post_data = {"schema": "acct10001", "tag_keys": ["tag1", "tag2"]}
        response = self.client.post(reverse("enabled_tags"), post_data)
        self.assertEqual(response.status_code, 400)
