#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Kessel Inventory client used by the cost management access check."""
import logging

import grpc
from django.conf import settings
from google.protobuf import struct_pb2

from kessel.inventory.v1beta2 import ClientBuilder
from kessel.inventory.v1beta2 import allowed_pb2
from kessel.inventory.v1beta2 import check_request_pb2
from kessel.inventory.v1beta2 import create_tuples_request_pb2
from kessel.inventory.v1beta2 import relation_object_reference_pb2
from kessel.inventory.v1beta2 import relation_object_type_pb2
from kessel.inventory.v1beta2 import relation_subject_reference_pb2
from kessel.inventory.v1beta2 import relationship_pb2
from kessel.inventory.v1beta2 import report_resource_request_pb2
from kessel.inventory.v1beta2 import reporter_reference_pb2
from kessel.inventory.v1beta2 import representation_metadata_pb2
from kessel.inventory.v1beta2 import resource_reference_pb2
from kessel.inventory.v1beta2 import resource_representations_pb2
from kessel.inventory.v1beta2 import subject_reference_pb2
from kessel.inventory.v1beta2 import tuple_service_pb2_grpc
from kessel.inventory.v1beta2 import write_visibility_pb2
from koku.rbac import RbacConnectionError

LOG = logging.getLogger(__name__)

AWS_ACCOUNT_VIEW = "cost_management_aws_account_view"
AWS_ACCOUNT_READ_RELATION = "t_cost_management_aws_account_read"
REPORTER_TYPE = "cost_management"
RBAC_REPORTER = "rbac"


def aws_account_access(principal_id):
    """Return the access dict AWSAccountView already understands.

    ALLOWED on the workspace becomes aws.account read ["*"]. Any other result
    becomes None, which AwsAccessPermission rejects.
    """
    workspace_id = settings.KESSEL_WORKSPACE_ID
    if not workspace_id:
        LOG.error("KESSEL_AUTHZ is on and KESSEL_WORKSPACE_ID is empty")
        return None
    if _workspace_view_allowed(principal_id, workspace_id):
        return {"aws.account": {"read": ["*"]}}
    return None


def report_aws_account(account_id, workspace_id, endpoint=None, reporter_instance_id="cost-management"):
    """Report one AWS account into a workspace."""
    common = struct_pb2.Struct()
    common.update({"workspace_id": workspace_id})
    request = report_resource_request_pb2.ReportResourceRequest(
        type="aws_account",
        reporter_type=REPORTER_TYPE,
        reporter_instance_id=reporter_instance_id,
        representations=resource_representations_pb2.ResourceRepresentations(
            metadata=representation_metadata_pb2.RepresentationMetadata(
                local_resource_id=account_id,
                api_href=f"/api/cost-management/v1/aws-accounts/{account_id}",
            ),
            common=common,
        ),
        write_visibility=write_visibility_pb2.MINIMIZE_LATENCY,
    )
    _inventory_call(endpoint, lambda stub: stub.ReportResource(request))


def grant_aws_account_view(principal_id, workspace_id, role_id, binding_id, endpoint=None):
    """Bind principal_id to AWS account view on workspace_id."""
    tuples = [
        # The v1 role relation only accepts the principal wildcard. The named user
        # is attached on the role binding subject, which the view permission intersects.
        _relationship("rbac", "role", role_id, AWS_ACCOUNT_READ_RELATION, "rbac", "principal", "*"),
        _relationship("rbac", "role_binding", binding_id, "t_role", "rbac", "role", role_id),
        _relationship("rbac", "role_binding", binding_id, "t_subject", "rbac", "principal", principal_id),
        _relationship("rbac", "workspace", workspace_id, "t_binding", "rbac", "role_binding", binding_id),
    ]
    request = create_tuples_request_pb2.CreateTuplesRequest(upsert=True, tuples=tuples)
    target = endpoint or settings.KESSEL_ENDPOINT
    _call(target, lambda channel: tuple_service_pb2_grpc.KesselTupleServiceStub(channel).CreateTuples(request))


def _workspace_view_allowed(principal_id, workspace_id):
    request = check_request_pb2.CheckRequest(
        object=resource_reference_pb2.ResourceReference(
            resource_type="workspace",
            resource_id=workspace_id,
            reporter=reporter_reference_pb2.ReporterReference(type=RBAC_REPORTER),
        ),
        relation=AWS_ACCOUNT_VIEW,
        subject=subject_reference_pb2.SubjectReference(
            resource=resource_reference_pb2.ResourceReference(
                reporter=reporter_reference_pb2.ReporterReference(type=RBAC_REPORTER),
                resource_id=principal_id,
                resource_type="principal",
            )
        ),
    )
    response = _inventory_call(None, lambda stub: stub.Check(request))
    return response.allowed == allowed_pb2.ALLOWED_TRUE


def _inventory_call(endpoint, call):
    target = endpoint or settings.KESSEL_ENDPOINT
    stub, channel = ClientBuilder(target).insecure().build()
    try:
        return call(stub)
    except grpc.RpcError as err:
        LOG.warning("Kessel call failed: %s", err)
        raise RbacConnectionError(err) from err
    finally:
        channel.close()


def _call(target, call):
    channel = grpc.insecure_channel(target)
    try:
        return call(channel)
    except grpc.RpcError as err:
        LOG.warning("Kessel call failed: %s", err)
        raise RbacConnectionError(err) from err
    finally:
        channel.close()


def _relationship(resource_ns, resource_name, resource_id, relation, subject_ns, subject_name, subject_id):
    return relationship_pb2.Relationship(
        resource=_object_ref(resource_ns, resource_name, resource_id),
        relation=relation,
        subject=relation_subject_reference_pb2.RelationSubjectReference(
            subject=_object_ref(subject_ns, subject_name, subject_id)
        ),
    )


def _object_ref(namespace, name, object_id):
    return relation_object_reference_pb2.RelationObjectReference(
        type=relation_object_type_pb2.RelationObjectType(namespace=namespace, name=name),
        id=object_id,
    )
