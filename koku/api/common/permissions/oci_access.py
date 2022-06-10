#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Defines the OCI Access Permissions class."""
from django.conf import settings
from rest_framework import permissions


class OCIAccessPermission(permissions.BasePermission):
    """Determines if a user can view OCI data."""

    resource_type = "oci.payer_tenant_id"

    def has_permission(self, request, view):
        """Check permission to view OCI data."""
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


class OCITenantPermission(OCIAccessPermission):
    """Determines if a user can view OCI data."""

    resource_type = "oci.payer_tenant_id"
