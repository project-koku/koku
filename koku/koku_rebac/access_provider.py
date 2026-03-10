#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Authorization backend abstraction for RBAC and Kessel ReBAC.

Kessel path uses Inventory API v1beta2 exclusively:
  - Per-resource types: StreamedListObjects with Check fallback for wildcard
  - Settings only: Check(rbac/workspace, _view/_edit, rbac/principal)

StreamedListObjects returns specific resource IDs for any type registered as
a Kessel Inventory resource.  When it returns empty, a workspace-level Check
determines whether the user has wildcard access (resources not yet registered)
or no access at all.
"""
from __future__ import annotations

import logging
import time

import grpc
from django.conf import settings
from kessel.inventory.v1beta2 import (
    allowed_pb2,
    check_request_pb2,
    representation_type_pb2,
    reporter_reference_pb2,
    resource_reference_pb2,
    streamed_list_objects_request_pb2,
    subject_reference_pb2,
)

from api.common import log_json
from koku.rbac import RESOURCE_TYPES
from koku.rbac import RbacService

from .client import get_kessel_client
from .exceptions import KesselConnectionError
from .workspace import get_workspace_resolver

LOG = logging.getLogger(__name__)

KOKU_TO_KESSEL_TYPE_MAP: dict[str, str] = {
    "aws.account": "aws_account",
    "aws.organizational_unit": "aws_organizational_unit",
    "gcp.account": "gcp_account",
    "gcp.project": "gcp_project",
    "azure.subscription_guid": "azure_subscription_guid",
    "openshift.cluster": "openshift_cluster",
    "openshift.node": "openshift_node",
    "openshift.project": "openshift_project",
    "integration": "integration",
    "cost_model": "cost_model",
    "settings": "settings",
}

CHECK_ONLY_TYPES = {"settings"}

PERMISSION_SUFFIX_MAP = {
    "read": "view",
    "write": "edit",
}

GRPC_MAX_RETRIES = 3
GRPC_BACKOFF_BASE = 0.1  # seconds; delays: 0.1s, 0.5s
_RETRYABLE_CODES = frozenset({grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED})


def _is_retryable_grpc_error(exc: BaseException) -> bool:
    return isinstance(exc, grpc.RpcError) and hasattr(exc, "code") and exc.code() in _RETRYABLE_CODES


def _retry_grpc(fn, max_retries: int = GRPC_MAX_RETRIES, backoff_base: float = GRPC_BACKOFF_BASE):
    """Call *fn* with retry on transient gRPC errors.

    Retries up to *max_retries* total attempts with exponential backoff.
    Re-raises the last exception if all attempts fail.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:
            if not _is_retryable_grpc_error(exc):
                raise
            last_exc = exc
            if attempt < max_retries - 1:
                time.sleep(backoff_base * (5 ** attempt))
    raise last_exc  # type: ignore[misc]


def _init_empty_access() -> dict:
    """Build the empty access dict matching the shape produced by RbacService."""
    res_access: dict = {}
    for res_type, operations in RESOURCE_TYPES.items():
        res_access[res_type] = {op: [] for op in operations}
    return res_access


def _build_resource_ref(resource_type: str, resource_id: str, reporter_type: str = "rbac") -> resource_reference_pb2.ResourceReference:
    """Construct a ResourceReference with the mandatory reporter field."""
    return resource_reference_pb2.ResourceReference(
        resource_type=resource_type,
        resource_id=resource_id,
        reporter=reporter_reference_pb2.ReporterReference(type=reporter_type),
    )


def _build_subject_ref(user_id: str) -> subject_reference_pb2.SubjectReference:
    """Construct a SubjectReference wrapping a ResourceReference for rbac/principal."""
    return subject_reference_pb2.SubjectReference(
        resource=_build_resource_ref("principal", f"redhat/{user_id}"),
    )


def _build_check_request(
    workspace_id: str, permission: str, user_id: str
) -> check_request_pb2.CheckRequest:
    """Construct a CheckRequest against rbac/workspace for one permission."""
    return check_request_pb2.CheckRequest(
        object=_build_resource_ref("workspace", workspace_id),
        relation=permission,
        subject=_build_subject_ref(user_id),
    )


def _build_streamed_list_request(
    resource_type: str, relation: str, user_id: str
) -> streamed_list_objects_request_pb2.StreamedListObjectsRequest:
    """Construct a StreamedListObjectsRequest for per-resource auth."""
    return streamed_list_objects_request_pb2.StreamedListObjectsRequest(
        object_type=representation_type_pb2.RepresentationType(
            resource_type=resource_type,
            reporter_type="cost_management",
        ),
        relation=relation,
        subject=_build_subject_ref(user_id),
    )


