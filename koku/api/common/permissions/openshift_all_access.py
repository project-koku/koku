#
# Copyright 2020 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Defines the OCP-on-ALL Access Permissions class."""
from rest_framework import permissions

from api.common.permissions import RESOURCE_TYPES


class OpenshiftAllAccessPermission(permissions.BasePermission):
    """Determines if a user can view Openshift on All data."""

    def has_permission(self, request, view):
        """Check permission to view AWS data."""
        if request.user.admin:
            return True

        resource_access = request.user.access
        if resource_access is None or not isinstance(resource_access, dict):
            return False

        read_access = []
        if request.method in permissions.SAFE_METHODS:
            # Check permissions for read-only request
            for resource_type in RESOURCE_TYPES:
                res_type_access = resource_access.get(resource_type, {})
                read_access.extend(res_type_access.get("read", []))
            return len(read_access) > 0

        return False
