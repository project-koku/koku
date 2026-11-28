#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Events (koku-events) provider implementation for Koku."""
import logging

import requests
from django.conf import settings
from rest_framework import serializers

from ..provider_interface import ProviderInterface
from api.common import error_obj
from api.models import Provider

LOG = logging.getLogger(__name__)


def resolve_events_endpoint(credentials, data_source):
    """Resolve effective (base_url, auth_token, ca_cert) from source config or settings."""
    creds = credentials or {}
    ds = data_source or {}
    base_url = (ds.get("url") or getattr(settings, "COST_EVENTS_URL", "") or "").strip().rstrip("/")
    token = (creds.get("token") or getattr(settings, "COST_EVENTS_AUTH_TOKEN", "") or "").strip()
    ca_cert = (ds.get("ca_cert") or getattr(settings, "COST_EVENTS_CA_CERT", "") or "").strip()
    return base_url, token, ca_cert


class EventsProvider(ProviderInterface):
    """Pre-rated event-cost provider pulling daily rollups from koku-events."""

    def name(self):
        """Return name of the provider."""
        return Provider.PROVIDER_EVENTS

    def cost_usage_source_is_reachable(self, credentials, data_source):
        """Verify that the koku-events export API is reachable and accepts credentials."""
        base_url, token, ca_cert = resolve_events_endpoint(credentials, data_source)
        if not base_url:
            raise serializers.ValidationError(
                error_obj("billing_source.url", "Events source URL is required (or configure COST_EVENTS_URL).")
            )

        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        verify = ca_cert if ca_cert else True
        timeout = getattr(settings, "COST_EVENTS_HTTP_TIMEOUT", 60)
        url = f"{base_url}/api/v1/export/dirty-dates"
        params = {}
        if data_source and data_source.get("tenant_id"):
            params["tenant_id"] = data_source["tenant_id"]

        try:
            response = requests.get(url, headers=headers, params=params, timeout=timeout, verify=verify)
            if response.status_code in (401, 403):
                raise serializers.ValidationError(
                    error_obj("authentication.token", f"Events source authentication failed ({response.status_code}).")
                )
            response.raise_for_status()
        except serializers.ValidationError:
            raise
        except requests.RequestException as err:
            LOG.warning("Events source reachability check failed for %s: %s", url, err)
            raise serializers.ValidationError(
                error_obj("billing_source.url", f"Unable to reach Events source at {base_url}: {err}")
            ) from err

        return True

    def infra_type_implementation(self, provider_uuid, schema_name):
        """Return infrastructure type (none for standalone Events source)."""
        return None

    def infra_key_list_implementation(self, infrastructure_type, schema_name):
        """Return empty list (Phase 3 will add OCP-on-Events cluster_id correlation)."""
        return []


class EventsLocalProvider(EventsProvider):
    """Local development Events provider skipping remote connectivity checks."""

    def name(self):
        """Return name of the local Events provider."""
        return Provider.PROVIDER_EVENTS_LOCAL

    def cost_usage_source_is_reachable(self, credentials, data_source):
        """Local provider does not require a live koku-events endpoint."""
        return True
