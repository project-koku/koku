#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the Kessel gRPC client singleton (Inventory API v1beta2 only)."""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "koku.test_settings_lite")

import django  # noqa: E402

django.setup()

from unittest.mock import MagicMock, patch  # noqa: E402

from django.test import SimpleTestCase  # noqa: E402

import koku_rebac.client  # noqa: E402, F401


class TestKesselClientImport(SimpleTestCase):
    """The client module must be importable."""

    def test_import_kessel_client_class(self):
        from koku_rebac.client import KesselClient

        self.assertIsNotNone(KesselClient)

    def test_import_get_kessel_client(self):
        from koku_rebac.client import get_kessel_client

        self.assertTrue(callable(get_kessel_client))

    def test_import_reset_client(self):
        from koku_rebac.client import _reset_client

        self.assertTrue(callable(_reset_client))


class TestKesselClientStubs(SimpleTestCase):
    """Verify the client exposes ONLY the Inventory API stub."""

    @patch("koku_rebac.client.KesselClient._build_channel")
    def test_has_inventory_stub(self, mock_build):
        mock_build.return_value = MagicMock()
        from koku_rebac.client import KesselClient

        client = KesselClient()
        self.assertIsNotNone(client.inventory_stub)

    @patch("koku_rebac.client.KesselClient._build_channel")
    def test_no_relations_api_stubs(self, mock_build):
        """Relations API stubs must NOT exist on the client."""
        mock_build.return_value = MagicMock()
        from koku_rebac.client import KesselClient

        client = KesselClient()
        self.assertFalse(hasattr(client, "check_stub"))
        self.assertFalse(hasattr(client, "lookup_stub"))
        self.assertFalse(hasattr(client, "tuples_stub"))


class TestKesselClientSingleton(SimpleTestCase):
    """get_kessel_client() must return the same instance."""

    @patch("koku_rebac.client.KesselClient._build_channel")
    def test_singleton_returns_same_instance(self, mock_build):
        mock_build.return_value = MagicMock()
        from koku_rebac.client import _reset_client, get_kessel_client

        _reset_client()
        a = get_kessel_client()
        b = get_kessel_client()
        self.assertIs(a, b)
        _reset_client()

    @patch("koku_rebac.client.KesselClient._build_channel")
    def test_reset_creates_new_instance(self, mock_build):
        mock_build.return_value = MagicMock()
        from koku_rebac.client import _reset_client, get_kessel_client

        _reset_client()
        a = get_kessel_client()
        _reset_client()
        b = get_kessel_client()
        self.assertIsNot(a, b)
        _reset_client()


class TestBuildChannel(SimpleTestCase):
    """_build_channel creates insecure or TLS channel based on CA path."""

    @patch("koku_rebac.client.grpc.insecure_channel")
    def test_insecure_channel_when_no_ca_path(self, mock_insecure):
        mock_insecure.return_value = MagicMock()
        from koku_rebac.client import KesselClient

        config = {"host": "localhost", "port": 9081}
        ch = KesselClient._build_channel(config, ca_path="")
        mock_insecure.assert_called_once_with("localhost:9081")
        self.assertIsNotNone(ch)

    @patch("koku_rebac.client.grpc.secure_channel")
    @patch("koku_rebac.client._build_channel_credentials")
    def test_secure_channel_when_ca_path_set(self, mock_creds_fn, mock_secure):
        mock_creds_fn.return_value = MagicMock()
        mock_secure.return_value = MagicMock()
        from koku_rebac.client import KesselClient

        config = {"host": "kessel.example.com", "port": 443}
        ch = KesselClient._build_channel(config, ca_path="/etc/pki/tls/ca.pem")
        mock_creds_fn.assert_called_once_with("/etc/pki/tls/ca.pem")
        mock_secure.assert_called_once()
        self.assertIsNotNone(ch)
