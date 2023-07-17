#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Defines the Settings Access Permissions class."""
from rest_framework import permissions


class SettingsAccessPermission(permissions.BasePermission):
    """Determines if a user can update Settings data."""

    resource_type = "settings"

    def has_permission(self, request, view):
        """Check permission based on the defined access."""
        if request.user.admin:
            return True

        if not request.user.access:
            return False

        if request.method in permissions.SAFE_METHODS:
            if request.user.access.get(self.resource_type, {}).get("read", []):
                return True
        else:
            setting_write = request.user.access.get(self.resource_type, {}).get("write", [])
            if "*" in setting_write:
                return True
        return False
