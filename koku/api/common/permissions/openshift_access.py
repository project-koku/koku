#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Defines the OpenShift Access Permissions class."""
from django.conf import settings
from rest_framework import permissions


class OpenShiftAccessPermission(permissions.BasePermission):
    """Determines if a user can view OpenShift data."""

    resource_type = "openshift.cluster"

    def has_permission(self, request, view):
        """Check permission to view OpenShift data."""
        if settings.ENHANCED_ORG_ADMIN and request.user.admin:
            return True

        resource_access = request.user.access
        if resource_access is None or not isinstance(resource_access, dict):
            return False

        res_type_access = resource_access.get(self.resource_type, {})
        if request.method in permissions.SAFE_METHODS:
            # Check permissions for read-only request
            read_access = res_type_access.get("read", [])
            return len(read_access) > 0

        return False


class OpenShiftProjectPermission(OpenShiftAccessPermission):
    """Determines if a user can view OpenShift data."""

    resource_type = "openshift.project"


class OpenShiftNodePermission(OpenShiftAccessPermission):
    """Determines if a user can view OpenShift data."""

    resource_type = "openshift.node"
