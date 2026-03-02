#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the AccessProvider abstraction and implementations."""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "koku.test_settings_lite")

import django  # noqa: E402

django.setup()

from unittest.mock import MagicMock, patch, PropertyMock  # noqa: E402

from django.test import SimpleTestCase, override_settings  # noqa: E402


class TestAccessProviderImport(SimpleTestCase):
    """The access_provider module must be importable."""

    def test_import_kessel_access_provider(self):
        from koku_rebac.access_provider import KesselAccessProvider

        self.assertIsNotNone(KesselAccessProvider)

    def test_import_rbac_access_provider(self):
        from koku_rebac.access_provider import RBACAccessProvider

        self.assertIsNotNone(RBACAccessProvider)

    def test_import_get_access_provider(self):
        from koku_rebac.access_provider import get_access_provider

        self.assertTrue(callable(get_access_provider))


class TestGetAccessProviderFactory(SimpleTestCase):
    """get_access_provider returns the right backend based on settings."""

    @override_settings(AUTHORIZATION_BACKEND="rbac")
    def test_returns_rbac_provider_by_default(self):
        from koku_rebac.access_provider import RBACAccessProvider, get_access_provider

        provider = get_access_provider()
        self.assertIsInstance(provider, RBACAccessProvider)

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    def test_returns_kessel_provider_for_rebac(self):
        from koku_rebac.access_provider import KesselAccessProvider, get_access_provider

        provider = get_access_provider()
        self.assertIsInstance(provider, KesselAccessProvider)


class TestRBACAccessProvider(SimpleTestCase):
    """RBACAccessProvider wraps the existing RbacService."""

    @patch("koku_rebac.access_provider.RbacService")
    def test_delegates_to_rbac_service(self, mock_cls):
        mock_svc = MagicMock()
        mock_svc.get_access_for_user.return_value = {"openshift.cluster": {"read": ["*"]}}
        mock_cls.return_value = mock_svc

        from koku_rebac.access_provider import RBACAccessProvider

        provider = RBACAccessProvider()
        user = MagicMock()
        result = provider.get_access_for_user(user)
        mock_svc.get_access_for_user.assert_called_once_with(user)
        self.assertEqual(result, {"openshift.cluster": {"read": ["*"]}})

    @patch("koku_rebac.access_provider.RbacService")
    def test_exposes_cache_ttl(self, mock_cls):
        mock_svc = MagicMock()
        mock_svc.get_cache_ttl.return_value = 300
        mock_cls.return_value = mock_svc

        from koku_rebac.access_provider import RBACAccessProvider

        provider = RBACAccessProvider()
        self.assertEqual(provider.get_cache_ttl(), 300)


