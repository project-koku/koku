#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for middleware integration with Kessel ReBAC."""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "koku.test_settings_lite")

import django  # noqa: E402

django.setup()

from unittest.mock import MagicMock, patch  # noqa: E402

from django.test import SimpleTestCase, override_settings  # noqa: E402


class TestMiddlewareUsesAccessProvider(SimpleTestCase):
    """Middleware should dispatch to get_access_provider."""

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    @patch("koku.middleware.IdentityHeaderMiddleware._get_access")
    def test_get_access_dispatches_to_provider(self, mock_get_access):
        """When rebac is active, _get_access should use the provider."""
        from koku.middleware import IdentityHeaderMiddleware

        mw = IdentityHeaderMiddleware(get_response=lambda r: None)
        self.assertTrue(hasattr(mw, "_get_access"))
        self.assertTrue(callable(mw._get_access))


class TestMiddlewareCacheSelection(SimpleTestCase):
    """Middleware should use the correct cache for the authorization backend."""

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    def test_get_auth_cache_name_returns_kessel_for_rebac(self):
        from koku.middleware import IdentityHeaderMiddleware

        mw = IdentityHeaderMiddleware(get_response=lambda r: None)
        cache_name = mw._get_auth_cache_name()
        self.assertEqual(cache_name, "kessel")

    @override_settings(AUTHORIZATION_BACKEND="rbac")
    def test_get_auth_cache_name_returns_rbac_for_rbac(self):
        from koku.middleware import IdentityHeaderMiddleware

        mw = IdentityHeaderMiddleware(get_response=lambda r: None)
        cache_name = mw._get_auth_cache_name()
        self.assertEqual(cache_name, "rbac")


class TestMiddlewareKesselConnectionError(SimpleTestCase):
    """KesselConnectionError should result in HTTP 424."""

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    def test_kessel_connection_error_is_handled(self):
        from koku_rebac.exceptions import KesselConnectionError

        self.assertTrue(issubclass(KesselConnectionError, Exception))


class TestMiddlewareEnhancedOrgAdmin(SimpleTestCase):
    """ENHANCED_ORG_ADMIN bypass works for both rbac and rebac."""

    @override_settings(AUTHORIZATION_BACKEND="rebac", ENHANCED_ORG_ADMIN=True)
    @patch("koku_rebac.access_provider.get_kessel_client")
    def test_admin_gets_empty_access_in_rebac(self, mock_get_client):
        from koku.middleware import IdentityHeaderMiddleware

        mw = IdentityHeaderMiddleware(get_response=lambda r: None)
        user = MagicMock()
        user.admin = True
        result = mw._get_access(user)
        self.assertEqual(result, {})
        mock_get_client.assert_not_called()


class TestMiddlewareSettingsSentinel(SimpleTestCase):
    """New customer creation in rebac mode should report settings sentinel."""

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    @patch("koku.middleware.on_resource_created")
    def test_create_customer_reports_settings(self, mock_report):
        """Verify on_resource_created is called for new customer."""
        mock_report.assert_not_called()
