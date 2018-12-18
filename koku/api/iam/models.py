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

"""Models for identity and access management."""

from uuid import uuid4

from django.contrib.postgres.fields import JSONField
from django.db import models
from tenant_schemas.models import TenantMixin


class Customer(models.Model):
    """A Koku Customer.

    A customer is an organization of N-number of users

    """

    date_created = models.DateTimeField(auto_now_add=True)
    uuid = models.UUIDField(default=uuid4, editable=False,
                            unique=True, null=False)
    account_id = models.CharField(max_length=150, blank=False, null=True, unique=True)
    schema_name = models.TextField(unique=True, null=False, default='public')

    class Meta:
        ordering = ['schema_name']


class User(models.Model):
    """A Koku User."""

    uuid = models.UUIDField(default=uuid4, editable=False,
                            unique=True, null=False)
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(blank=True)
    date_created = models.DateTimeField(auto_now_add=True)
    is_active = models.NullBooleanField(default=True)
    customer = models.ForeignKey('Customer', null=True, on_delete=models.CASCADE)

    class Meta:
        ordering = ['username']


class UserPreference(models.Model):
    """A user preference."""

    uuid = models.UUIDField(default=uuid4, editable=False,
                            unique=True, null=False)
    user = models.ForeignKey('User', null=False, on_delete=models.CASCADE)
    preference = JSONField(default=dict)
    name = models.CharField(max_length=255, null=False, default=uuid4)
    description = models.CharField(max_length=255, null=True)

    class Meta:
        """Meta for UserPreference."""

        unique_together = ('name', 'user')
        ordering = ('name',)

    def __str__(self):
        """Return string representation of user preferences."""
        return 'UserPreference({}): User: {}, Preference: {}'.format(self.name,
                                                                     self.user,
                                                                     self.preference)


class Tenant(TenantMixin):
    """The model used to create a tenant schema."""

    # Override the mixin domain url to make it nullable, non-unique
    domain_url = None

    # Delete all schemas when a tenant is removed
    auto_drop_schema = True