class TestKesselAccessProvider(SimpleTestCase):
    """KesselAccessProvider queries Kessel Inventory API v1beta2."""

    def _make_user(self, user_id="user123", org_id="org123"):
        user = MagicMock()
        user.user_id = user_id
        user.username = f"username-{user_id}"
        user.customer.org_id = org_id
        return user

    def _make_check_response(self, allowed):
        from kessel.inventory.v1beta2 import allowed_pb2

        resp = MagicMock()
        if allowed:
            resp.allowed = allowed_pb2.ALLOWED_TRUE
        else:
            resp.allowed = allowed_pb2.ALLOWED_FALSE
        return resp

    @patch("koku_rebac.access_provider.get_workspace_resolver")
    @patch("koku_rebac.access_provider.get_kessel_client")
    def test_returns_dict_with_resource_types(self, mock_get_client, mock_get_resolver):
        """All RESOURCE_TYPES keys are present even when no permissions are granted."""
        mock_client = MagicMock()
        mock_client.inventory_stub.Check.return_value = self._make_check_response(False)
        mock_client.inventory_stub.StreamedListObjects.side_effect = lambda *a, **kw: iter([])
        mock_get_client.return_value = mock_client

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = "org123"
        mock_get_resolver.return_value = mock_resolver

        from koku_rebac.access_provider import KesselAccessProvider

        provider = KesselAccessProvider()
        result = provider.get_access_for_user(self._make_user())

        self.assertIsInstance(result, dict)
        self.assertIn("openshift.cluster", result)
        self.assertIn("cost_model", result)
        self.assertIn("settings", result)
        self.assertEqual(result["openshift.cluster"]["read"], [])

    @patch("koku_rebac.access_provider.get_workspace_resolver")
    @patch("koku_rebac.access_provider.get_kessel_client")
    def test_check_uses_workspace_not_tenant(self, mock_get_client, mock_get_resolver):
        """CheckRequest targets rbac/workspace with workspace_id, not rbac/tenant."""
        mock_client = MagicMock()
        mock_client.inventory_stub.Check.return_value = self._make_check_response(False)
        mock_client.inventory_stub.StreamedListObjects.side_effect = lambda *a, **kw: iter([])
        mock_get_client.return_value = mock_client

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = "ws-42"
        mock_get_resolver.return_value = mock_resolver

        from koku_rebac.access_provider import KesselAccessProvider

        provider = KesselAccessProvider()
        provider.get_access_for_user(self._make_user(user_id="alice", org_id="myorg"))

        mock_resolver.resolve.assert_called_once_with("myorg")

        first_call = mock_client.inventory_stub.Check.call_args_list[0]
        req = first_call[0][0]
        self.assertEqual(req.object.resource_type, "workspace")
        self.assertEqual(req.object.resource_id, "ws-42")
        self.assertEqual(req.object.reporter.type, "rbac")

    @patch("koku_rebac.access_provider.get_workspace_resolver")
    @patch("koku_rebac.access_provider.get_kessel_client")
    def test_subject_uses_user_id_not_username(self, mock_get_client, mock_get_resolver):
        """SubjectReference uses redhat/{user_id}, not the username."""
        mock_client = MagicMock()
        mock_client.inventory_stub.Check.return_value = self._make_check_response(False)
        mock_client.inventory_stub.StreamedListObjects.side_effect = lambda *a, **kw: iter([])
        mock_get_client.return_value = mock_client

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = "org1"
        mock_get_resolver.return_value = mock_resolver

        from koku_rebac.access_provider import KesselAccessProvider

        provider = KesselAccessProvider()
        provider.get_access_for_user(self._make_user(user_id="uid-999", org_id="org1"))

        first_call = mock_client.inventory_stub.Check.call_args_list[0]
        req = first_call[0][0]
        self.assertEqual(req.subject.resource.resource_type, "principal")
        self.assertEqual(req.subject.resource.resource_id, "redhat/uid-999")
        self.assertEqual(req.subject.resource.reporter.type, "rbac")

    @patch("koku_rebac.access_provider.get_workspace_resolver")
    @patch("koku_rebac.access_provider.get_kessel_client")
    def test_view_permission_suffix_for_read(self, mock_get_client, mock_get_resolver):
        """Read operations use _view compound permission, not _read."""
        mock_client = MagicMock()
        mock_client.inventory_stub.Check.return_value = self._make_check_response(False)
        mock_client.inventory_stub.StreamedListObjects.side_effect = lambda *a, **kw: iter([])
        mock_get_client.return_value = mock_client

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = "org1"
        mock_get_resolver.return_value = mock_resolver

        from koku_rebac.access_provider import KesselAccessProvider

        provider = KesselAccessProvider()
        provider.get_access_for_user(self._make_user())

        check_calls = mock_client.inventory_stub.Check.call_args_list
        permissions = [call[0][0].relation for call in check_calls]
        self.assertIn("cost_management_aws_account_view", permissions)
        self.assertNotIn("cost_management_aws_account_read", permissions)

    @patch("koku_rebac.access_provider.get_workspace_resolver")
    @patch("koku_rebac.access_provider.get_kessel_client")
    def test_edit_permission_suffix_for_write(self, mock_get_client, mock_get_resolver):
        """Write operations use _edit compound permission, not _write."""
        mock_client = MagicMock()
        mock_client.inventory_stub.Check.return_value = self._make_check_response(False)
        mock_client.inventory_stub.StreamedListObjects.side_effect = lambda *a, **kw: iter([])
        mock_get_client.return_value = mock_client

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = "org1"
        mock_get_resolver.return_value = mock_resolver

        from koku_rebac.access_provider import KesselAccessProvider

        provider = KesselAccessProvider()
        provider.get_access_for_user(self._make_user())

        check_calls = mock_client.inventory_stub.Check.call_args_list
        permissions = [call[0][0].relation for call in check_calls]
        self.assertIn("cost_management_cost_model_edit", permissions)
        self.assertIn("cost_management_settings_edit", permissions)
        self.assertNotIn("cost_management_cost_model_write", permissions)
        self.assertNotIn("cost_management_settings_write", permissions)

    @patch("koku_rebac.access_provider.get_workspace_resolver")
    @patch("koku_rebac.access_provider.get_kessel_client")
    def test_granted_read_returns_wildcard(self, mock_get_client, mock_get_resolver):
        """Check ALLOWED_TRUE grants wildcard ["*"] access for read via fallback."""
        mock_client = MagicMock()

        def fake_check(request, **kwargs):
            if request.relation == "cost_management_aws_account_view":
                return self._make_check_response(True)
            return self._make_check_response(False)

        mock_client.inventory_stub.Check.side_effect = fake_check
        mock_client.inventory_stub.StreamedListObjects.side_effect = lambda *a, **kw: iter([])
        mock_get_client.return_value = mock_client

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = "org1"
        mock_get_resolver.return_value = mock_resolver

        from koku_rebac.access_provider import KesselAccessProvider

        provider = KesselAccessProvider()
        result = provider.get_access_for_user(self._make_user())

        self.assertEqual(result["aws.account"]["read"], ["*"])
        self.assertEqual(result["gcp.account"]["read"], [])

    @patch("koku_rebac.access_provider.get_workspace_resolver")
    @patch("koku_rebac.access_provider.get_kessel_client")
    def test_write_grants_read_parity(self, mock_get_client, mock_get_resolver):
        """When _edit is ALLOWED, read is also granted ["*"] (RBAC v1 parity)."""
        mock_client = MagicMock()

        def fake_check(request, **kwargs):
            if request.relation == "cost_management_cost_model_edit":
                return self._make_check_response(True)
            return self._make_check_response(False)

        mock_client.inventory_stub.Check.side_effect = fake_check
        mock_client.inventory_stub.StreamedListObjects.side_effect = lambda *a, **kw: iter([])
        mock_get_client.return_value = mock_client

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = "org1"
        mock_get_resolver.return_value = mock_resolver

        from koku_rebac.access_provider import KesselAccessProvider

        provider = KesselAccessProvider()
        result = provider.get_access_for_user(self._make_user())

        self.assertEqual(result["cost_model"]["write"], ["*"])
        self.assertEqual(result["cost_model"]["read"], ["*"])

    @patch("koku_rebac.access_provider.get_workspace_resolver")
    @patch("koku_rebac.access_provider.get_kessel_client")
    def test_streamed_list_objects_returns_resource_ids(self, mock_get_client, mock_get_resolver):
        """StreamedListObjects returns specific resource IDs for per-resource types."""
        mock_client = MagicMock()
        mock_client.inventory_stub.Check.return_value = self._make_check_response(False)

        mock_response_1 = MagicMock()
        mock_response_1.object.resource_id = "cluster-uuid-1"
        mock_response_2 = MagicMock()
        mock_response_2.object.resource_id = "cluster-uuid-3"

        def fake_stream(request, **kwargs):
            if request.object_type.resource_type == "openshift_cluster":
                return iter([mock_response_1, mock_response_2])
            return iter([])

        mock_client.inventory_stub.StreamedListObjects.side_effect = fake_stream
        mock_get_client.return_value = mock_client

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = "org1"
        mock_get_resolver.return_value = mock_resolver

        from koku_rebac.access_provider import KesselAccessProvider

        provider = KesselAccessProvider()
        result = provider.get_access_for_user(self._make_user())

        self.assertEqual(result["openshift.cluster"]["read"], ["cluster-uuid-1", "cluster-uuid-3"])

    @patch("koku_rebac.access_provider.get_workspace_resolver")
    @patch("koku_rebac.access_provider.get_kessel_client")
    def test_empty_stream_and_denied_check_returns_empty(self, mock_get_client, mock_get_resolver):
        """When StreamedListObjects returns nothing and Check denies, access is empty."""
        mock_client = MagicMock()
        mock_client.inventory_stub.Check.return_value = self._make_check_response(False)
        mock_client.inventory_stub.StreamedListObjects.side_effect = lambda *a, **kw: iter([])
        mock_get_client.return_value = mock_client

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = "org1"
        mock_get_resolver.return_value = mock_resolver

        from koku_rebac.access_provider import KesselAccessProvider

        provider = KesselAccessProvider()
        result = provider.get_access_for_user(self._make_user())

        self.assertEqual(result["openshift.cluster"]["read"], [])
        self.assertEqual(result["openshift.node"]["read"], [])
        self.assertEqual(result["openshift.project"]["read"], [])
        self.assertEqual(result["aws.account"]["read"], [])
        self.assertEqual(result["cost_model"]["read"], [])

    @patch("koku_rebac.access_provider.get_workspace_resolver")
    @patch("koku_rebac.access_provider.get_kessel_client")
    def test_check_exception_logs_and_continues(self, mock_get_client, mock_get_resolver):
        """Check failure for one type does not prevent others from populating."""
        mock_client = MagicMock()

        def fake_check(request, **kwargs):
            if "settings" in request.relation:
                raise Exception("Kessel connection lost")
            if request.relation == "cost_management_aws_account_view":
                return self._make_check_response(True)
            return self._make_check_response(False)

        mock_client.inventory_stub.Check.side_effect = fake_check
        mock_client.inventory_stub.StreamedListObjects.side_effect = lambda *a, **kw: iter([])
        mock_get_client.return_value = mock_client

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = "org1"
        mock_get_resolver.return_value = mock_resolver

        from koku_rebac.access_provider import KesselAccessProvider

        provider = KesselAccessProvider()
        result = provider.get_access_for_user(self._make_user())

        self.assertEqual(result["aws.account"]["read"], ["*"])
        self.assertEqual(result["settings"]["read"], [])
        self.assertEqual(result["settings"]["write"], [])

    @patch("koku_rebac.access_provider.get_workspace_resolver")
    @patch("koku_rebac.access_provider.get_kessel_client")
    def test_reporter_reference_always_set(self, mock_get_client, mock_get_resolver):
        """ReporterReference is never nil -- mitigates Kessel nil-panic risk."""
        mock_client = MagicMock()
        mock_client.inventory_stub.Check.return_value = self._make_check_response(False)
        mock_client.inventory_stub.StreamedListObjects.side_effect = lambda *a, **kw: iter([])
        mock_get_client.return_value = mock_client

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = "org1"
        mock_get_resolver.return_value = mock_resolver

        from koku_rebac.access_provider import KesselAccessProvider

        provider = KesselAccessProvider()
        provider.get_access_for_user(self._make_user())

        for call in mock_client.inventory_stub.Check.call_args_list:
            req = call[0][0]
            self.assertIsNotNone(req.object.reporter)
            self.assertEqual(req.object.reporter.type, "rbac")
            self.assertIsNotNone(req.subject.resource.reporter)
            self.assertEqual(req.subject.resource.reporter.type, "rbac")

    def test_cache_ttl_returns_integer(self):
        from koku_rebac.access_provider import KesselAccessProvider

        provider = KesselAccessProvider()
        ttl = provider.get_cache_ttl()
        self.assertIsInstance(ttl, int)
