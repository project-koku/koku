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

from api.iam.models import Customer
from api.iam.serializers import CustomerSerializer

LOG = logging.getLogger(__name__)


class CustomerManagerError(Exception):
    """General Exception class for CustomerManager errors."""

    def __init__(self, message):
        """Set custom error message for CustomerManager errors."""
        self.message = message


class CustomerManagerDoesNotExist(Exception):
    """CustomerManager could not find customer error."""

    def __init__(self, message):
        """Set custom error message for CustomerManager errors."""
        self.message = message


class CustomerManagerPermissionError(Exception):
    """CustomerManager permission error."""

    def __init__(self, message):
        """Set custom error message for CustomerManager errors."""
        self.message = message


class CustomerManager:
    """Customer Manager to manage operations related to customer tasks."""

    def __init__(self, uuid):
        """Establish provider manager database objects."""
        self.model = None
        try:
            query = Customer.objects.all().filter(uuid=uuid)
            self.model = query.get()
        except Customer.DoesNotExist as e:
            msg = 'Could not find customer with uuid: {}'.format(uuid)
            raise CustomerManagerDoesNotExist(msg)
        except ValidationError as e:
            raise(CustomerManagerError(str(e)))

    def get_model(self):
        """Get the model object for the customer."""
        return self.model

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
