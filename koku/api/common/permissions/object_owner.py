#
# Copyright 2018 Red Hat, Inc.
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
"""Defines the Owner Permissions class."""
from rest_framework import permissions


class IsObjectOwner(permissions.BasePermission):
    """Custom permission to only allow owners of an object to edit."""

    def has_object_permission(self, request, view, obj):
        """Permissions are only allowed to the owner of the object."""
        o_user = getattr(obj, "user", None)
        r_user = getattr(request, "user", None)

        if hasattr(o_user, "uuid") and hasattr(r_user, "uuid"):
            o_id = getattr(o_user, "uuid", None)
            r_id = getattr(r_user, "uuid", None)
        else:
            o_id = getattr(o_user, "id", None)
            r_id = getattr(r_user, "id", None)

        if o_id and r_id:
            return o_id == r_id

        return False
