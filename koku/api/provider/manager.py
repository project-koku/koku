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
"""Management capabilities for Provider functionality."""

import logging

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction

from api.provider.models import Provider


LOG = logging.getLogger(__name__)


class ProviderManagerError(Exception):
    """General Exception class for ProviderManager errors."""

    def __init__(self, message):
        """Set custom error message for ProviderManager errors."""
        self.message = message


class ProviderManager:
    """Provider Manager to manage operations related to backend providers."""

    def __init__(self, uuid):
        """Establish provider manager database objects."""
        try:
            self.model = Provider.objects.all().filter(uuid=uuid)
            self.created_by = self.model.get().created_by
            self.owned_by = self.model.get().customer.owner
        except (ObjectDoesNotExist, ValidationError) as e:
            raise(ProviderManagerError(str(e)))

    @staticmethod
    def get_providers_for_customer(customer):
        """Get all providers created by a given customer."""
        return Provider.objects.all().filter(customer=customer)

    def is_removable_by_user(self, current_user):
        """Determine if the current_user can remove the provider."""
        if current_user.is_superuser:
            return True

        if current_user.id != self.owned_by.id:
            if current_user.id != self.created_by.id:
                return False
        return True

    @transaction.atomic
    def remove(self, current_user):
        """Remove the provider with current_user."""
        if self.is_removable_by_user(current_user):
            self.model.delete()
        else:
            err_msg = 'User {} does not have permission to delete provider {}'.format(current_user, str(self.model))
            raise ProviderManagerError(err_msg)
