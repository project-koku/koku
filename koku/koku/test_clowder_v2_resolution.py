#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for Clowder V2 dependency endpoint resolution and service auth."""
from types import SimpleNamespace
from unittest.mock import patch

import requests_mock
from django.test import SimpleTestCase

from koku import service_auth
from koku.configurator import ClowderConfigurator
from koku.configurator import DependencyEndpoint
from koku.configurator import EnvConfigurator
from koku.rbac import RbacService
from sources.config import Config as SourcesConfig
from sources.sources_http_client import SourcesHTTPClient

GATEWAY = "https://ewgw.example.com:443"
IN_CLUSTER = "http://rbac-service.ns.svc:8000"


def v2(uri, authenticated=False, ca_certificate=None):
    return SimpleNamespace(uri=uri, authenticated=authenticated, ca_certificate=ca_certificate)


class FakeCredentials:
    def get_token(self):
        return SimpleNamespace(access_token="tok")


class TestClowderDependencyEndpoint(SimpleTestCase):
    """Test ClowderConfigurator.get_dependency_endpoint."""

    @patch("koku.configurator.get_v2_dependency_endpoint", create=True)
    def test_v2_endpoint(self, mock_get_v2):
        """uri, authenticated and ca_certificate come from the v2 endpoint."""
        mock_get_v2.return_value = v2(GATEWAY + "/", True, "/tmp/ca.crt")
        endpoint = ClowderConfigurator.get_dependency_endpoint("rbac", "service", "http://localhost:8111")
        self.assertEqual(endpoint, DependencyEndpoint(GATEWAY, True, "/tmp/ca.crt"))
        mock_get_v2.assert_called_once_with("rbac", "service")

    @patch("koku.configurator.get_v2_dependency_endpoint", create=True)
    def test_authenticated_defaults_to_false(self, mock_get_v2):
        """A v2 endpoint without an authenticated field is unauthenticated."""
        mock_get_v2.return_value = v2(IN_CLUSTER, authenticated=None)
        endpoint = ClowderConfigurator.get_dependency_endpoint("rbac", "service", "http://localhost:8111")
        self.assertFalse(endpoint.authenticated)

    @patch("koku.configurator.get_v2_dependency_endpoint", create=True)
    def test_missing_endpoint_raises(self, mock_get_v2):
        """No v2 endpoint raises instead of falling back to v1 or defaults."""
        for missing in (None, v2("")):
            mock_get_v2.return_value = missing
            with self.assertRaises(ValueError):
                ClowderConfigurator.get_dependency_endpoint("rbac", "service", "http://localhost:8111")

    @patch("koku.configurator.get_v2_dependency_endpoint", create=True)
    def test_authenticated_requires_https(self, mock_get_v2):
        """An authenticated endpoint must use https."""
        mock_get_v2.return_value = v2("http://ewgw.example.com:443", True)
        with self.assertRaises(ValueError):
            ClowderConfigurator.get_dependency_endpoint("rbac", "service", "http://localhost:8111")


class TestEnvDependencyEndpoint(SimpleTestCase):
    """Test EnvConfigurator.get_dependency_endpoint."""

    def test_default(self):
        endpoint = EnvConfigurator.get_dependency_endpoint("sources-api", "svc", "http://localhost:3000")
        self.assertEqual(endpoint, DependencyEndpoint("http://localhost:3000"))

    @patch.dict(
        "os.environ",
        {"RBAC_SERVICE_HOST": "rbac-env-host", "RBAC_SERVICE_PORT": "9090", "RBAC_SERVICE_PROTOCOL": "https"},
    )
    def test_env_vars(self):
        endpoint = EnvConfigurator.get_dependency_endpoint("rbac", "service", "http://localhost:8111")
        self.assertEqual(endpoint, DependencyEndpoint("https://rbac-env-host:9090"))