class KesselAccessProvider:
    """Queries Kessel Inventory API v1beta2 for user access.

    Per-resource types use StreamedListObjects to return specific resource IDs.
    When StreamedListObjects returns empty, a workspace-level Check determines
    whether the user has wildcard access (resources not yet registered) or none.

    Settings is the only type that uses workspace-level Check exclusively
    (it's a capability, not a per-resource concept).
    """

    def __init__(self) -> None:
        self._workspace_resolver = get_workspace_resolver()

    def get_access_for_user(self, user) -> dict:
        """Get resource access for a user from Kessel.

        Raises KesselConnectionError when every gRPC call fails, so the
        middleware can return HTTP 424 instead of caching an empty dict.
        """
        client = get_kessel_client()
        access = _init_empty_access()
        org_id = user.customer.org_id
        user_id = getattr(user, "user_id", None) or user.username

        workspace_id = self._workspace_resolver.resolve(org_id)

        call_count = 0
        error_count = 0

        for koku_type, kessel_type in KOKU_TO_KESSEL_TYPE_MAP.items():
            if koku_type in CHECK_ONLY_TYPES:
                calls, errors = self._resolve_workspace_access(client, access, koku_type, kessel_type, workspace_id, user_id)
            else:
                calls, errors = self._resolve_per_resource_access(client, access, koku_type, kessel_type, workspace_id, user_id)
            call_count += calls
            error_count += errors

        if call_count > 0 and error_count == call_count:
            raise KesselConnectionError(
                f"All {error_count} Kessel gRPC calls failed -- service may be unreachable"
            )

        return access

    def _resolve_workspace_access(
        self, client, access: dict, koku_type: str, kessel_type: str, workspace_id: str, user_id: str,
    ) -> tuple[int, int]:
        """Use Check for workspace-level capabilities. Grants wildcard on success.

        Returns (call_count, error_count) for total-failure detection.
        """
        calls = errors = 0
        for operation in RESOURCE_TYPES.get(koku_type, ["read"]):
            suffix = PERMISSION_SUFFIX_MAP.get(operation, operation)
            permission = f"cost_management_{kessel_type}_{suffix}"
            allowed, ok = self._check_workspace_permission(client, workspace_id, permission, user_id)
            calls += 1
            if not ok:
                errors += 1
            elif allowed:
                access[koku_type][operation] = ["*"]
                if operation == "write":
                    access[koku_type]["read"] = ["*"]
        return calls, errors

    def _resolve_per_resource_access(
        self, client, access: dict, koku_type: str, kessel_type: str, workspace_id: str, user_id: str,
    ) -> tuple[int, int]:
        """Use StreamedListObjects with workspace-level Check for per-resource types.

        1. Check workspace-level permission first.
        2. If ALLOWED -> ["*"] (wildcard: user has blanket permission on this type).
        3. If DENIED  -> fall back to StreamedListObjects for per-resource IDs.
        4. Write access also grants read (write-grants-read parity).

        The workspace Check runs first so that users with org-wide roles
        (e.g. cost-administrator) always get wildcard access, even when
        the access-provider response is cached and new resources have been
        registered since the last cache fill.

        Returns (call_count, error_count) for total-failure detection.
        """
        calls = errors = 0
        for operation in RESOURCE_TYPES.get(koku_type, ["read"]):
            suffix = PERMISSION_SUFFIX_MAP.get(operation, operation)
            permission = f"cost_management_{kessel_type}_{suffix}"

            allowed, check_ok = self._check_workspace_permission(client, workspace_id, permission, user_id)
            calls += 1
            if not check_ok:
                errors += 1
            elif allowed:
                access[koku_type][operation] = ["*"]
            else:
                resource_ids, list_ok = self._streamed_list_objects(client, kessel_type, operation, user_id)
                calls += 1
                if not list_ok:
                    errors += 1
                elif resource_ids:
                    access[koku_type][operation] = resource_ids

            if operation == "write" and access[koku_type].get("write"):
                write_ids = access[koku_type]["write"]
                read_ids = access[koku_type].get("read", [])
                if write_ids == ["*"]:
                    access[koku_type]["read"] = ["*"]
                elif read_ids != ["*"]:
                    merged = list(dict.fromkeys(read_ids + write_ids))
                    access[koku_type]["read"] = merged
        return calls, errors

    def _streamed_list_objects(self, client, kessel_type, operation, user_id) -> tuple[list[str], bool]:
        """Call StreamedListObjects and return (resource_ids, success).

        Returns ([], False) on error so callers can track total failures.
        Retries on transient gRPC errors.
        """
        request = _build_streamed_list_request(kessel_type, operation, user_id)
        try:
            def _do_stream():
                resource_ids = []
                for response in client.inventory_stub.StreamedListObjects(request):
                    if response.object and response.object.resource_id:
                        resource_ids.append(response.object.resource_id)
                return resource_ids

            return _retry_grpc(_do_stream), True
        except Exception:
            LOG.exception(
                log_json(msg="Kessel StreamedListObjects failed", resource_type=kessel_type, operation=operation)
            )
            return [], False

    def _check_workspace_permission(self, client, workspace_id, permission, user_id) -> tuple[bool, bool]:
        """Check a single workspace-level permission.

        Returns (allowed, success) so callers can distinguish
        'denied' from 'gRPC error'.  Retries on transient gRPC errors.
        """
        request = _build_check_request(workspace_id, permission, user_id)
        try:
            resp = _retry_grpc(lambda: client.inventory_stub.Check(request))
            return resp.allowed == allowed_pb2.ALLOWED_TRUE, True
        except Exception:
            LOG.exception(
                log_json(msg="Kessel Check failed", permission=permission)
            )
            return False, False

    def get_cache_ttl(self) -> int:
        return int(settings.CACHES.get("kessel", {}).get("TIMEOUT", 300))


class RBACAccessProvider:
    """Wraps the existing RbacService for legacy compatibility."""

    def __init__(self):
        self._service = RbacService()

    def get_access_for_user(self, user):
        """Delegate to the existing RbacService."""
        return self._service.get_access_for_user(user)

    def get_cache_ttl(self) -> int:
        return self._service.get_cache_ttl()


def get_access_provider():
    """Factory: return the access provider for the configured backend."""
    if settings.AUTHORIZATION_BACKEND == "rebac":
        return KesselAccessProvider()
    return RBACAccessProvider()
