#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Transparent resource reporting to Kessel Inventory API v1beta2.

Resource lifecycle requires TWO Kessel APIs working in tandem:
  - **Inventory API** (gRPC): ReportResource / DeleteResource for metadata.
  - **Relations API** (REST):  SpiceDB tuple management (t_workspace).

**Creation** writes to both: ReportResource registers metadata, then a
Relations API POST creates the ``t_workspace`` tuple that makes the
resource discoverable via StreamedListObjects.

**Deletion** mirrors creation: DeleteResource removes metadata, then a
Relations API DELETE removes the ``t_workspace`` tuple.

The on-prem Kessel configuration disables the CDC-to-consumer pipeline
that normally creates tuples automatically.  Koku writes and deletes
them directly via the Relations API to maintain symmetry.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import grpc
import requests as http_requests
from django.conf import settings
from django.utils import timezone
from kessel.inventory.v1beta2 import delete_resource_request_pb2
from kessel.inventory.v1beta2 import report_resource_request_pb2
from kessel.inventory.v1beta2 import reporter_reference_pb2
from kessel.inventory.v1beta2 import resource_reference_pb2
from kessel.inventory.v1beta2 import write_visibility_pb2

from api.common import log_json
from koku_rebac.kessel_auth import get_http_auth_headers

if TYPE_CHECKING:
    from .client import KesselClient

from .client import get_kessel_client
from .models import KesselSyncedResource

LOG = logging.getLogger(__name__)

REPORTER_TYPE = "cost_management"
RESOURCE_NAMESPACE = "cost_management"
RELATION_T_WORKSPACE = "t_workspace"
WORKSPACE_NAMESPACE = "rbac"
WORKSPACE_TYPE = "workspace"

IMMEDIATE_WRITE_TYPES = frozenset({
    "integration",
    "openshift_cluster",
    "openshift_node",
    "openshift_project",
    "aws_account",
    "aws_organizational_unit",
    "gcp_account",
    "gcp_project",
    "azure_subscription_guid",
    "cost_model",
})


def _build_report_request(
    resource_type: str, resource_id: str, org_id: str
) -> report_resource_request_pb2.ReportResourceRequest:
    """Build a ReportResourceRequest with mandatory representations."""
    request = report_resource_request_pb2.ReportResourceRequest(
        inventory_id=f"{org_id}/{resource_type}/{resource_id}",
        type=resource_type,
        reporter_type=REPORTER_TYPE,
        reporter_instance_id=resource_id,
    )

    request.representations.metadata.local_resource_id = resource_id
    request.representations.metadata.api_href = f"/api/cost-management/v1/{resource_type}/{resource_id}"
    request.representations.common.update({"workspace_id": org_id})
    request.representations.reporter.update({"local_resource_id": resource_id})

    if resource_type in IMMEDIATE_WRITE_TYPES:
        request.write_visibility = write_visibility_pb2.IMMEDIATE

    return request


def _get_tuples_url() -> str:
    """Build the Relations API tuples endpoint URL."""
    return f"{settings.KESSEL_RELATIONS_URL.rstrip('/')}{settings.KESSEL_TUPLES_PATH}"


def _track_synced_resource(resource_type: str, resource_id: str, org_id: str, *, synced: bool = True) -> None:
    """Record a resource in the tracking table with its sync status."""
    KesselSyncedResource.objects.update_or_create(
        resource_type=resource_type,
        resource_id=resource_id,
        org_id=org_id,
        defaults={"kessel_synced": synced, "last_synced_at": timezone.now()},
    )


