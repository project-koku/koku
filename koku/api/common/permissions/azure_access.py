#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Defines the Azure Access Permissions class."""
from django.conf import settings
from rest_framework import permissions


class AzureAccessPermission(permissions.BasePermission):
    """Determines if a user can view Azure data."""

    resource_type = "azure.subscription_guid"

    def has_permission(self, request, view):
        """Check permission to view Azure data."""
        if settings.ENHANCED_ORG_ADMIN and request.user.admin:
            return True

        resource_access = request.user.access
        if resource_access is None or not isinstance(resource_access, dict):
            return False

        res_type_access = resource_access.get(AzureAccessPermission.resource_type, {})
        if request.method in permissions.SAFE_METHODS:
            # Check permissions for read-only request
            read_access = res_type_access.get("read", [])
            return len(read_access) > 0

        return False
