#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Defines the OCP-on-ALL Access Permissions class."""
from rest_framework import permissions

from api.common.permissions import RESOURCE_TYPES


class OpenshiftAllAccessPermission(permissions.BasePermission):
    """Determines if a user can view Openshift on All data."""

    def has_permission(self, request, view):
        """Check permission to view OCP-on-ALL data."""
        if request.user.admin:
            return True

        resource_access = request.user.access
        if resource_access is None or not isinstance(resource_access, dict):
            return False

        read_access = []
        if request.method in permissions.SAFE_METHODS:
            # Check permissions for read-only request
            for resource_type in RESOURCE_TYPES:
                res_type_access = resource_access.get(resource_type, {})
                read_access.extend(res_type_access.get("read", []))
            return len(read_access) > 0

        return False
