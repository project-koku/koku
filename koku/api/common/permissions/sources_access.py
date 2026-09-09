#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Defines the Sources Access Permissions class."""
from django.conf import settings
from rest_framework import permissions

from api.common.permissions.aws_access import AWSOUAccessPermission
from api.common.permissions.aws_access import AwsAccessPermission
from api.common.permissions.azure_access import AzureAccessPermission
from api.common.permissions.gcp_access import GcpAccessPermission
from api.common.permissions.gcp_access import GcpProjectPermission
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.common.permissions.openshift_access import OpenShiftNodePermission
from api.common.permissions.openshift_access import OpenShiftProjectPermission

# Provider resource types. A user who can read cost data for any of these also
# needs to read the sources list to render the corresponding cost pages -- the
# UI relies on it to detect whether data is available.
PROVIDER_RESOURCE_TYPES = (
    AwsAccessPermission.resource_type,
    AWSOUAccessPermission.resource_type,
    AzureAccessPermission.resource_type,
    GcpAccessPermission.resource_type,
    GcpProjectPermission.resource_type,
    OpenShiftAccessPermission.resource_type,
    OpenShiftNodePermission.resource_type,
    OpenShiftProjectPermission.resource_type,
)


class SourcesAccessPermission(permissions.BasePermission):
    """Determines if a user can view or manage sources.

    Read operations (GET, HEAD, OPTIONS) require ``sources:*:read`` or read
    access to any provider resource type (e.g. a "Cost OpenShift Viewer" whose
    only permission is ``openshift.cluster`` read still needs the sources list
    to render OCP cost pages).
    Write operations (POST, PATCH, DELETE) require ``sources:*:write``.
    Org admins bypass RBAC checks.
    """

    resource_type = "sources"

    def has_permission(self, request, view):
        """Check permission based on the defined access."""
        if settings.ENHANCED_ORG_ADMIN and request.user.admin:
            return True

        access = request.user.access
        if not access:
            return False

        if request.method in permissions.SAFE_METHODS:
            if "*" in access.get(self.resource_type, {}).get("read", []):
                return True
            # A provider viewer (no sources:*:read, but e.g. openshift.cluster
            # read) still needs to list sources for the cost UI to work.
            return any(access.get(res_type, {}).get("read", []) for res_type in PROVIDER_RESOURCE_TYPES)

        sources_write = access.get(self.resource_type, {}).get("write", [])
        return "*" in sources_write
