#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Defines the Rate Access Permissions class."""
from uuid import UUID

from rest_framework import permissions


class CostModelsAccessPermission(permissions.BasePermission):
    """Determines if a user has access to Cost Model APIs."""

    def get_uuid_from_url(self, request):
        """Get the uuid from the request url."""
        url_parts = request.META.get("PATH_INFO").split("/")
        try:
            given_uuid = str(UUID(url_parts[url_parts.index("cost-models") + 1]))
        except ValueError:
            given_uuid = None
        return given_uuid

    def has_permission(self, request, view):
        """Check permission based on the defined access."""
        if request.user.admin:
            return True

        if not request.user.access:
            return False

        if request.method in permissions.SAFE_METHODS:
            rates_read = request.user.access.get("cost_model", {}).get("read", [])
            if rates_read:
                return True
        else:
            rates_write = request.user.access.get("cost_model", {}).get("write", [])
            if "*" in rates_write:
                return True
            if self.get_uuid_from_url(request) in rates_write:
                return True
        return False
