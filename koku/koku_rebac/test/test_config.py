#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for Kessel ReBAC configuration settings and exceptions."""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "koku.test_settings_lite")

import django  # noqa: E402

django.setup()

from django.test import SimpleTestCase  # noqa: E402


class TestAuthorizationBackendSetting(SimpleTestCase):
    """Verify AUTHORIZATION_BACKEND is derived correctly."""

    def test_onprem_resolves_to_rebac(self):
        """resolve_authorization_backend(onprem=True) always returns 'rebac'."""
        from koku_rebac.config import resolve_authorization_backend

        self.assertEqual(resolve_authorization_backend(onprem=True, env_value=""), "rebac")

    def test_onprem_forces_rebac_even_if_env_says_rbac(self):
        from koku_rebac.config import resolve_authorization_backend

        result = resolve_authorization_backend(onprem=True, env_value="rbac")
        self.assertEqual(result, "rebac")

    def test_saas_default_is_rbac(self):
        from koku_rebac.config import resolve_authorization_backend

        result = resolve_authorization_backend(onprem=False, env_value="")
        self.assertEqual(result, "rbac")

    def test_saas_explicit_rebac_is_honoured(self):
        from koku_rebac.config import resolve_authorization_backend

        result = resolve_authorization_backend(onprem=False, env_value="rebac")
        self.assertEqual(result, "rebac")

    def test_invalid_value_falls_back_to_rbac(self):
        from koku_rebac.config import resolve_authorization_backend

        result = resolve_authorization_backend(onprem=False, env_value="invalid")
        self.assertEqual(result, "rbac")


class TestKesselCacheEnum(SimpleTestCase):
    """CacheEnum should include a kessel entry."""

    def test_kessel_cache_enum_exists(self):
        from koku.settings import CacheEnum

        self.assertTrue(hasattr(CacheEnum, "kessel"))


class TestKesselConfigDicts(SimpleTestCase):
    """Kessel configuration settings must exist."""

    def test_inventory_config_exists(self):
        from django.conf import settings

        self.assertTrue(hasattr(settings, "KESSEL_INVENTORY_CONFIG"))
        self.assertIn("host", settings.KESSEL_INVENTORY_CONFIG)
        self.assertIn("port", settings.KESSEL_INVENTORY_CONFIG)

    def test_relations_config_removed(self):
        """KESSEL_RELATIONS_CONFIG must no longer exist -- Koku uses Inventory API only."""
        from django.conf import settings

        self.assertFalse(hasattr(settings, "KESSEL_RELATIONS_CONFIG"))

    def test_spicedb_config_removed(self):
        """SPICEDB_CONFIG must no longer exist -- management plane is externalized."""
        from django.conf import settings

        self.assertFalse(hasattr(settings, "SPICEDB_CONFIG"))

    def test_kessel_ca_path_exists(self):
        from django.conf import settings

        self.assertTrue(hasattr(settings, "KESSEL_CA_PATH"))

    def test_kessel_auth_settings_exist(self):
        from django.conf import settings

        self.assertTrue(hasattr(settings, "KESSEL_AUTH_ENABLED"))
        self.assertTrue(hasattr(settings, "KESSEL_AUTH_CLIENT_ID"))
        self.assertTrue(hasattr(settings, "KESSEL_AUTH_CLIENT_SECRET"))
        self.assertTrue(hasattr(settings, "KESSEL_AUTH_OIDC_ISSUER"))

    def test_rbac_v2_url_exists(self):
        from django.conf import settings

        self.assertTrue(hasattr(settings, "RBAC_V2_URL"))


class TestKesselExceptions(SimpleTestCase):
    """Custom exception hierarchy."""

    def test_kessel_error_is_exception(self):
        from koku_rebac.exceptions import KesselError

        self.assertTrue(issubclass(KesselError, Exception))

    def test_kessel_connection_error_is_kessel_error(self):
        from koku_rebac.exceptions import KesselConnectionError, KesselError

        self.assertTrue(issubclass(KesselConnectionError, KesselError))

    def test_kessel_connection_error_can_be_raised(self):
        from koku_rebac.exceptions import KesselConnectionError

        with self.assertRaises(KesselConnectionError):
            raise KesselConnectionError("test connection failure")
