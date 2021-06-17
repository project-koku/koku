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
        """Check permission to view and update settings data."""
        if request.user.admin:
            return True

        if request.method in permissions.SAFE_METHODS:
            return True

        return False