class TestRequestOptions(SimpleTestCase):
    """Test koku.service_auth.request_options."""

    def setUp(self):
        service_auth._credentials = None
        self.addCleanup(setattr, service_auth, "_credentials", None)

    @patch("koku.service_auth.fetch_oidc_discovery")
    def test_unauthenticated_fetches_no_token(self, mock_discovery):
        """Unauthenticated endpoints get no auth and never touch the credentials."""
        self.assertEqual(service_auth.request_options(DependencyEndpoint(IN_CLUSTER)), {"verify": True})
        mock_discovery.assert_not_called()

    def test_ca_certificate(self):
        endpoint = DependencyEndpoint(IN_CLUSTER, ca_certificate="/tmp/ca.crt")
        self.assertEqual(service_auth.request_options(endpoint), {"verify": "/tmp/ca.crt"})

    @patch.dict("os.environ", {"KESSEL_AUTH_CLIENT_ID": "", "KESSEL_AUTH_CLIENT_SECRET": ""})
    def test_authenticated_without_credentials_raises(self):
        with self.assertRaises(RuntimeError):
            service_auth.request_options(DependencyEndpoint(GATEWAY, True))

    @patch("koku.service_auth.OAuth2ClientCredentials")
    @patch("koku.service_auth.fetch_oidc_discovery")
    @patch.dict(
        "os.environ",
        {
            "KESSEL_AUTH_OIDC_ISSUER": "https://sso.example.com",
            "KESSEL_AUTH_CLIENT_ID": "id",
            "KESSEL_AUTH_CLIENT_SECRET": "secret",
        },
    )
    def test_credentials_built_once(self, mock_discovery, mock_creds):
        mock_discovery.return_value.token_endpoint = "https://sso.example.com/token"
        endpoint = DependencyEndpoint(GATEWAY, True)
        service_auth.request_options(endpoint)
        service_auth.request_options(endpoint)
        mock_creds.assert_called_once_with("id", "secret", "https://sso.example.com/token")
        mock_discovery.assert_called_once_with("https://sso.example.com")


class TestRbacAuth(SimpleTestCase):
    """RBAC calls carry the bearer only when the endpoint is authenticated."""

    def _rbac(self, endpoint):
        with patch("koku.rbac.CONFIGURATOR") as configurator:
            configurator.get_dependency_endpoint.return_value = endpoint
            return RbacService()

    @patch("koku.service_auth._get_credentials", return_value=FakeCredentials())
    def test_authenticated_sends_bearer_and_identity(self, _):
        rbac = self._rbac(DependencyEndpoint(GATEWAY, True))
        with requests_mock.mock() as m:
            m.get(f"{GATEWAY}/path", json={"data": []})
            rbac._request_user_access(f"{rbac.base_url}/path", {"x-rh-identity": "ident"})
        headers = m.last_request.headers
        self.assertEqual(headers["Authorization"], "Bearer tok")
        self.assertEqual(headers["x-rh-identity"], "ident")

    @patch("koku.service_auth._get_credentials")
    def test_in_cluster_sends_no_bearer(self, mock_creds):
        rbac = self._rbac(DependencyEndpoint(IN_CLUSTER))
        with requests_mock.mock() as m:
            m.get(f"{IN_CLUSTER}/path", json={"data": []})
            rbac._request_user_access(f"{rbac.base_url}/path", {"x-rh-identity": "ident"})
        self.assertNotIn("Authorization", m.last_request.headers)
        mock_creds.assert_not_called()

    @patch("koku.service_auth._get_credentials", side_effect=RuntimeError("no credentials"))
    def test_token_failure_fails_closed(self, _):
        rbac = self._rbac(DependencyEndpoint(GATEWAY, True))
        with requests_mock.mock() as m:
            with self.assertRaises(RuntimeError):
                rbac._request_user_access(f"{rbac.base_url}/path", {})
        self.assertFalse(m.called)


class TestSourcesAuth(SimpleTestCase):
    """Sources calls use the bearer instead of the PSK when the endpoint is authenticated."""

    def _get(self, endpoint):
        url = f"{endpoint.uri}/probe"
        with patch.object(SourcesConfig, "SOURCES_API_ENDPOINT", endpoint):
            client = SourcesHTTPClient("ident")
            with requests_mock.mock() as m:
                m.get(url, json={})
                client._get_network_response(url, "error")
        return m.last_request.headers

    @patch("koku.service_auth._get_credentials", return_value=FakeCredentials())
    def test_authenticated_bearer_replaces_psk(self, _):
        headers = self._get(DependencyEndpoint(GATEWAY, True))
        self.assertEqual(headers["Authorization"], "Bearer tok")
        self.assertNotIn("x-rh-sources-psk", headers)
        self.assertEqual(headers["x-rh-identity"], "ident")

    def test_in_cluster_uses_psk(self):
        headers = self._get(DependencyEndpoint("http://sources.ns.svc:8000"))
        self.assertEqual(headers["x-rh-sources-psk"], SourcesConfig.SOURCES_PSK)
        self.assertNotIn("Authorization", headers)

    def test_token_failure_fails_closed(self):
        endpoint = DependencyEndpoint(GATEWAY, True)
        with patch("koku.service_auth._get_credentials", side_effect=RuntimeError("no credentials")):
            with self.assertRaises(RuntimeError):
                self._get(endpoint)