def on_resource_created(resource_type: str, resource_id: str, org_id: str) -> None:
    """Report a new resource to Kessel Inventory AND create SpiceDB tuples.

    Two-phase creation (symmetrical with on_resource_deleted):
      1. ReportResource on Inventory API (registers metadata)
      2. Create t_workspace tuple on Relations API (enables discoverability)

    This is a no-op when AUTHORIZATION_BACKEND != "rebac".
    gRPC/HTTP errors are logged but never propagated to the caller.
    """
    if settings.AUTHORIZATION_BACKEND != "rebac":
        return

    client = get_kessel_client()
    request = _build_report_request(resource_type, resource_id, org_id)

    inventory_ok = True
    try:
        client.inventory_stub.ReportResource(request)
    except grpc.RpcError:
        inventory_ok = False
        LOG.warning(
            log_json(msg="Failed to report resource to Kessel", resource_type=resource_type, resource_id=resource_id),
            exc_info=True,
        )

    tuple_ok = _create_resource_tuples(resource_type, resource_id, org_id)
    _track_synced_resource(resource_type, resource_id, org_id, synced=(inventory_ok and tuple_ok))


def _create_resource_tuples(resource_type: str, resource_id: str, org_id: str) -> bool:
    """Create the SpiceDB t_workspace tuple for a resource via Relations API.

    The on-prem Kessel config disables the CDC-to-consumer pipeline that
    normally creates these tuples.  Koku writes them directly so that
    StreamedListObjects can discover the resource immediately.

    Symmetrical with ``_delete_resource_tuples``.
    """
    url = _get_tuples_url()
    payload = {
        "upsert": True,
        "tuples": [
            {
                "resource": {
                    "type": {"namespace": RESOURCE_NAMESPACE, "name": resource_type},
                    "id": resource_id,
                },
                "relation": RELATION_T_WORKSPACE,
                "subject": {
                    "subject": {
                        "type": {"namespace": WORKSPACE_NAMESPACE, "name": WORKSPACE_TYPE},
                        "id": org_id,
                    }
                },
            }
        ],
    }
    try:
        resp = http_requests.post(url, json=payload, timeout=10)
        if not resp.ok:
            LOG.warning(
                log_json(
                    msg="Relations API tuple create failed",
                    resource_type=resource_type,
                    resource_id=resource_id,
                    status=resp.status_code,
                )
            )
            return False
        return True
    except http_requests.RequestException:
        LOG.warning(
            log_json(
                msg="Relations API tuple create error",
                resource_type=resource_type,
                resource_id=resource_id,
            ),
            exc_info=True,
        )
        return False


def create_structural_tuple(
    resource_type: str, resource_id: str, relation: str, subject_type: str, subject_id: str
) -> bool:
    """Create a cross-type structural relationship tuple via Relations API.

    Used to declare containment hierarchies:
      integration#has_cluster -> openshift_cluster
      openshift_cluster#has_project -> openshift_project

    These enable SpiceDB computed permissions to cascade access upward:
    project access -> cluster visibility -> integration visibility.
    """
    if settings.AUTHORIZATION_BACKEND != "rebac":
        return True

    url = _get_tuples_url()
    payload = {
        "upsert": True,
        "tuples": [
            {
                "resource": {
                    "type": {"namespace": RESOURCE_NAMESPACE, "name": resource_type},
                    "id": resource_id,
                },
                "relation": relation,
                "subject": {
                    "subject": {
                        "type": {"namespace": RESOURCE_NAMESPACE, "name": subject_type},
                        "id": subject_id,
                    }
                },
            }
        ],
    }
    try:
        resp = http_requests.post(url, json=payload, timeout=10)
        if not resp.ok:
            LOG.warning(
                log_json(
                    msg="Structural tuple create failed",
                    resource_type=resource_type,
                    resource_id=resource_id,
                    relation=relation,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    status=resp.status_code,
                )
            )
            return False
        return True
    except http_requests.RequestException:
        LOG.warning(
            log_json(
                msg="Structural tuple create error",
                resource_type=resource_type,
                resource_id=resource_id,
                relation=relation,
            ),
            exc_info=True,
        )
        return False


