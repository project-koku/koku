#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for Clowder V2 dependency endpoint resolution."""
import importlib
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

import sources.config
from koku.configurator import ClowderConfigurator
from koku.configurator import Configurator
from koku.configurator import EnvConfigurator
from koku.rbac import RbacService


class TestClowderV2EndpointUrl(SimpleTestCase):
    """Test ClowderConfigurator.get_endpoint_url V2/V1/fallback resolution."""

    def _make_v2_endpoint(self, uri, ca_certificate=None, authenticated=False):
        """Create a mock V2 endpoint object."""
        return SimpleNamespace(uri=uri, ca_certificate=ca_certificate, authenticated=authenticated)

    def _make_v1_endpoint(self, hostname, port):
        """Create a mock V1 endpoint object."""
        return SimpleNamespace(hostname=hostname, port=port)

    @patch.dict("os.environ", {"CLOWDER_ENABLED": "True"})
    @patch("koku.configurator.get_v2_dependency_endpoint", create=True)
    @patch("koku.configurator.DependencyEndpoints", new_callable=dict, create=True)
    def test_v2_endpoint_with_uri(self, mock_deps, mock_get_v2):
        """V2 endpoint with URI is used directly."""

        mock_get_v2.return_value = self._make_v2_endpoint("https://rbac.svc:8443")
        result = ClowderConfigurator.get_endpoint_url("rbac", "service", "http://localhost:8111")
        self.assertEqual(result, "https://rbac.svc:8443")
        mock_get_v2.assert_called_once_with("rbac", "service")

    @patch.dict("os.environ", {"CLOWDER_ENABLED": "True"})
    @patch("koku.configurator.get_v2_dependency_endpoint", create=True)
    @patch("koku.configurator.DependencyEndpoints", new_callable=dict, create=True)
    def test_v2_endpoint_with_ca_certificate(self, mock_deps, mock_get_v2):
        """V2 endpoint with CA certificate returns URI."""

        mock_get_v2.return_value = self._make_v2_endpoint(
            "https://rbac.svc:8443", ca_certificate="/tmp/ca.crt", authenticated=True
        )
        result = ClowderConfigurator.get_endpoint_url("rbac", "service", "http://localhost:8111")
        self.assertEqual(result, "https://rbac.svc:8443")

    @patch.dict("os.environ", {"CLOWDER_ENABLED": "True"})
    @patch("koku.configurator.get_v2_dependency_endpoint", create=True)
    @patch("koku.configurator.DependencyEndpoints", {"rbac": {}}, create=True)
    def test_v2_endpoint_empty_uri_falls_to_v1(self, mock_get_v2):
        """V2 endpoint with empty URI falls back to V1."""

        mock_get_v2.return_value = self._make_v2_endpoint("")
        v1 = self._make_v1_endpoint("rbac-host", 8111)
        with patch.dict("koku.configurator.DependencyEndpoints", {"rbac": {"service": v1}}):
            result = ClowderConfigurator.get_endpoint_url("rbac", "service", "http://localhost:8111")
        self.assertEqual(result, "http://rbac-host:8111")

    @patch.dict("os.environ", {"CLOWDER_ENABLED": "True"})
    @patch("koku.configurator.get_v2_dependency_endpoint", create=True)
    @patch("koku.configurator.DependencyEndpoints", {"rbac": {}}, create=True)
    def test_v2_none_falls_to_v1(self, mock_get_v2):
        """V2 returns None, falls back to V1 flat endpoint."""

        mock_get_v2.return_value = None
        v1 = self._make_v1_endpoint("sources-host", 3000)
        with patch.dict("koku.configurator.DependencyEndpoints", {"sources-api": {"svc": v1}}):
            result = ClowderConfigurator.get_endpoint_url("sources-api", "svc", "http://localhost:3000")
        self.assertEqual(result, "http://sources-host:3000")

    @patch.dict("os.environ", {"CLOWDER_ENABLED": "True"})
    @patch("koku.configurator.get_v2_dependency_endpoint", create=True)
    @patch("koku.configurator.DependencyEndpoints", new_callable=dict, create=True)
    def test_no_v2_no_v1_falls_to_default(self, mock_deps, mock_get_v2):
        """No V2 and no V1 endpoint falls back to default."""

        mock_get_v2.return_value = None
        result = ClowderConfigurator.get_endpoint_url("rbac", "service", "http://localhost:8111")
        self.assertEqual(result, "http://localhost:8111")

    @patch.dict("os.environ", {"CLOWDER_ENABLED": "True", "RBAC_SERVICE_URL": "http://custom-rbac:9999"})
    @patch("koku.configurator.get_v2_dependency_endpoint", create=True)
    @patch("koku.configurator.DependencyEndpoints", new_callable=dict, create=True)
    def test_no_v2_no_v1_falls_to_env_var(self, mock_deps, mock_get_v2):
        """No V2 and no V1 uses env var when available."""

        mock_get_v2.return_value = None
        result = ClowderConfigurator.get_endpoint_url("rbac", "service", "http://localhost:8111")
        self.assertEqual(result, "http://custom-rbac:9999")

    @patch.dict(
        "os.environ",
        {"RBAC_SERVICE_HOST": "rbac-env-host", "RBAC_SERVICE_PORT": "9090", "RBAC_SERVICE_PROTOCOL": "https"},
    )
    @patch("koku.configurator.get_v2_dependency_endpoint", create=True)
    @patch("koku.configurator.DependencyEndpoints", new_callable=dict, create=True)
    def test_no_v2_no_v1_no_url_falls_to_component_vars(self, mock_deps, mock_get_v2):
        """No V2, no V1, no URL env var falls back to component HOST/PORT/PROTOCOL vars."""

        mock_get_v2.return_value = None
        result = ClowderConfigurator.get_endpoint_url("rbac", "service", "http://localhost:8111")
        self.assertEqual(result, "https://rbac-env-host:9090")

    def test_base_configurator_returns_default(self):
        """Base Configurator.get_endpoint_url returns default directly."""

        result = Configurator.get_endpoint_url("rbac", "service", "http://localhost:8111")
        self.assertEqual(result, "http://localhost:8111")

    def test_env_configurator_returns_default(self):
        """EnvConfigurator reconstructs URL from default when no env overrides."""

        result = EnvConfigurator.get_endpoint_url("sources-api", "svc", "http://localhost:3000")
        self.assertEqual(result, "http://localhost:3000")

    @patch.dict("os.environ", {"SOURCES_API_SVC_HOST": "custom-host", "SOURCES_API_SVC_PORT": "9999"})
    def test_env_configurator_uses_env_vars(self):
        """EnvConfigurator picks up host/port from environment variables."""

        result = EnvConfigurator.get_endpoint_url("sources-api", "svc", "http://localhost:3000")
        self.assertEqual(result, "http://custom-host:9999")

    @patch.dict("os.environ", {"RBAC_SERVICE_PROTOCOL": "https"})
    def test_env_configurator_uses_protocol_env(self):
        """EnvConfigurator picks up protocol from environment variable."""

        result = EnvConfigurator.get_endpoint_url("rbac", "service", "http://localhost:8111")
        self.assertEqual(result, "https://localhost:8111")


