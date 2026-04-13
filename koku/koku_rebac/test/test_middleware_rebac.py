#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Unit tests for middleware + Kessel ReBAC integration.

These tests exercise the real middleware chain, Django cache, and ORM with
mocked gRPC at the Kessel boundary.  They validate middleware *behavior*
(call routing, caching, error handling) -- not wire-protocol correctness,
which is covered by the contract tests.

Updated for Inventory API v1beta2: all mocks target inventory_stub, not
check_stub.
"""
import copy
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

from django.test import override_settings

from api.iam.test.iam_test_case import IamTestCase
from koku.middleware import IdentityHeaderMiddleware
from koku.settings import CacheEnum

_KESSEL_CACHE = {CacheEnum.kessel: {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


class TestMiddlewareKesselMocked(IamTestCase):
    """UT-MW-AUTH: Middleware + mocked Kessel gRPC boundary."""

    def setUp(self):
        super().setUp()
        self.mock_request = copy.deepcopy(self.request_context["request"])
        self.mock_request.path = "/api/cost-management/v1/reports/openshift/costs/"
        self.mock_request.META["QUERY_STRING"] = ""
        if not hasattr(self.mock_request.user, "req_id"):
            self.mock_request.user.req_id = None

    def _make_check_response(self, allowed):
        from kessel.inventory.v1beta2 import allowed_pb2

        resp = MagicMock()
        resp.allowed = allowed_pb2.ALLOWED_TRUE if allowed else allowed_pb2.ALLOWED_FALSE
        return resp

    # UT-MW-AUTH-001
    @override_settings(AUTHORIZATION_BACKEND="rebac", ENHANCED_ORG_ADMIN=False)
    @patch("koku_rebac.access_provider.get_workspace_resolver")
    @patch("koku_rebac.access_provider.get_kessel_client")
    def test_rebac_uses_kessel_not_rbac(self, mock_get_client, mock_get_resolver):
        """On-prem (ReBAC) requests reach the Kessel Inventory Check stub."""
        mock_client = MagicMock()
        mock_client.inventory_stub.Check.return_value = self._make_check_response(False)
        mock_client.inventory_stub.StreamedListObjects.return_value = iter([])
        mock_get_client.return_value = mock_client

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = "test-org"
        mock_get_resolver.return_value = mock_resolver

        non_admin_data = self._create_user_data()
        non_admin_ctx = self._create_request_context(
            self.customer_data, non_admin_data, create_customer=False, is_admin=False
        )
        request = copy.deepcopy(non_admin_ctx["request"])
        request.path = "/api/cost-management/v1/reports/openshift/costs/"
        request.META["QUERY_STRING"] = ""
        if not hasattr(request.user, "req_id"):
            request.user.req_id = None

        mw = IdentityHeaderMiddleware(Mock())
        mw.process_request(request)

        mock_client.inventory_stub.Check.assert_called()

    # UT-MW-AUTH-002
    @override_settings(AUTHORIZATION_BACKEND="rebac", CACHES=_KESSEL_CACHE)
    @patch("koku_rebac.access_provider.get_workspace_resolver")
    @patch("koku_rebac.access_provider.get_kessel_client")
    def test_kessel_results_are_cached(self, mock_get_client, mock_get_resolver):
        """Second request within TTL is served from cache (no second gRPC call)."""
        mock_client = MagicMock()
        mock_client.inventory_stub.Check.return_value = self._make_check_response(False)
        mock_client.inventory_stub.StreamedListObjects.return_value = iter([])
        mock_get_client.return_value = mock_client

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = "test-org"
        mock_get_resolver.return_value = mock_resolver

        mw = IdentityHeaderMiddleware(Mock())
        mw.process_request(self.mock_request)

        call_count_after_first = mock_client.inventory_stub.Check.call_count

        request2 = copy.deepcopy(self.mock_request)
        request2.user = self.mock_request.user
        mw.process_request(request2)

        self.assertEqual(
            mock_client.inventory_stub.Check.call_count,
            call_count_after_first,
            "Kessel should not be called again on cache hit",
        )

    # UT-MW-AUTH-003
    @override_settings(AUTHORIZATION_BACKEND="rebac", ENHANCED_ORG_ADMIN=False)
    def test_kessel_outage_returns_424(self):
        """Kessel outage results in HTTP 424 via KesselConnectionError."""
        from koku_rebac.exceptions import KesselConnectionError

        non_admin_data = self._create_user_data()
        non_admin_ctx = self._create_request_context(
            self.customer_data, non_admin_data, create_customer=False, is_admin=False
        )
        request = copy.deepcopy(non_admin_ctx["request"])
        request.path = "/api/cost-management/v1/reports/openshift/costs/"
        request.META["QUERY_STRING"] = ""
        if not hasattr(request.user, "req_id"):
            request.user.req_id = None

        with patch("koku_rebac.access_provider.KesselAccessProvider.get_access_for_user") as mock_access:
            mock_access.side_effect = KesselConnectionError("unreachable")
            mw = IdentityHeaderMiddleware(Mock())
            result = mw.process_request(request)

        self.assertIsNotNone(result)
        self.assertEqual(result.status_code, 424)

    # UT-MW-AUTH-005
    @override_settings(AUTHORIZATION_BACKEND="rebac")
    @patch("koku.middleware.on_resource_created")
    def test_new_org_gets_settings_sentinel(self, mock_report):
        """New customer creation reports a settings resource to Kessel."""
        new_org_id = "new-org-ut-mw-test"
        IdentityHeaderMiddleware.create_customer("acct-ut-001", new_org_id, "POST")
        mock_report.assert_called_once_with("settings", f"settings-{new_org_id}", new_org_id)

        org_id2 = "sentinel-ut-org"
        IdentityHeaderMiddleware.create_customer("acct-ut-002", org_id2, "POST")
        mock_report.assert_called_with("settings", f"settings-{org_id2}", org_id2)

    # UT-MW-AUTH-010
    @override_settings(AUTHORIZATION_BACKEND="rebac", ENHANCED_ORG_ADMIN=False)
    @patch("koku_rebac.access_provider.get_workspace_resolver")
    @patch("koku_rebac.access_provider.get_kessel_client")
    def test_non_admin_gets_access_from_kessel(self, mock_get_client, mock_get_resolver):
        """Non-admin user has access resolved through mocked Kessel Inventory Check."""
        mock_client = MagicMock()

        def fake_check(request, **kwargs):
            if request.relation == "cost_management_aws_account_view":
                return self._make_check_response(True)
            return self._make_check_response(False)

        mock_client.inventory_stub.Check.side_effect = fake_check
        mock_client.inventory_stub.StreamedListObjects.return_value = iter([])
        mock_get_client.return_value = mock_client

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = "test-org"
        mock_get_resolver.return_value = mock_resolver

        non_admin_data = self._create_user_data()
        non_admin_ctx = self._create_request_context(
            self.customer_data, non_admin_data, create_customer=False, is_admin=False
        )
        request = copy.deepcopy(non_admin_ctx["request"])
        request.path = "/api/cost-management/v1/reports/openshift/costs/"
        request.META["QUERY_STRING"] = ""
        if not hasattr(request.user, "req_id"):
            request.user.req_id = None

        mw = IdentityHeaderMiddleware(Mock())
        mw.process_request(request)

        self.assertEqual(request.user.access["aws.account"]["read"], ["*"])