def _build_delete_request(
    resource_type: str, resource_id: str
) -> delete_resource_request_pb2.DeleteResourceRequest:
    """Build a DeleteResourceRequest from type and ID."""
    return delete_resource_request_pb2.DeleteResourceRequest(
        reference=resource_reference_pb2.ResourceReference(
            resource_type=resource_type,
            resource_id=resource_id,
            reporter=reporter_reference_pb2.ReporterReference(
                type=REPORTER_TYPE,
                instance_id=resource_id,
            ),
        )
    )


def _delete_from_kessel(client: KesselClient, resource_type: str, resource_id: str) -> bool:
    """Call DeleteResource on Kessel Inventory. Returns True on success."""
    request = _build_delete_request(resource_type, resource_id)
    try:
        client.inventory_stub.DeleteResource(request)
        return True
    except grpc.RpcError:
        LOG.warning(
            log_json(msg="Failed to delete resource from Kessel", resource_type=resource_type, resource_id=resource_id),
            exc_info=True,
        )
        return False


def _delete_resource_tuples(resource_type: str, resource_id: str) -> bool:
    """Delete all SpiceDB tuples for a resource via Relations API.

    StreamedListObjects is purely SpiceDB-backed, so the Inventory API's
    DeleteResource alone does NOT revoke discoverability.  This function
    removes ALL ``cost_management/<type>:<id>`` relationships from SpiceDB
    (t_workspace, has_cluster, has_project, etc.) to complete the cleanup.
    """
    url = _get_tuples_url()
    params = {
        "filter.resource_namespace": RESOURCE_NAMESPACE,
        "filter.resource_type": resource_type,
        "filter.resource_id": resource_id,
    }
    try:
        resp = http_requests.delete(url, params=params, headers=get_http_auth_headers(), timeout=10)
        if not resp.ok:
            LOG.warning(
                log_json(
                    msg="Relations API tuple delete failed",
                    resource_type=resource_type,
                    resource_id=resource_id,
                    status=resp.status_code,
                )
            )
            return False
        return True
    except http_requests.RequestException:
        LOG.warning(
            log_json(
                msg="Relations API tuple delete error",
                resource_type=resource_type,
                resource_id=resource_id,
            ),
            exc_info=True,
        )
        return False


def on_resource_deleted(resource_type: str, resource_id: str, org_id: str) -> None:
    """Remove a resource from Kessel Inventory AND SpiceDB if ReBAC is active.

    Called when cost data is fully purged from PostgreSQL (retention expiry).
    Source deletion does NOT trigger this -- historical data must remain queryable.

    Two-phase cleanup (both are independent, best-effort):
      1. DeleteResource on Inventory API (removes metadata)
      2. Delete t_workspace tuple on Relations API (revokes discoverability)
    """
    if settings.AUTHORIZATION_BACKEND != "rebac":
        return

    client = get_kessel_client()
    _delete_from_kessel(client, resource_type, resource_id)
    _delete_resource_tuples(resource_type, resource_id)
    KesselSyncedResource.objects.filter(
        resource_type=resource_type, resource_id=resource_id, org_id=org_id
    ).delete()


def cleanup_orphaned_kessel_resources(provider_uuid: str, org_id: str) -> int:
    """Remove Kessel resources for a provider whose cost data has been fully purged.

    Called from the data expiry pipeline after purge_expired_report_data completes
    for a specific provider_uuid. Only executes when the provider no longer exists
    in the database (was previously deleted via Sources API and data has now expired).

    Returns the number of Kessel resources cleaned up.
    """
    if settings.AUTHORIZATION_BACKEND != "rebac":
        return 0

    from api.models import Provider

    if Provider.objects.filter(uuid=provider_uuid).exists():
        return 0

    tracked = KesselSyncedResource.objects.filter(org_id=org_id)
    if not tracked.exists():
        return 0

    cleaned = 0
    client = get_kessel_client()
    for entry in tracked.iterator():
        _delete_from_kessel(client, entry.resource_type, entry.resource_id)
        _delete_resource_tuples(entry.resource_type, entry.resource_id)
        entry.delete()
        cleaned += 1

    return cleaned
