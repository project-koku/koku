#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Defines the Ingress Access Permissions class."""
from api.common.permissions.settings_access import SettingsAccessPermission
from masu.processor import is_ingress_rbac_grace_period_enabled


class IngressAccessPermission(SettingsAccessPermission):
    """Determines if a user can access ingress data."""

    def has_permission(self, request, view):
        # bypasses RBAC checks if ingress RBAC grace period is enabled
        customer = getattr(request.user, "customer", None)
        if customer and is_ingress_rbac_grace_period_enabled(customer.schema_name):
            return True

        # otherwise check settings access permissions
        return super().has_permission(request, view)
