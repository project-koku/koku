#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Integration tests for Kessel/ReBAC authorization (Inventory API v1beta2).

Tests in this module use IamTestCase + PostgreSQL and, where noted, a **real
Kessel stack** (Inventory API running in Podman Compose).  They exercise
the middleware chain, Django cache, URL routing, DRF request/response cycle,
and ORM with live gRPC round-trips to Inventory API v1beta2.

Prerequisites for real-Kessel tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Start the Kessel stack before running::

    podman compose -f dev/kessel/docker-compose.yml up -d

Run tests requiring a live stack::

    ENABLE_KESSEL_TEST=1 python manage.py test koku_rebac.test.test_integration -v 2
"""
import copy
import os
import unittest
from unittest.mock import MagicMock
from unittest.mock import Mock

from django.core.cache import caches
from django.test import override_settings
from django.test import SimpleTestCase

from .kessel_fixture import KesselFixture
from api.iam.test.iam_test_case import IamTestCase
from koku.middleware import IdentityHeaderMiddleware
from koku.rbac import RESOURCE_TYPES
from koku.settings import CacheEnum

_KESSEL_STACK_SKIP = "Requires live Kessel stack (ENABLE_KESSEL_TEST=1)"


class TestMiddlewareKesselIntegration(IamTestCase):
    """IT-MW: Middleware integration with Kessel Inventory API."""

    def setUp(self):
        super().setUp()
        self.mock_request = copy.deepcopy(self.request_context["request"])
        self.mock_request.path = "/api/cost-management/v1/reports/openshift/costs/"
        self.mock_request.META["QUERY_STRING"] = ""
        if not hasattr(self.mock_request.user, "req_id"):
            self.mock_request.user.req_id = None

    @override_settings(AUTHORIZATION_BACKEND="rebac", ONPREM=True)
    def test_org_admin_bypass(self):
        """Org admins bypass Kessel entirely."""
        mw = IdentityHeaderMiddleware(Mock())
        result = mw.process_request(self.mock_request)
        self.assertIsNone(result)
        self.assertIsNotNone(self.mock_request.user.access)

    @override_settings(AUTHORIZATION_BACKEND="rebac", ONPREM=True)
    def test_kessel_cache_vs_rbac_cache(self):
        """Kessel results go to the 'kessel' cache, not 'rbac'."""
        mw = IdentityHeaderMiddleware(Mock())
        mw.process_request(self.mock_request)
        rbac_cache = caches[CacheEnum.rbac]
        kessel_cache = caches[CacheEnum.kessel]
        self.assertIsNotNone(kessel_cache)
        self.assertIsNotNone(rbac_cache)

    @override_settings(AUTHORIZATION_BACKEND="rbac")
    def test_rbac_backend_does_not_call_kessel(self):
        """When AUTHORIZATION_BACKEND='rbac', Kessel is not touched."""
        mw = IdentityHeaderMiddleware(Mock())
        mw.process_request(self.mock_request)
        self.assertIsNotNone(self.mock_request.user.access)


class TestAccessManagementHiddenInRBAC(IamTestCase):
    """IT-HIDDEN: Access management endpoints removed from URL patterns."""

    @override_settings(AUTHORIZATION_BACKEND="rbac")
    def test_access_management_urls_not_registered(self):
        """Access management URLs should not be registered (externalized)."""
        from django.urls import reverse

        with self.assertRaises(Exception):
            reverse("roles-list")

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    def test_access_management_urls_also_removed_in_rebac(self):
        """Access management URLs are removed even in rebac mode (externalized)."""
        from django.urls import reverse

        with self.assertRaises(Exception):
            reverse("roles-list")


IT_WORKSPACE = "org-it-access-provider"
IT_GRANTED_USER = "it-granted-user"
IT_DENIED_USER = "it-denied-user"


def _make_user(user_id, org_id=IT_WORKSPACE):
    """Build a lightweight mock User for direct KesselAccessProvider calls."""
    user = MagicMock()
    user.user_id = user_id
    user.username = f"username-{user_id}"
    user.customer.org_id = org_id
    return user


@unittest.skipUnless(os.environ.get("ENABLE_KESSEL_TEST", ""), _KESSEL_STACK_SKIP)
@override_settings(AUTHORIZATION_BACKEND="rebac", ONPREM=True)
class TestAccessProviderKesselIntegration(SimpleTestCase):
    """IT-AP: KesselAccessProvider against a live Kessel stack with real authz.

    Calls ``get_access_for_user()`` directly (not through middleware) to
    validate Check and StreamedListObjects business logic end-to-end.
    """

    fixture: KesselFixture

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fixture = KesselFixture()
        cls.fixture.seed_access(
            IT_WORKSPACE,
            IT_GRANTED_USER,
            {"aws.account": {"read": ["*"]}, "cost_model": {"write": ["*"]}},
        )

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()
        super().tearDownClass()

    def _get_provider(self):
        from koku_rebac.access_provider import KesselAccessProvider

        return KesselAccessProvider()

    def test_check_grants_wildcard_when_tuples_exist(self):
        """IT-AP-1: Seeded AWS read permission grants wildcard access."""
        provider = self._get_provider()
        result = provider.get_access_for_user(_make_user(IT_GRANTED_USER))
        self.assertEqual(result["aws.account"]["read"], ["*"])

    def test_check_denies_when_no_tuples(self):
        """IT-AP-2: User with no tuples gets empty access lists."""
        provider = self._get_provider()
        result = provider.get_access_for_user(_make_user(IT_DENIED_USER))
        self.assertEqual(result["aws.account"]["read"], [])
        self.assertEqual(result["cost_model"]["read"], [])
        self.assertEqual(result["cost_model"]["write"], [])

    def test_write_grants_read_parity(self):
        """IT-AP-3: cost_model write permission also grants read (RBAC v1 parity)."""
        provider = self._get_provider()
        result = provider.get_access_for_user(_make_user(IT_GRANTED_USER))
        self.assertEqual(result["cost_model"]["write"], ["*"])
        self.assertEqual(result["cost_model"]["read"], ["*"])

    def test_ocp_streamed_list_returns_resource_ids(self):
        """IT-AP-4: StreamedListObjects returns seeded OCP resource IDs.

        Requires both: (a) resources registered in the Inventory API database
        via ReportResource, and (b) SpiceDB tuples for the authorization path.
        """
        from koku_rebac.client import get_kessel_client
        from koku_rebac.resource_reporter import _build_report_request

        ocp_fixture = KesselFixture()
        try:
            ocp_fixture.seed_access(
                IT_WORKSPACE,
                IT_GRANTED_USER,
                {"openshift.cluster": {"read": ["*"]}},
            )
            ocp_fixture.seed_ocp_resources(
                IT_WORKSPACE,
                "openshift_cluster",
                ["it-cluster-001", "it-cluster-002"],
                wait_user=IT_GRANTED_USER,
            )

            client = get_kessel_client()
            for rid in ("it-cluster-001", "it-cluster-002"):
                req = _build_report_request("openshift_cluster", rid, IT_WORKSPACE)
                client.inventory_stub.ReportResource(req)

            provider = self._get_provider()
            result = provider.get_access_for_user(_make_user(IT_GRANTED_USER))
            self.assertIn("it-cluster-001", result["openshift.cluster"]["read"])
            self.assertIn("it-cluster-002", result["openshift.cluster"]["read"])
        finally:
            ocp_fixture.cleanup()

    def test_ocp_streamed_list_empty_when_no_resources(self):
        """IT-AP-5: StreamedListObjects returns empty list when no OCP resources exist."""
        provider = self._get_provider()
        result = provider.get_access_for_user(_make_user(IT_DENIED_USER))
        self.assertEqual(result["openshift.cluster"]["read"], [])
        self.assertEqual(result["openshift.node"]["read"], [])
        self.assertEqual(result["openshift.project"]["read"], [])

    def test_access_dict_shape_matches_resource_types(self):
        """IT-AP-6: Every key from RESOURCE_TYPES is present in the returned dict."""
        provider = self._get_provider()
        result = provider.get_access_for_user(_make_user(IT_DENIED_USER))
        for res_type, operations in RESOURCE_TYPES.items():
            self.assertIn(res_type, result, f"Missing key: {res_type}")
            for op in operations:
                self.assertIn(op, result[res_type], f"Missing operation {op} for {res_type}")

    def test_cross_provider_type_isolation(self):
        """IT-AP-7: AWS read granted, other providers denied."""
        fixture = KesselFixture()
        try:
            fixture.seed_access(IT_WORKSPACE, "it-isolated-user", {"aws.account": {"read": ["*"]}})
            provider = self._get_provider()
            result = provider.get_access_for_user(_make_user("it-isolated-user"))
            self.assertEqual(result["aws.account"]["read"], ["*"])
            self.assertEqual(result["gcp.account"]["read"], [])
            self.assertEqual(result["gcp.project"]["read"], [])
            self.assertEqual(result["azure.subscription_guid"]["read"], [])
            self.assertEqual(result["openshift.cluster"]["read"], [])
            self.assertEqual(result["cost_model"]["read"], [])
            self.assertEqual(result["settings"]["read"], [])
        finally:
            fixture.cleanup()

    def test_write_read_parity_is_per_type(self):
        """IT-AP-8: Settings write grants settings read, not cost_model write."""
        fixture = KesselFixture()
        try:
            fixture.seed_access(
                IT_WORKSPACE,
                "it-mixed-rw-user",
                {"settings": {"write": ["*"]}, "cost_model": {"read": ["*"]}},
            )
            provider = self._get_provider()
            result = provider.get_access_for_user(_make_user("it-mixed-rw-user"))
            self.assertEqual(result["settings"]["write"], ["*"])
            self.assertEqual(result["settings"]["read"], ["*"])
            self.assertEqual(result["cost_model"]["read"], ["*"])
            self.assertEqual(result["cost_model"]["write"], [])
        finally:
            fixture.cleanup()

    def test_ocp_top_down_inheritance(self):
        """IT-AP-9: cluster_read cascades to nodes and projects via ZED schema."""
        from koku_rebac.client import get_kessel_client
        from koku_rebac.resource_reporter import _build_report_request

        fixture = KesselFixture()
        try:
            fixture.seed_access(IT_WORKSPACE, "it-ocp-topdown", {"openshift.cluster": {"read": ["*"]}})
            fixture.seed_inventory_resources(
                IT_WORKSPACE, "openshift_cluster", ["td-cluster-1"], wait_user="it-ocp-topdown"
            )
            fixture.seed_inventory_resources(IT_WORKSPACE, "openshift_node", ["td-node-1"], wait_user="it-ocp-topdown")
            fixture.seed_inventory_resources(
                IT_WORKSPACE, "openshift_project", ["td-project-1"], wait_user="it-ocp-topdown"
            )

            client = get_kessel_client()
            for rtype, rid in [
                ("openshift_cluster", "td-cluster-1"),
                ("openshift_node", "td-node-1"),
                ("openshift_project", "td-project-1"),
            ]:
                client.inventory_stub.ReportResource(_build_report_request(rtype, rid, IT_WORKSPACE))

            provider = self._get_provider()
            result = provider.get_access_for_user(_make_user("it-ocp-topdown"))
            self.assertIn("td-cluster-1", result["openshift.cluster"]["read"])
            self.assertIn("td-node-1", result["openshift.node"]["read"])
            self.assertIn("td-project-1", result["openshift.project"]["read"])
        finally:
            fixture.cleanup()

    def test_ocp_bottom_up_isolation(self):
        """IT-AP-10: project_read only -- no cluster or node access."""
        from koku_rebac.client import get_kessel_client
        from koku_rebac.resource_reporter import _build_report_request

        fixture = KesselFixture()
        try:
            fixture.seed_access(IT_WORKSPACE, "it-ocp-bottomup", {"openshift.project": {"read": ["*"]}})
            fixture.seed_inventory_resources(IT_WORKSPACE, "openshift_cluster", ["bu-cluster-1"])
            fixture.seed_inventory_resources(IT_WORKSPACE, "openshift_node", ["bu-node-1"])
            fixture.seed_inventory_resources(
                IT_WORKSPACE, "openshift_project", ["bu-project-1"], wait_user="it-ocp-bottomup"
            )

            client = get_kessel_client()
            for rtype, rid in [
                ("openshift_cluster", "bu-cluster-1"),
                ("openshift_node", "bu-node-1"),
                ("openshift_project", "bu-project-1"),
            ]:
                client.inventory_stub.ReportResource(_build_report_request(rtype, rid, IT_WORKSPACE))

            provider = self._get_provider()
            result = provider.get_access_for_user(_make_user("it-ocp-bottomup"))
            self.assertIn("bu-project-1", result["openshift.project"]["read"])
            self.assertEqual(result["openshift.cluster"]["read"], [])
            self.assertEqual(result["openshift.node"]["read"], [])
        finally:
            fixture.cleanup()

    def test_same_workspace_different_users(self):
        """IT-AP-11: User A sees clusters, User B sees nothing."""
        from koku_rebac.client import get_kessel_client
        from koku_rebac.resource_reporter import _build_report_request

        fixture = KesselFixture()
        try:
            fixture.seed_access(IT_WORKSPACE, "it-user-a", {"openshift.cluster": {"read": ["*"]}})
            fixture.seed_inventory_resources(
                IT_WORKSPACE, "openshift_cluster", ["mu-cluster-1"], wait_user="it-user-a"
            )

            client = get_kessel_client()
            client.inventory_stub.ReportResource(
                _build_report_request("openshift_cluster", "mu-cluster-1", IT_WORKSPACE)
            )

            provider = self._get_provider()
            result_a = provider.get_access_for_user(_make_user("it-user-a"))
            result_b = provider.get_access_for_user(_make_user("it-user-b-denied"))
            self.assertIn("mu-cluster-1", result_a["openshift.cluster"]["read"])
            self.assertEqual(result_b["openshift.cluster"]["read"], [])
            self.assertEqual(result_b["openshift.node"]["read"], [])
            self.assertEqual(result_b["openshift.project"]["read"], [])
        finally:
            fixture.cleanup()

    def test_ksl_all_read_wildcard(self):
        """IT-AP-12: cost_management_all_read grants read to ALL types."""
        fixture = KesselFixture()
        try:
            fixture.seed_all_read_wildcard(IT_WORKSPACE, "it-allread-user")
            provider = self._get_provider()
            result = provider.get_access_for_user(_make_user("it-allread-user"))
            for res_type, operations in RESOURCE_TYPES.items():
                if "read" in operations:
                    self.assertEqual(
                        result[res_type]["read"],
                        ["*"],
                        f"Expected wildcard read for {res_type}, got {result[res_type]['read']}",
                    )
        finally:
            fixture.cleanup()

    def test_per_resource_aws_accounts(self):
        """IT-AP-13: Registered AWS accounts return specific IDs, not wildcard."""
        from koku_rebac.client import get_kessel_client
        from koku_rebac.resource_reporter import _build_report_request

        fixture = KesselFixture()
        try:
            fixture.seed_access(IT_WORKSPACE, "it-aws-perres", {"aws.account": {"read": ["*"]}})
            fixture.seed_inventory_resources(
                IT_WORKSPACE, "aws_account", ["acct-111", "acct-222"], wait_user="it-aws-perres"
            )

            client = get_kessel_client()
            for rid in ("acct-111", "acct-222"):
                client.inventory_stub.ReportResource(_build_report_request("aws_account", rid, IT_WORKSPACE))

            provider = self._get_provider()
            result = provider.get_access_for_user(_make_user("it-aws-perres"))
            aws_read = result["aws.account"]["read"]
            self.assertIn("acct-111", aws_read)
            self.assertIn("acct-222", aws_read)
            self.assertNotEqual(aws_read, ["*"], "Expected specific IDs, not wildcard")
        finally:
            fixture.cleanup()

    def test_per_resource_cost_model_write_read_parity(self):
        """IT-AP-14: cost_model write with registered resources returns specific IDs for both."""
        from koku_rebac.client import get_kessel_client
        from koku_rebac.resource_reporter import _build_report_request

        fixture = KesselFixture()
        try:
            fixture.seed_access(IT_WORKSPACE, "it-cm-perres", {"cost_model": {"write": ["*"]}})
            fixture.seed_inventory_resources(
                IT_WORKSPACE, "cost_model", ["cm-uuid-1", "cm-uuid-2"], wait_user="it-cm-perres", wait_relation="write"
            )

            client = get_kessel_client()
            for rid in ("cm-uuid-1", "cm-uuid-2"):
                client.inventory_stub.ReportResource(_build_report_request("cost_model", rid, IT_WORKSPACE))

            provider = self._get_provider()
            result = provider.get_access_for_user(_make_user("it-cm-perres"))
            cm_write = result["cost_model"]["write"]
            cm_read = result["cost_model"]["read"]
            self.assertIn("cm-uuid-1", cm_write)
            self.assertIn("cm-uuid-2", cm_write)
            for cm_id in cm_write:
                self.assertIn(cm_id, cm_read, f"Write ID {cm_id} missing from read list")
        finally:
            fixture.cleanup()

    def test_wildcard_fallback_when_no_resources_registered(self):
        """IT-AP-15: Wildcard fallback when user has permission but no resources registered."""
        fixture = KesselFixture()
        try:
            fixture.seed_access(IT_WORKSPACE, "it-fallback-user", {"gcp.account": {"read": ["*"]}})
            provider = self._get_provider()
            result = provider.get_access_for_user(_make_user("it-fallback-user"))
            self.assertEqual(
                result["gcp.account"]["read"],
                ["*"],
                "Expected wildcard when no resources are registered",
            )
        finally:
            fixture.cleanup()

    def test_compound_aws_and_ocp_access(self):
        """IT-AP-16: Both AWS per-resource and OCP per-resource in same access dict."""
        from koku_rebac.client import get_kessel_client
        from koku_rebac.resource_reporter import _build_report_request

        fixture = KesselFixture()
        try:
            fixture.seed_access(
                IT_WORKSPACE,
                "it-compound-user",
                {"aws.account": {"read": ["*"]}, "openshift.cluster": {"read": ["*"]}},
            )
            fixture.seed_inventory_resources(
                IT_WORKSPACE, "aws_account", ["compound-acct-1"], wait_user="it-compound-user"
            )
            fixture.seed_inventory_resources(
                IT_WORKSPACE,
                "openshift_cluster",
                ["compound-cluster-1", "compound-cluster-2"],
                wait_user="it-compound-user",
            )

            client = get_kessel_client()
            client.inventory_stub.ReportResource(_build_report_request("aws_account", "compound-acct-1", IT_WORKSPACE))
            for cid in ("compound-cluster-1", "compound-cluster-2"):
                client.inventory_stub.ReportResource(_build_report_request("openshift_cluster", cid, IT_WORKSPACE))

            provider = self._get_provider()
            result = provider.get_access_for_user(_make_user("it-compound-user"))
            self.assertIn("compound-acct-1", result["aws.account"]["read"])
            self.assertIn("compound-cluster-1", result["openshift.cluster"]["read"])
            self.assertIn("compound-cluster-2", result["openshift.cluster"]["read"])
        finally:
            fixture.cleanup()

    def test_ocp_access_without_aws(self):
        """IT-AP-17: OCP clusters visible but AWS empty (cross-type boundary)."""
        from koku_rebac.client import get_kessel_client
        from koku_rebac.resource_reporter import _build_report_request

        fixture = KesselFixture()
        try:
            fixture.seed_access(IT_WORKSPACE, "it-ocp-only", {"openshift.cluster": {"read": ["*"]}})
            fixture.seed_inventory_resources(
                IT_WORKSPACE, "openshift_cluster", ["ocp-only-cluster"], wait_user="it-ocp-only"
            )
            client = get_kessel_client()
            client.inventory_stub.ReportResource(
                _build_report_request("openshift_cluster", "ocp-only-cluster", IT_WORKSPACE)
            )

            provider = self._get_provider()
            result = provider.get_access_for_user(_make_user("it-ocp-only"))
            self.assertIn("ocp-only-cluster", result["openshift.cluster"]["read"])
            self.assertEqual(result["aws.account"]["read"], [])
            self.assertEqual(result["azure.subscription_guid"]["read"], [])
            self.assertEqual(result["gcp.account"]["read"], [])
        finally:
            fixture.cleanup()

    def test_realistic_org_profile(self):
        """IT-AP-18: Full realistic org profile -- acceptance test."""
        from koku_rebac.client import get_kessel_client
        from koku_rebac.resource_reporter import _build_report_request

        fixture = KesselFixture()
        try:
            fixture.seed_access(
                IT_WORKSPACE,
                "it-org-admin",
                {
                    "aws.account": {"read": ["*"]},
                    "azure.subscription_guid": {"read": ["*"]},
                    "openshift.cluster": {"read": ["*"]},
                    "cost_model": {"write": ["*"]},
                    "settings": {"read": ["*"]},
                },
            )
            fixture.seed_inventory_resources(IT_WORKSPACE, "aws_account", ["org-aws-1"], wait_user="it-org-admin")
            fixture.seed_inventory_resources(
                IT_WORKSPACE, "azure_subscription_guid", ["org-sub-1"], wait_user="it-org-admin"
            )
            fixture.seed_inventory_resources(
                IT_WORKSPACE, "openshift_cluster", ["org-cluster-1"], wait_user="it-org-admin"
            )
            fixture.seed_inventory_resources(
                IT_WORKSPACE, "cost_model", ["org-cm-1"], wait_user="it-org-admin", wait_relation="write"
            )

            client = get_kessel_client()
            for rtype, rid in [
                ("aws_account", "org-aws-1"),
                ("azure_subscription_guid", "org-sub-1"),
                ("openshift_cluster", "org-cluster-1"),
                ("cost_model", "org-cm-1"),
            ]:
                client.inventory_stub.ReportResource(_build_report_request(rtype, rid, IT_WORKSPACE))

            provider = self._get_provider()
            result = provider.get_access_for_user(_make_user("it-org-admin"))

            self.assertIn("org-aws-1", result["aws.account"]["read"])
            self.assertIn("org-sub-1", result["azure.subscription_guid"]["read"])
            self.assertIn("org-cluster-1", result["openshift.cluster"]["read"])
            self.assertIn("org-cm-1", result["cost_model"]["write"])
            self.assertIn("org-cm-1", result["cost_model"]["read"])
            self.assertEqual(result["settings"]["read"], ["*"])
            self.assertEqual(result["gcp.account"]["read"], [])
            self.assertEqual(result["gcp.project"]["read"], [])
        finally:
            fixture.cleanup()
