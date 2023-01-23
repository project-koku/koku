#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Defines the Settings Access Permissions class."""
from django.conf import settings
from rest_framework import permissions


class MinimalReportAccessPermission(permissions.BasePermission):
    """Determines if a user can post Minimal data."""

    def has_permission(self, request, view):
        """Check permission to view and post Minimal report data."""
        if settings.ENHANCED_ORG_ADMIN and request.user.admin:
            return True

        if request.method in permissions.SAFE_METHODS:
            return True

        return False
