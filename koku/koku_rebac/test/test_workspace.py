#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the WorkspaceResolver implementations."""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "koku.test_settings_lite")

import django  # noqa: E402

django.setup()

from unittest.mock import patch  # noqa: E402

from django.test import SimpleTestCase, override_settings  # noqa: E402


class TestShimResolver(SimpleTestCase):
    """ShimResolver returns org_id as workspace_id."""

    def test_resolve_returns_org_id(self):
        from koku_rebac.workspace import ShimResolver

        resolver = ShimResolver()
        self.assertEqual(resolver.resolve("org-42"), "org-42")

    def test_resolve_empty_org(self):
        from koku_rebac.workspace import ShimResolver

        resolver = ShimResolver()
        self.assertEqual(resolver.resolve(""), "")

    def test_resolve_preserves_format(self):
        from koku_rebac.workspace import ShimResolver

        resolver = ShimResolver()
        self.assertEqual(resolver.resolve("12345678"), "12345678")


class TestRbacV2Resolver(SimpleTestCase):
    """RbacV2Resolver calls RBAC v2 with OAuth2 bearer token."""

    @patch("koku_rebac.workspace.requests.get")
    @patch("koku_rebac.workspace.requests.post")
    def test_resolve_calls_rbac_with_oauth_token(self, mock_post, mock_get):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status = lambda: None
        mock_post.return_value.json.return_value = {"access_token": "tok-123"}

        mock_get.return_value.status_code = 200
        mock_get.return_value.raise_for_status = lambda: None
        mock_get.return_value.json.return_value = {"results": [{"id": "ws-abc-def", "type": "default"}]}

        from koku_rebac.workspace import RbacV2Resolver

        resolver = RbacV2Resolver(
            rbac_url="http://rbac:8000",
            token_url="http://sso/token",
            client_id="koku",
            client_secret="secret",
        )
        result = resolver.resolve("org-99")

        self.assertEqual(result, "ws-abc-def")
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        self.assertEqual(call_kwargs.kwargs["headers"]["x-rh-rbac-org-id"], "org-99")
        self.assertEqual(call_kwargs.kwargs["headers"]["Authorization"], "Bearer tok-123")
        self.assertNotIn("x-rh-identity", call_kwargs.kwargs["headers"])

    @patch("koku_rebac.workspace.requests.get")
    @patch("koku_rebac.workspace.requests.post")
    def test_resolve_no_results_raises(self, mock_post, mock_get):
        mock_post.return_value.raise_for_status = lambda: None
        mock_post.return_value.json.return_value = {"access_token": "tok"}

        mock_get.return_value.raise_for_status = lambda: None
        mock_get.return_value.json.return_value = {"results": []}

        from koku_rebac.workspace import RbacV2Resolver

        resolver = RbacV2Resolver(
            rbac_url="http://rbac:8000",
            token_url="http://sso/token",
            client_id="koku",
            client_secret="secret",
        )
        with self.assertRaises(ValueError):
            resolver.resolve("org-missing")

    @patch("koku_rebac.workspace.requests.post")
    def test_token_failure_raises(self, mock_post):
        from requests.exceptions import HTTPError

        mock_post.return_value.raise_for_status.side_effect = HTTPError("401")

        from koku_rebac.workspace import RbacV2Resolver

        resolver = RbacV2Resolver(
            rbac_url="http://rbac:8000",
            token_url="http://sso/token",
            client_id="bad-id",
            client_secret="bad-secret",
        )
        with self.assertRaises(HTTPError):
            resolver.resolve("org-1")


class TestGetWorkspaceResolverFactory(SimpleTestCase):
    """get_workspace_resolver returns the right resolver based on ONPREM."""

    @override_settings(ONPREM=True)
    def test_returns_shim_when_onprem(self):
        from koku_rebac.workspace import ShimResolver, get_workspace_resolver

        resolver = get_workspace_resolver()
        self.assertIsInstance(resolver, ShimResolver)

    @override_settings(ONPREM=False)
    def test_returns_rbac_v2_when_not_onprem(self):
        from koku_rebac.workspace import RbacV2Resolver, get_workspace_resolver

        resolver = get_workspace_resolver()
        self.assertIsInstance(resolver, RbacV2Resolver)
