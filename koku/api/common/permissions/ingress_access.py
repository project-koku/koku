#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Defines the Ingress Access Permissions class."""
from django.conf import settings
from rest_framework import permissions

from api.common.permissions import RESOURCE_TYPES
from masu.processor import is_ingress_rbac_grace_period_enabled


class IngressAccessPermission(permissions.BasePermission):
    """Utility class for Ingress RBAC checks."""

    def has_permission(self, request, view):

        customer = getattr(request.user, "customer", None)
        if customer and is_ingress_rbac_grace_period_enabled(customer.schema_name):
            return True

        if settings.ENHANCED_ORG_ADMIN and request.user.admin:
            return True

        resource_access = request.user.access
        if resource_access is None or not isinstance(resource_access, dict):
            return False

        if request.method in permissions.SAFE_METHODS:
            # Check permissions for read-only request
            return any(resource_access.get(rt, {}).get("read", []) for rt in RESOURCE_TYPES)

        return False
