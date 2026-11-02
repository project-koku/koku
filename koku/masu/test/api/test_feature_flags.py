#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the schema feature-flags Masu endpoint."""
from unittest.mock import patch

from django.test.utils import override_settings
from django.urls import reverse

from masu.api.feature_flags import DEFAULT_SCHEMA_FEATURE_FLAGS
from masu.processor import OCP_TAG_MAPPING_STATEMENT_TIMEOUT_FLAG
from masu.test import MasuTestCase


@override_settings(ROOT_URLCONF="masu.urls")
class SchemaFeatureFlagsTests(MasuTestCase):
    """Test cases for GET feature-flags/."""

    @patch("koku.middleware.MASU", return_value=True)
    def test_schema_required(self, _):
        """Omit schema → 400."""
        response = self.client.get(reverse("schema_feature_flags"))
        self.assertEqual(response.status_code, 400)

    @patch("koku.middleware.MASU", return_value=True)
    def test_unknown_schema(self, _):
        """Unknown tenant schema → 400."""
        response = self.client.get(reverse("schema_feature_flags"), {"schema": "acct_does_not_exist"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("does not exist", response.json()["errors"][0]["detail"])

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.feature_flags.is_feature_flag_enabled_by_schema")
    def test_default_flags(self, mock_enabled, _):
        """Default curated list is evaluated for the schema."""
        mock_enabled.side_effect = lambda schema, flag, **kwargs: flag.endswith("penalty-customer")
        response = self.client.get(reverse("schema_feature_flags"), {"schema": self.schema})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["schema"], self.schema)
        self.assertEqual(set(body["flags"]), set(DEFAULT_SCHEMA_FEATURE_FLAGS))
        self.assertTrue(body["flags"]["cost-management.backend.penalty-customer"])
        self.assertFalse(body["flags"][OCP_TAG_MAPPING_STATEMENT_TIMEOUT_FLAG])
        self.assertEqual(mock_enabled.call_count, len(DEFAULT_SCHEMA_FEATURE_FLAGS))

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.feature_flags.is_feature_flag_enabled_by_schema")
    def test_custom_flags_param(self, mock_enabled, _):
        """Optional flags= limits evaluation to the requested names."""
        mock_enabled.return_value = True
        flag_a = "cost-management.backend.penalty-customer"
        flag_b = OCP_TAG_MAPPING_STATEMENT_TIMEOUT_FLAG
        response = self.client.get(
            reverse("schema_feature_flags"),
            {"schema": self.schema, "flags": f"{flag_a}, {flag_b}, {flag_a}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["flags"], {flag_a: True, flag_b: True})
        self.assertEqual(mock_enabled.call_count, 2)

    @patch("koku.middleware.MASU", return_value=True)
    def test_empty_flags_param(self, _):
        """flags= with only whitespace → 400."""
        response = self.client.get(
            reverse("schema_feature_flags"),
            {"schema": self.schema, "flags": " , "},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("flag", response.json()["errors"][0]["detail"].lower())
