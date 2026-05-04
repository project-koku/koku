#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Defines the Sources Access Permissions class."""
from django.conf import settings
from rest_framework import permissions


class SourcesAccessPermission(permissions.BasePermission):
    """Determines if a user can manage sources.

    Read operations (GET, HEAD, OPTIONS) require sources:*:read.
    Write operations (POST, PUT, PATCH, DELETE) require sources:*:write.
    Org admins bypass RBAC checks.
    """

    resource_type = "sources"

    def has_permission(self, request, view):
        """Check permission based on the defined access."""
        if settings.ENHANCED_ORG_ADMIN and request.user.admin:
            return True

        if not request.user.access:
            return False

        if request.method in permissions.SAFE_METHODS:
            if request.user.access.get(self.resource_type, {}).get("read", []):
                return True
        else:
            sources_write = request.user.access.get(self.resource_type, {}).get("write", [])
            if "*" in sources_write:
                return True
        return False
