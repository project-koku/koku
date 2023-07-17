#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Defines the Settings Access Permissions class."""
from django.conf import settings
from rest_framework import permissions


class SettingsAccessPermission(permissions.BasePermission):
    """Determines if a user can update Settings data."""

    resource_type = "settings"

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
            setting_write = request.user.access.get(self.resource_type, {}).get("write", [])
            if "*" in setting_write:
                return True
        return False


# TODO: Remove after settings switch over
# Deprecated check:
class DeprecatedSettingsAccessPermission(permissions.BasePermission):
    """Determines if a user can update Settings data."""

    resource_type = "settings"

    def has_permission(self, request, view):
        """Check permission to view and update settings data."""
        if request.user.admin:
            return True

        if request.method in permissions.SAFE_METHODS:
            return True

        return False
