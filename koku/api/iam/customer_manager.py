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
"""Management capabilities for Customer functionality."""

import logging

from django.core.exceptions import ValidationError

from api.iam.models import Customer, Tenant
from api.iam.serializers import CustomerSerializer

LOG = logging.getLogger(__name__)


class CustomerManagerError(Exception):
    """General Exception class for CustomerManager errors."""

    pass


class CustomerManagerDoesNotExist(Exception):
    """CustomerManager could not find customer error."""

    pass


class CustomerManagerPermissionError(Exception):
    """CustomerManager permission error."""

    pass


class CustomerManager:
    """Customer Manager to manage operations related to customer tasks."""

    def __init__(self, uuid):
        """Establish provider manager database objects."""
        self.model = None
        self.tenant = None
        try:
            query = Customer.objects.all().filter(uuid=uuid)
            self.model = query.get()
        except Customer.DoesNotExist as e:
            msg = 'Could not find customer with uuid: {}'.format(uuid)
            raise CustomerManagerDoesNotExist(msg)
        except ValidationError as e:
            raise(CustomerManagerError(str(e)))

        try:
            self.tenant = self._get_tenant_query().get()
        except Tenant.DoesNotExist as e:
            msg = 'No tenant found for {}'.format(self.get_name())
            LOG.error(msg)

    def get_model(self):
        """Get the model object for the customer."""
        return self.model

    def _get_tenant_query(self):
        """Get the tenant model query for the customer."""
        customer_schema_name = self.get_model().schema_name
        query = Tenant.objects.all().filter(schema_name=customer_schema_name)
        return query

    def get_tenant(self):
        """Get the tenant object for the customer."""
        return self.tenant

    def get_name(self):
        """Get the name of the customer."""
        return self.model.name

    def get_users_for_customer(self):
        """List of users that belong to the customer."""
        group = CustomerSerializer.get_authentication_group_for_customer(self.model)
        users = CustomerSerializer.get_users_for_group(group)
        return users

    def remove_users(self, current_user):
        """Remove users associated with this customer."""
        if current_user.is_superuser:
            users = self.get_users_for_customer()
            if users:
                for user in users:
                    LOG.info('Removing User: {}'.format(user))
                    user.delete()
        else:
            err_msg = '{} does not have pemrissions to remove users.'.format(current_user)
            raise CustomerManagerPermissionError(err_msg)

    def remove_tenant(self, current_user):
        """Remove tenant associated with this customer."""
        if current_user.is_superuser:
            tenant = self.get_tenant()
            if tenant:
                customer_name = self.get_model().name
                LOG.info('Removing tenant for customer: {}'.format(customer_name))
                tenant.delete()
        else:
            err_msg = '{} does not have pemrissions to tenant.'.format(current_user)
            raise CustomerManagerPermissionError(err_msg)
