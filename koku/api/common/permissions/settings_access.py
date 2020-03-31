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
