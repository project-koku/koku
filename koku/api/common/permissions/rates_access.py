#
# Copyright 2019 Red Hat, Inc.
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
"""Defines the Group Access Permissions class."""
from uuid import UUID

from rest_framework import permissions


class RatesAccessPermission(permissions.BasePermission):
    """Determines if a user has access to Group APIs."""

    def get_uuid_from_url(self, request):
        """Get the uuid from the request url."""
        url_parts = request.META.get('PATH_INFO').split('/')
        try:
            given_uuid = str(UUID(url_parts[url_parts.index('rates') + 1]))
        except ValueError:
            given_uuid = None
        return given_uuid

    def has_permission(self, request, view):
        """Check permission based on the defined access."""
        if request.user.admin:
            return True
        if request.method in permissions.SAFE_METHODS:
            username = request.query_params.get('username')
            if username:
                decoded = request.user.identity_header.get('decoded', {})
                identity_username = decoded.get('identity', {}).get('user', {}).get('username')
                return username == identity_username
            else:
                group_read = request.user.access.get('rate', {}).get('read', [])
                if group_read:
                    return True
        else:
            group_write = request.user.access.get('rate', {}).get('write', [])
            if '*' in group_write:
                return True
            if self.get_uuid_from_url(request) in group_write:
                return True
        return False
