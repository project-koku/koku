#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Service-account bearer auth for calls to Clowder v2 dependencies."""
import threading

from kessel.auth import fetch_oidc_discovery
from kessel.auth import oauth2_auth_request
from kessel.auth import OAuth2ClientCredentials

from .env import ENVIRONMENT

_credentials = None
_lock = threading.Lock()


def _get_credentials():
    """Build the shared credentials object on first use; fail if it is not configured."""
    global _credentials
    with _lock:
        if _credentials is None:
            issuer = ENVIRONMENT.get_value("KESSEL_AUTH_OIDC_ISSUER", default="")
            client_id = ENVIRONMENT.get_value("KESSEL_AUTH_CLIENT_ID", default="")
            client_secret = ENVIRONMENT.get_value("KESSEL_AUTH_CLIENT_SECRET", default="")
            if not (issuer and client_id and client_secret):
                raise RuntimeError(
                    "Authenticated dependency endpoint requires KESSEL_AUTH_OIDC_ISSUER, "
                    "KESSEL_AUTH_CLIENT_ID and KESSEL_AUTH_CLIENT_SECRET"
                )
            token_endpoint = fetch_oidc_discovery(issuer).token_endpoint
            _credentials = OAuth2ClientCredentials(client_id, client_secret, token_endpoint)
        return _credentials


def request_options(endpoint):
    """Return requests kwargs (TLS trust and, when authenticated, the bearer) for a DependencyEndpoint."""
    options = {"verify": endpoint.ca_certificate or True}
    if endpoint.authenticated:
        options["auth"] = oauth2_auth_request(_get_credentials())
    return options
