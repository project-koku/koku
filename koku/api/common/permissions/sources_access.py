#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Defines the Sources Access Permissions class."""
from django.conf import settings
from rest_framework import permissions

from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.common.permissions.openshift_access import OpenShiftNodePermission
from api.common.permissions.openshift_access import OpenShiftProjectPermission

# On-prem only ingests OpenShift data, so these are the only provider resource
# types worth checking here. A user with org-wide (wildcard) read on one of them
# still needs the sources list for the cost UI to detect whether data exists.
OCP_RESOURCE_TYPES = (
    OpenShiftAccessPermission.resource_type,
    OpenShiftNodePermission.resource_type,
    OpenShiftProjectPermission.resource_type,
)


class SourcesAccessPermission(permissions.BasePermission):
    """Determines if a user can view or manage sources.

    Read operations (GET, HEAD, OPTIONS) require ``sources:*:read`` or org-wide
    (wildcard) read on an OpenShift resource type -- e.g. a "Cost OpenShift
    Viewer" (``openshift.cluster:*``) still needs the sources list to render OCP
    cost pages. Resource-scoped readers (e.g. ``openshift.cluster:["cluster-a"]``)
    are not granted access: the on-prem sources endpoint does no per-source
    filtering, so the response would expose every source's authentication and
    billing metadata.
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
            # An OpenShift viewer with org-wide (wildcard) read still needs to
            # list sources for the cost UI. Scoped readers do not qualify --
            # there is no per-source filtering on-prem, so the list would leak
            # every source's credentials and billing config.
            return any("*" in access.get(res_type, {}).get("read", []) for res_type in OCP_RESOURCE_TYPES)

        sources_write = access.get(self.resource_type, {}).get("write", [])
        return "*" in sources_write
