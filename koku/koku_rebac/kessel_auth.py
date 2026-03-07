#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Thread-safe OAuth2 token provider for Kessel API authentication.

When KESSEL_AUTH_ENABLED is True, Koku authenticates to the Kessel
Relations API (HTTP) and Inventory API (gRPC) using JWTs obtained
via the OAuth2 client_credentials grant from Keycloak.

The token is cached in memory and refreshed transparently when it
approaches expiry.  All public helpers are no-ops when auth is
disabled, so callers don't need conditional logic.
"""
from __future__ import annotations

import logging
import threading
import time

import grpc
import requests
from django.conf import settings

from api.common import log_json

LOG = logging.getLogger(__name__)

_REFRESH_BUFFER_SECONDS = 30
_TOKEN_REQUEST_TIMEOUT = 5


class _TokenProvider:
    """Acquires and caches an OAuth2 access token (client_credentials)."""

    def __init__(self) -> None:
        self._token: str = ""
        self._expires_at: float = 0.0
        self._lock = threading.Lock()

    def get_token(self) -> str:
        """Return a valid access token, refreshing if needed."""
        now = time.time()
        if now < self._expires_at - _REFRESH_BUFFER_SECONDS:
            return self._token

        with self._lock:
            if time.time() < self._expires_at - _REFRESH_BUFFER_SECONDS:
                return self._token
            self._refresh()
            return self._token

    def _refresh(self) -> None:
        token_url = getattr(settings, "KESSEL_AUTH_TOKEN_URL", "") or (
            f"{settings.KESSEL_AUTH_OIDC_ISSUER}/protocol/openid-connect/token"
        )
        try:
            resp = requests.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.KESSEL_AUTH_CLIENT_ID,
                    "client_secret": settings.KESSEL_AUTH_CLIENT_SECRET,
                },
                timeout=_TOKEN_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data["access_token"]
            self._expires_at = time.time() + data.get("expires_in", 300)
            LOG.debug(log_json(msg="Kessel auth token refreshed", expires_in=data.get("expires_in")))
        except Exception:
            LOG.error(log_json(msg="Failed to refresh Kessel auth token", url=token_url), exc_info=True)
            raise


_provider: _TokenProvider | None = None
_provider_lock = threading.Lock()


def _get_provider() -> _TokenProvider:
    global _provider
    if _provider is None:
        with _provider_lock:
            if _provider is None:
                _provider = _TokenProvider()
    return _provider


def get_kessel_token() -> str:
    """Return a valid Kessel access token.  Raises if token acquisition fails."""
    return _get_provider().get_token()


def is_kessel_auth_enabled() -> bool:
    """Return True when Kessel API authentication is configured.

    On-prem deployments always have Kessel auth enabled.
    """
    return getattr(settings, "KESSEL_AUTH_ENABLED", False)


def get_http_auth_headers() -> dict[str, str]:
    """Return HTTP headers with Bearer token, or empty dict if auth is disabled."""
    if not is_kessel_auth_enabled():
        return {}
    return {"Authorization": f"Bearer {get_kessel_token()}"}


def get_grpc_call_credentials() -> grpc.CallCredentials | None:
    """Return gRPC call credentials, or None if auth is disabled.

    The credentials use a callback that fetches (or returns cached)
    the access token on each RPC, ensuring automatic refresh.
    """
    if not is_kessel_auth_enabled():
        return None

    class _Plugin(grpc.AuthMetadataPlugin):
        def __call__(self, context, callback):
            try:
                token = get_kessel_token()
                callback((("authorization", f"Bearer {token}"),), None)
            except Exception as exc:
                callback((), exc)

    return grpc.metadata_call_credentials(_Plugin())


def _reset_provider() -> None:
    """Tear down the singleton -- for test isolation only."""
    global _provider
    with _provider_lock:
        _provider = None
