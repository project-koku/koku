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
"""Defines the Customer Owner Permissions class."""
from rest_framework import permissions

from api.iam.models import Customer


class IsCustomerOwner(permissions.BasePermission):
    """Permission class for customer owners to use create/delete methods."""

    def has_permission(self, request, view):
        """Allow permission only for to create/delete to customer owners.

        Authenticated users may perform read methods.
        """
        if request.user and request.user.is_authenticated:
            if request.method in permissions.SAFE_METHODS:
                # Check permissions for read-only request
                return True

            group = request.user.groups.first()
            if group:
                customer = Customer.objects.get(pk=group.id)
                is_customer_owner = customer.owner.id == request.user.id
                return is_customer_owner

        return False
