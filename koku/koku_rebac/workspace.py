#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Workspace resolution for Kessel authorization.

On-prem: org_id IS the workspace_id (ShimResolver).
SaaS: RBAC v2 API provides the default workspace (RbacV2Resolver).
"""
import logging
import threading
import time
from typing import Protocol

import requests
from django.conf import settings

LOG = logging.getLogger(__name__)

_REFRESH_BUFFER_SECONDS = 30


class WorkspaceResolver(Protocol):
    """Protocol for resolving an org_id to a Kessel workspace_id."""

    def resolve(self, org_id: str) -> str:
        ...


class ShimResolver:
    """On-prem resolver: org_id maps directly to workspace_id."""

    def resolve(self, org_id: str) -> str:
        return org_id


class RbacV2Resolver:
    """SaaS resolver: queries RBAC v2 for the default workspace.

    Uses OAuth2 client_credentials token (NOT the user's x-rh-identity)
    per Kessel migration guide -- the service must use its own authority.
    """

    def __init__(self, rbac_url: str, token_url: str, client_id: str, client_secret: str) -> None:
        self._rbac_url = rbac_url.rstrip("/")
        if not token_url or token_url.startswith("/"):
            raise ValueError(f"RbacV2Resolver: invalid token URL '{token_url}' -- check KESSEL_AUTH_OIDC_ISSUER")
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._cached_token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = threading.Lock()

    def _get_access_token(self) -> str:
        """Obtain an OAuth2 access token via client_credentials grant."""
        now = time.time()
        if self._cached_token and now < self._token_expires_at - _REFRESH_BUFFER_SECONDS:
            return self._cached_token

        with self._token_lock:
            if self._cached_token and time.time() < self._token_expires_at - _REFRESH_BUFFER_SECONDS:
                return self._cached_token

            resp = requests.post(
                self._token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            self._cached_token = data.get("access_token")
            if not self._cached_token:
                raise ValueError("OAuth2 token response missing 'access_token'")
            self._token_expires_at = time.time() + data.get("expires_in", 300)
            return self._cached_token

    def resolve(self, org_id: str) -> str:
        """Query RBAC v2 for the default workspace of the given org."""
        token = self._get_access_token()
        url = f"{self._rbac_url}/api/rbac/v2/workspaces/"
        resp = requests.get(
            url,
            params={"type": "default"},
            headers={
                "Authorization": f"Bearer {token}",
                "x-rh-rbac-org-id": org_id,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results") or data.get("data") or []
        if not results:
            raise ValueError(f"No default workspace found for org {org_id}")

        workspace_id = results[0].get("id")
        if not workspace_id:
            raise ValueError(f"Workspace entry missing 'id' for org {org_id}")
        return workspace_id


def get_workspace_resolver() -> WorkspaceResolver:
    """Factory: return the resolver for the current deployment mode."""
    if getattr(settings, "ONPREM", False):
        return ShimResolver()
    return RbacV2Resolver(
        rbac_url=getattr(settings, "RBAC_V2_URL", "http://localhost:8000"),
        token_url=f"{getattr(settings, 'KESSEL_AUTH_OIDC_ISSUER', '')}/protocol/openid-connect/token",
        client_id=getattr(settings, "KESSEL_AUTH_CLIENT_ID", ""),
        client_secret=getattr(settings, "KESSEL_AUTH_CLIENT_SECRET", ""),
    )
