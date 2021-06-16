#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Defines the Resource Type Access Permissions class."""
from rest_framework import permissions


class ResourceTypeAccessPermission(permissions.BasePermission):
    """Determines if a user can view resource-type data."""

    resource_type = "resource_type"

    def has_permission(self, request, view):
        """Check permission to view resource-type data."""
        if request.user.admin:
            return True

        return False
