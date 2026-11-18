#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Defines the Ingress Access Permissions class."""
import logging

from api.common import log_json
from api.common.permissions.settings_access import SettingsAccessPermission
from masu.processor import is_ingress_rbac_grace_period_enabled

LOG = logging.getLogger(__name__)


class IngressAccessPermission(SettingsAccessPermission):
    """Determines if a user can access ingress data."""

    def has_permission(self, request, view):
        """Check if the user has permission to access ingress data."""
        customer = getattr(request.user, "customer", None)

        if not customer:
            LOG.warning("Unauthorized ingress access. User has no customer attribute.")
            return False

        if is_ingress_rbac_grace_period_enabled(customer.schema_name):
            LOG.info(log_json(msg="Ingress RBAC grace period is enabled for customer", schema=customer.schema_name))
            return True

        return super().has_permission(request, view)
