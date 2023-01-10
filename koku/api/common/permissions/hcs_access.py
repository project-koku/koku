#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Defines the Settings Access Permissions class."""
from rest_framework import permissions


class HCSAccessPermission(permissions.BasePermission):
    """Determines if a user can post HCS data."""

    def has_permission(self, request, view):
        """Check permission to view and post HCS report data."""
        if request.user.admin:
            return True

        if request.method in permissions.SAFE_METHODS:
            return True

        return False
