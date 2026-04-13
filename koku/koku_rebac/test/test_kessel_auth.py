#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for koku_rebac.kessel_auth — token provider and credential helpers."""
from unittest.mock import MagicMock
from unittest.mock import patch

from django.test import override_settings
from django.test import SimpleTestCase


class TestIsKesselAuthEnabled(SimpleTestCase):
    """is_kessel_auth_enabled() reflects settings."""

    @override_settings(KESSEL_AUTH_ENABLED=True)
    def test_returns_true_when_enabled(self):
        from koku_rebac.kessel_auth import is_kessel_auth_enabled

        self.assertTrue(is_kessel_auth_enabled())

    @override_settings(KESSEL_AUTH_ENABLED=False)
    def test_returns_false_when_disabled(self):
        from koku_rebac.kessel_auth import is_kessel_auth_enabled

        self.assertFalse(is_kessel_auth_enabled())


class TestGetHttpAuthHeaders(SimpleTestCase):
    """get_http_auth_headers() returns correct dict based on auth state."""

    @override_settings(KESSEL_AUTH_ENABLED=False)
    def test_returns_empty_dict_when_disabled(self):
        from koku_rebac.kessel_auth import get_http_auth_headers

        self.assertEqual(get_http_auth_headers(), {})

    @override_settings(KESSEL_AUTH_ENABLED=True)
    @patch("koku_rebac.kessel_auth.get_kessel_token", return_value="test-jwt-token")
    def test_returns_bearer_header_when_enabled(self, _mock_token):
        from koku_rebac.kessel_auth import get_http_auth_headers

        headers = get_http_auth_headers()
        self.assertEqual(headers, {"Authorization": "Bearer test-jwt-token"})


class TestGetGrpcCallCredentials(SimpleTestCase):
    """get_grpc_call_credentials() returns credentials or None."""

    @override_settings(KESSEL_AUTH_ENABLED=False)
    def test_returns_none_when_disabled(self):
        from koku_rebac.kessel_auth import get_grpc_call_credentials

        self.assertIsNone(get_grpc_call_credentials())

    @override_settings(KESSEL_AUTH_ENABLED=True)
    @patch("koku_rebac.kessel_auth.get_kessel_token", return_value="grpc-jwt")
    def test_returns_credentials_when_enabled(self, _mock_token):
        import grpc

        from koku_rebac.kessel_auth import get_grpc_call_credentials

        creds = get_grpc_call_credentials()
        self.assertIsInstance(creds, grpc.CallCredentials)


class TestTokenProvider(SimpleTestCase):
    """_TokenProvider caching and refresh behaviour."""

    def setUp(self):
        from koku_rebac.kessel_auth import _reset_provider

        _reset_provider()

    def tearDown(self):
        from koku_rebac.kessel_auth import _reset_provider

        _reset_provider()

    @override_settings(
        KESSEL_AUTH_ENABLED=True,
        KESSEL_AUTH_CLIENT_ID="test-client",
        KESSEL_AUTH_CLIENT_SECRET="test-secret",
        KESSEL_AUTH_OIDC_ISSUER="http://keycloak:8080/realms/test",
    )
    @patch("koku_rebac.kessel_auth.requests.post")
    def test_fetches_token_on_first_call(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"access_token": "fresh-token", "expires_in": 300},
            raise_for_status=lambda: None,
        )

        from koku_rebac.kessel_auth import get_kessel_token

        token = get_kessel_token()
        self.assertEqual(token, "fresh-token")
        mock_post.assert_called_once()

    @override_settings(
        KESSEL_AUTH_ENABLED=True,
        KESSEL_AUTH_CLIENT_ID="test-client",
        KESSEL_AUTH_CLIENT_SECRET="test-secret",
        KESSEL_AUTH_OIDC_ISSUER="http://keycloak:8080/realms/test",
    )
    @patch("koku_rebac.kessel_auth.requests.post")
    def test_caches_token_within_expiry(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"access_token": "cached-token", "expires_in": 300},
            raise_for_status=lambda: None,
        )

        from koku_rebac.kessel_auth import get_kessel_token

        get_kessel_token()
        get_kessel_token()
        get_kessel_token()
        self.assertEqual(mock_post.call_count, 1)

    @override_settings(
        KESSEL_AUTH_ENABLED=True,
        KESSEL_AUTH_CLIENT_ID="test-client",
        KESSEL_AUTH_CLIENT_SECRET="test-secret",
        KESSEL_AUTH_OIDC_ISSUER="http://keycloak:8080/realms/test",
    )
    @patch("koku_rebac.kessel_auth.requests.post")
    @patch("koku_rebac.kessel_auth.time.time")
    def test_refreshes_token_when_expired(self, mock_time, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"access_token": "new-token", "expires_in": 300},
            raise_for_status=lambda: None,
        )
        mock_time.side_effect = [
            1000.0,
            1000.0,
            1000.0,  # first call: check, lock-check, after-refresh
            1400.0,  # second call: expired (1000+300-30=1270 < 1400)
            1400.0,
            1400.0,  # second call: lock-check, after-refresh
        ]

        from koku_rebac.kessel_auth import get_kessel_token

        get_kessel_token()
        get_kessel_token()
        self.assertEqual(mock_post.call_count, 2)

    @override_settings(
        KESSEL_AUTH_ENABLED=True,
        KESSEL_AUTH_CLIENT_ID="test-client",
        KESSEL_AUTH_CLIENT_SECRET="test-secret",
        KESSEL_AUTH_OIDC_ISSUER="http://keycloak:8080/realms/test",
    )
    @patch("koku_rebac.kessel_auth.requests.post")
    def test_raises_on_token_failure(self, mock_post):
        from requests.exceptions import ConnectionError as ReqConnectionError

        mock_post.side_effect = ReqConnectionError("connection refused")

        from koku_rebac.kessel_auth import get_kessel_token

        with self.assertRaises(ReqConnectionError):
            get_kessel_token()

    @override_settings(
        KESSEL_AUTH_ENABLED=True,
        KESSEL_AUTH_CLIENT_ID="test-client",
        KESSEL_AUTH_CLIENT_SECRET="test-secret",
        KESSEL_AUTH_OIDC_ISSUER="http://keycloak:8080/realms/test",
    )
    @patch("koku_rebac.kessel_auth.requests.post")
    def test_sends_correct_client_credentials(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"access_token": "t", "expires_in": 300},
            raise_for_status=lambda: None,
        )

        from koku_rebac.kessel_auth import get_kessel_token

        get_kessel_token()
        call_kwargs = mock_post.call_args
        self.assertEqual(
            call_kwargs.kwargs["data"]["client_id"],
            "test-client",
        )
        self.assertEqual(
            call_kwargs.kwargs["data"]["client_secret"],
            "test-secret",
        )
        self.assertEqual(
            call_kwargs.kwargs["data"]["grant_type"],
            "client_credentials",
        )
        self.assertIn("realms/test/protocol/openid-connect/token", call_kwargs.args[0])