class TestRbacServiceV2Integration(SimpleTestCase):
    """Test that RbacService uses base_url correctly."""

    @patch("koku.rbac.CONFIGURATOR")
    def test_rbac_service_uses_base_url(self, mock_configurator):
        """RbacService stores base_url from get_endpoint_url."""
        mock_configurator.get_endpoint_url.return_value = "https://rbac.svc:8443"

        svc = RbacService()
        self.assertEqual(svc.base_url, "https://rbac.svc:8443")
        self.assertFalse(hasattr(svc, "protocol"))
        self.assertFalse(hasattr(svc, "host"))
        self.assertFalse(hasattr(svc, "port"))

    @patch("koku.rbac.CONFIGURATOR")
    def test_rbac_url_construction(self, mock_configurator):
        """RbacService constructs correct full URL from base_url + path."""
        mock_configurator.get_endpoint_url.return_value = "http://rbac-host:8111"

        svc = RbacService()
        full_url = f"{svc.base_url}{svc.path}"
        self.assertEqual(full_url, "http://rbac-host:8111/r/insights/platform/rbac/v1/access/")


class TestSourcesConfigV2Integration(SimpleTestCase):
    """Test that Sources Config uses get_endpoint_url."""

    @patch("koku.configurator.CONFIGURATOR")
    def test_sources_api_url(self, mock_configurator):
        """Sources Config.SOURCES_API_URL comes from get_endpoint_url."""
        mock_configurator.get_endpoint_url.return_value = "https://sources.svc:8443"

        self.addCleanup(importlib.reload, sources.config)
        importlib.reload(sources.config)
        self.assertEqual(sources.config.Config.SOURCES_API_URL, "https://sources.svc:8443")
