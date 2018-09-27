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
            self.model = Provider.objects.all().filter(uuid=uuid).get()
        except (ObjectDoesNotExist, ValidationError) as e:
            raise(ProviderManagerError(str(e)))

    @staticmethod
    def get_providers_queryset_for_customer(customer):
        """Get all providers created by a given customer."""
        return Provider.objects.all().filter(customer=customer)

    def get_name(self):
        """Get the name of the provider."""
        return self.model.name

    def is_removable_by_user(self, current_user):
        """Determine if the current_user can remove the provider."""
        return self.model.customer == current_user.customer

    @transaction.atomic
    def remove(self, current_user, customer_remove_context=False):
        """Remove the provider with current_user."""
        if self.is_removable_by_user(current_user):
            authentication_model = self.model.authentication
            billing_source = self.model.billing_source

            authentication_model.delete()
            billing_source.delete()
            self.model.delete()
            LOG.info('Provider: {} removed by {}'.format(self.model.name, current_user.username))
        else:
            err_msg = 'User {} does not have permission to delete provider {}'.format(current_user, str(self.model))
            raise ProviderManagerError(err_msg)
