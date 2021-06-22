#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Defines the IBM Access Permissions class."""
from rest_framework import permissions


class IbmAccessPermission(permissions.BasePermission):
    """Determines if a user can view IBM data."""

    resource_type = "ibm.account"

    def has_permission(self, request, view):
        """Check permission to view IBM data."""
        if request.user.admin:
            return True

        resource_access = request.user.access
        if resource_access is None or not isinstance(resource_access, dict):
            return False

        res_type_access = resource_access.get(IbmAccessPermission.resource_type, {})
        if request.method in permissions.SAFE_METHODS:
            # Check permissions for read-only request
            read_access = res_type_access.get("read", [])
            return len(read_access) > 0

        return False
