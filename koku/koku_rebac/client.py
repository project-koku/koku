#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Thread-safe singleton gRPC client for Kessel Inventory API v1beta2."""
import logging
import threading

import grpc
from django.conf import settings
from kessel.inventory.v1beta2 import inventory_service_pb2_grpc

from api.common import log_json
from koku_rebac.kessel_auth import get_grpc_call_credentials

LOG = logging.getLogger(__name__)

_client_instance: "KesselClient | None" = None
_client_lock = threading.Lock()


def _build_channel_credentials(ca_path: str) -> grpc.ChannelCredentials:
    """Build TLS credentials, optionally loading a custom CA certificate."""
    if ca_path:
        try:
            with open(ca_path, "rb") as f:
                root_certs = f.read()
        except FileNotFoundError:
            LOG.error(log_json(msg="Kessel CA file not found, falling back to system roots", ca_path=ca_path))
            return grpc.ssl_channel_credentials()
        return grpc.ssl_channel_credentials(root_certificates=root_certs)
    return grpc.ssl_channel_credentials()


class KesselClient:
    """Wraps the Kessel Inventory API v1beta2 gRPC stub.

    This is the only Kessel client Koku needs -- all authorization
    checks (Check, StreamedListObjects) and resource reporting
    (ReportResource) go through the Inventory API.
    """

    def __init__(self) -> None:
        inventory_cfg: dict = settings.KESSEL_INVENTORY_CONFIG
        ca_path: str = getattr(settings, "KESSEL_CA_PATH", "")

        self._channel = self._build_channel(inventory_cfg, ca_path)
        self.inventory_stub = inventory_service_pb2_grpc.KesselInventoryServiceStub(self._channel)

    @staticmethod
    def _build_channel(config: dict, ca_path: str) -> grpc.Channel:
        """Create a gRPC channel to the Kessel Inventory API.

        When KESSEL_AUTH_ENABLED is True the channel carries per-RPC
        call credentials (OAuth2 Bearer token) so the Inventory API
        can verify the caller's identity.
        """
        target = f"{config['host']}:{config['port']}"
        call_creds = get_grpc_call_credentials()

        if ca_path:
            channel_creds = _build_channel_credentials(ca_path)
            if call_creds:
                channel_creds = grpc.composite_channel_credentials(channel_creds, call_creds)
            return grpc.secure_channel(target, channel_creds)

        if call_creds:
            # Auth enabled but no TLS -- use local credentials so
            # call_credentials can ride on an otherwise-insecure channel.
            channel_creds = grpc.composite_channel_credentials(grpc.local_channel_credentials(), call_creds)
            return grpc.secure_channel(target, channel_creds)

        return grpc.insecure_channel(target)


def get_kessel_client() -> KesselClient:
    """Return (or create) the process-wide singleton KesselClient.

    Uses double-checked locking to avoid acquiring the lock on every call.
    """
    global _client_instance
    if _client_instance is None:
        with _client_lock:
            if _client_instance is None:
                _client_instance = KesselClient()
                LOG.info(log_json(msg="KesselClient initialised (Inventory API v1beta2 only)"))
    return _client_instance


def _reset_client() -> None:
    """Tear down the singleton -- intended for test isolation only."""
    global _client_instance
    with _client_lock:
        if _client_instance is not None:
            try:
                _client_instance._channel.close()
            except Exception:
                LOG.debug(log_json(msg="Error closing Kessel gRPC channel during reset"), exc_info=True)
        _client_instance = None
