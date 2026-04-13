#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Contract tests against a real Kessel stack (Podman Compose).

These tests exercise gRPC round-trips to Inventory API v1beta2
running in local containers.  They validate that:

  1. The Kessel SDK protobuf stubs are wire-compatible with the deployed
     services.
  2. The ZED schema loaded into SpiceDB supports the Check and
     StreamedListObjects request shapes used by Koku.
  3. ReportResource calls succeed with valid representations.

Tuples are seeded via ``KesselFixture`` so tests are deterministic under
real authorization (``authz: impl: kessel``).

PREREQUISITES
~~~~~~~~~~~~~
Start the Kessel stack before running these tests::

    podman compose -f dev/kessel/docker-compose.yml up -d

Run::

    ENABLE_KESSEL_TEST=1 python -m pytest koku_rebac/test/test_contract.py -v
"""
import os
import unittest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "koku.test_settings_lite")

import django  # noqa: E402

django.setup()

import time  # noqa: E402

import grpc  # noqa: E402
from django.test import SimpleTestCase  # noqa: E402

from kessel.inventory.v1beta2 import allowed_pb2  # noqa: E402
from kessel.inventory.v1beta2 import check_request_pb2  # noqa: E402
from kessel.inventory.v1beta2 import delete_resource_request_pb2  # noqa: E402
from kessel.inventory.v1beta2 import inventory_service_pb2_grpc  # noqa: E402
from kessel.inventory.v1beta2 import report_resource_request_pb2  # noqa: E402
from kessel.inventory.v1beta2 import representation_type_pb2  # noqa: E402
from kessel.inventory.v1beta2 import reporter_reference_pb2  # noqa: E402
from kessel.inventory.v1beta2 import resource_reference_pb2  # noqa: E402
from kessel.inventory.v1beta2 import streamed_list_objects_request_pb2  # noqa: E402
from kessel.inventory.v1beta2 import subject_reference_pb2  # noqa: E402
from kessel.inventory.v1beta2 import write_visibility_pb2  # noqa: E402

from .kessel_fixture import KesselFixture  # noqa: E402

_KESSEL_STACK_SKIP = "Requires live Kessel stack (ENABLE_KESSEL_TEST=1)"

CT_WORKSPACE = "org-ct-contract"
CT_USER = "ct-granted-user"
CT_DENIED_USER = "ct-denied-user"


def _get_inventory_stub():
    """Create a gRPC stub connected to the local Inventory API."""
    host = os.environ.get("KESSEL_INVENTORY_HOST", "localhost")
    port = os.environ.get("KESSEL_INVENTORY_PORT", "9081")
    channel = grpc.insecure_channel(f"{host}:{port}")
    return inventory_service_pb2_grpc.KesselInventoryServiceStub(channel)


def _build_check(workspace_id, permission, user_id):
    """Build a CheckRequest for the contract test."""
    return check_request_pb2.CheckRequest(
        object=resource_reference_pb2.ResourceReference(
            resource_type="workspace",
            resource_id=workspace_id,
            reporter=reporter_reference_pb2.ReporterReference(type="rbac"),
        ),
        relation=permission,
        subject=subject_reference_pb2.SubjectReference(
            resource=resource_reference_pb2.ResourceReference(
                resource_type="principal",
                resource_id=f"redhat/{user_id}",
                reporter=reporter_reference_pb2.ReporterReference(type="rbac"),
            ),
        ),
    )


@unittest.skipUnless(os.environ.get("ENABLE_KESSEL_TEST", ""), _KESSEL_STACK_SKIP)
class TestInventoryCheckContract(SimpleTestCase):
    """CT-CHECK: Inventory API v1beta2 Check roundtrips with real authorization."""

    fixture: KesselFixture

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.stub = _get_inventory_stub()
        cls.fixture = KesselFixture()
        cls.fixture.seed_access(CT_WORKSPACE, CT_USER, {"aws.account": {"read": ["*"]}})

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()
        super().tearDownClass()

    def test_check_granted_when_tuples_exist(self):
        """Check returns ALLOWED_TRUE when matching tuples are seeded."""
        req = _build_check(CT_WORKSPACE, "cost_management_aws_account_view", CT_USER)
        resp = self.stub.Check(req)
        self.assertEqual(resp.allowed, allowed_pb2.ALLOWED_TRUE)

    def test_check_denied_when_no_tuples(self):
        """Check returns ALLOWED_FALSE for a user with no seeded tuples."""
        req = _build_check(CT_WORKSPACE, "cost_management_aws_account_view", CT_DENIED_USER)
        resp = self.stub.Check(req)
        self.assertEqual(resp.allowed, allowed_pb2.ALLOWED_FALSE)

    def test_check_unknown_permission_does_not_error(self):
        """An unknown permission returns ALLOWED_FALSE or expected gRPC error, never a panic."""
        req = _build_check(CT_WORKSPACE, "nonexistent_permission", CT_USER)
        try:
            resp = self.stub.Check(req)
            self.assertEqual(resp.allowed, allowed_pb2.ALLOWED_FALSE)
        except grpc.RpcError as e:
            self.assertIn(
                e.code(),
                (grpc.StatusCode.INVALID_ARGUMENT, grpc.StatusCode.NOT_FOUND, grpc.StatusCode.FAILED_PRECONDITION),
            )

    def test_check_workspace_view_compound(self):
        """Check against _view compound permission returns ALLOWED_FALSE for unseeded type."""
        req = _build_check(CT_WORKSPACE, "cost_management_settings_view", CT_USER)
        resp = self.stub.Check(req)
        self.assertEqual(resp.allowed, allowed_pb2.ALLOWED_FALSE)

    def test_check_workspace_edit_compound(self):
        """Check against _edit compound permission returns ALLOWED_FALSE for unseeded type."""
        req = _build_check(CT_WORKSPACE, "cost_management_cost_model_edit", CT_USER)
        resp = self.stub.Check(req)
        self.assertEqual(resp.allowed, allowed_pb2.ALLOWED_FALSE)

    def test_reporter_reference_not_nil(self):
        """Requests with ReporterReference set should not cause nil-panics."""
        req = _build_check(CT_WORKSPACE, "cost_management_aws_account_view", CT_USER)
        self.assertIsNotNone(req.object.reporter)
        self.assertEqual(req.object.reporter.type, "rbac")
        resp = self.stub.Check(req)
        self.assertIsNotNone(resp)


CT_CLEANUP_WORKSPACE = "org-ct-cleanup"
CT_CLEANUP_USER = "ct-cleanup-user"
CT_CLEANUP_CLUSTER_ID = "ct-cleanup-cluster-001"


def _build_report_resource(resource_type, resource_id, org_id):
    """Build a ReportResourceRequest for the contract test."""
    request = report_resource_request_pb2.ReportResourceRequest(
        inventory_id=f"{org_id}/{resource_type}/{resource_id}",
        type=resource_type,
        reporter_type="cost_management",
        reporter_instance_id=resource_id,
        write_visibility=write_visibility_pb2.IMMEDIATE,
    )
    request.representations.metadata.local_resource_id = resource_id
    request.representations.metadata.api_href = f"/api/cost-management/v1/{resource_type}/{resource_id}"
    request.representations.common.update({"workspace_id": org_id})
    request.representations.reporter.update({"local_resource_id": resource_id})
    return request


def _build_delete_resource(resource_type, resource_id):
    """Build a DeleteResourceRequest for the contract test."""
    return delete_resource_request_pb2.DeleteResourceRequest(
        reference=resource_reference_pb2.ResourceReference(
            resource_type=resource_type,
            resource_id=resource_id,
            reporter=reporter_reference_pb2.ReporterReference(
                type="cost_management",
                instance_id=resource_id,
            ),
        )
    )


def _build_streamed_list(resource_type, user_id, relation="read"):
    """Build a StreamedListObjectsRequest for per-resource discovery."""
    return streamed_list_objects_request_pb2.StreamedListObjectsRequest(
        object_type=representation_type_pb2.RepresentationType(
            resource_type=resource_type,
            reporter_type="cost_management",
        ),
        relation=relation,
        subject=subject_reference_pb2.SubjectReference(
            resource=resource_reference_pb2.ResourceReference(
                resource_type="principal",
                resource_id=f"redhat/{user_id}",
                reporter=reporter_reference_pb2.ReporterReference(type="rbac"),
            ),
        ),
    )


@unittest.skipUnless(os.environ.get("ENABLE_KESSEL_TEST", ""), _KESSEL_STACK_SKIP)
class TestDeleteResourceCleanupContract(SimpleTestCase):
    """CT-CLEANUP: Full cleanup (Inventory + Relations) revokes StreamedListObjects discoverability.

    The Kessel architecture separates Inventory (resource metadata) from
    Relations/SpiceDB (authorization tuples).  StreamedListObjects is purely
    SpiceDB-backed, so DeleteResource (Inventory API) alone does NOT revoke
    discoverability.  Full cleanup requires BOTH deleting the Inventory entry
    AND removing the SpiceDB t_workspace tuple via the Relations API.

    Lifecycle:
      1. seed_access creates SpiceDB tuples (workspace -> role_binding -> role -> principal)
      2. ReportResource registers the resource in Kessel Inventory
      3. seed_inventory_resources creates the resource-workspace SpiceDB tuple
      4. StreamedListObjects returns the resource (SpiceDB tuples satisfied)
      5. delete_resource_tuples removes the SpiceDB t_workspace tuple
      6. DeleteResource removes the Inventory entry
      7. StreamedListObjects no longer returns the resource
    """

    fixture: KesselFixture

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.stub = _get_inventory_stub()
        cls.fixture = KesselFixture()
        cls.fixture.seed_access(
            CT_CLEANUP_WORKSPACE,
            CT_CLEANUP_USER,
            {"openshift.cluster": {"read": ["*"]}},
        )

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()
        super().tearDownClass()

    def _list_resource_ids(self, resource_type, user_id, relation="read"):
        """Call StreamedListObjects and return the set of resource IDs."""
        request = _build_streamed_list(resource_type, user_id, relation)
        ids = set()
        try:
            for response in self.stub.StreamedListObjects(request):
                if response.object and response.object.resource_id:
                    ids.add(response.object.resource_id)
        except grpc.RpcError:
            pass
        return ids

    def _poll_listed(self, resource_type, resource_id, user_id, expected_present, timeout=45):
        """Poll StreamedListObjects until resource is present/absent or timeout."""
        deadline = time.monotonic() + timeout
        interval = 0.5
        while time.monotonic() < deadline:
            ids = self._list_resource_ids(resource_type, user_id)
            found = resource_id in ids
            if found == expected_present:
                return True
            time.sleep(min(interval, max(0, deadline - time.monotonic())))
            interval = min(interval * 2, 5.0)
        return False

    def test_full_cleanup_removes_from_streamed_list(self):
        """ReportResource -> discoverable -> full cleanup -> gone.

        Kessel's StreamedListObjects is purely SpiceDB-backed:
        DeleteResource (Inventory API) alone does NOT revoke
        discoverability because the SpiceDB t_workspace tuple persists.

        Full cleanup requires BOTH:
          a) Deleting the SpiceDB resource-workspace tuple (Relations API)
          b) Deleting the Inventory entry (DeleteResource)
        """
        resource_type = "openshift_cluster"
        resource_id = CT_CLEANUP_CLUSTER_ID

        self.stub.ReportResource(_build_report_resource(resource_type, resource_id, CT_CLEANUP_WORKSPACE))
        self.fixture.seed_inventory_resources(
            CT_CLEANUP_WORKSPACE,
            resource_type,
            [resource_id],
            wait_user=CT_CLEANUP_USER,
        )

        self.assertTrue(
            self._poll_listed(resource_type, resource_id, CT_CLEANUP_USER, expected_present=True),
            f"StreamedListObjects must return {resource_id} after ReportResource + tuple seeding",
        )

        self.fixture.delete_resource_tuples(resource_type, resource_id)
        self.stub.DeleteResource(_build_delete_resource(resource_type, resource_id))

        self.assertTrue(
            self._poll_listed(resource_type, resource_id, CT_CLEANUP_USER, expected_present=False),
            f"StreamedListObjects must NOT return {resource_id} after full cleanup",
        )

    def test_delete_nonexistent_resource_does_not_error(self):
        """DeleteResource for a resource that doesn't exist should not raise."""
        try:
            self.stub.DeleteResource(_build_delete_resource("openshift_cluster", "ct-nonexistent-cluster-999"))
        except grpc.RpcError as e:
            self.assertIn(
                e.code(),
                (grpc.StatusCode.NOT_FOUND, grpc.StatusCode.OK),
                f"Unexpected gRPC error for nonexistent resource: {e.code()} {e.details()}",
            )
