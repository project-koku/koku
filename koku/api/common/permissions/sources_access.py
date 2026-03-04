#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Defines the Sources Access Permissions class for ONPREM deployments.

On-prem sources are first-class Kessel ``integration`` resources whose
visibility is computed by SpiceDB from workspace and structural
relationships (integration -> cluster -> project).

Read access is granted when the user has any ``integration`` read
access (populated by StreamedListObjects in the access provider).
Write operations require ``settings`` write access.
"""
from django.conf import settings
from rest_framework import permissions


class SourcesAccessPermission(permissions.BasePermission):
    """Allow source reads when the user has integration resource access.

    Write operations still require ``settings`` write (admin privilege).
    """

    def has_permission(self, request, view):
        if settings.ENHANCED_ORG_ADMIN and request.user.admin:
            return True

        resource_access = request.user.access
        if resource_access is None or not isinstance(resource_access, dict):
            return False

        if request.method in permissions.SAFE_METHODS:
            integration_read = resource_access.get("integration", {}).get("read", [])
            return bool(integration_read)

        setting_write = resource_access.get("settings", {}).get("write", [])
        return "*" in setting_write
