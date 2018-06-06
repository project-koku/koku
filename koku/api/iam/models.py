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

from django.conf import settings
from django.contrib.auth.models import Group as DjangoGroup, User as DjangoUser
from django.contrib.postgres.fields import JSONField
from django.db import models
from django.utils import timezone
from tenant_schemas.models import TenantMixin


class Customer(DjangoGroup):
    """A Koku Customer.

    A customer is an organization of N-number of users

    """

    date_created = models.DateTimeField(auto_now_add=True)
    owner = models.ForeignKey('User', null=True, on_delete=models.SET_NULL)
    uuid = models.UUIDField(default=uuid4, editable=False,
                            unique=True, null=False)
    schema_name = models.TextField(unique=True, null=False, default='public')

    class Meta:
        ordering = ['name']


class User(DjangoUser):
    """A Koku User."""

    uuid = models.UUIDField(default=uuid4, editable=False,
                            unique=True, null=False)

    class Meta:
        ordering = ['username']


def token_expiration():
    """Get the date time for token expiration."""
    expire_setting = settings.PASSWORD_RESET_TIMEOUT_DAYS
    expire = timezone.now() + timezone.timedelta(days=expire_setting)
    return expire


class ResetToken(models.Model):
    """A Reset Token for managing user password resets."""

    token = models.UUIDField(default=uuid4, editable=False,
                             unique=True, null=False)
    expiration_date = models.DateTimeField(default=token_expiration)
    user = models.ForeignKey('User', null=False, on_delete=models.CASCADE)
    used = models.BooleanField(default=False)


class UserPreference(models.Model):
    """A user preference."""

    uuid = models.UUIDField(default=uuid4, editable=False,
                            unique=True, null=False)
    user = models.ForeignKey('User', null=False, on_delete=models.CASCADE)
    preference = JSONField(default=dict)
    name = models.CharField(max_length=255, null=False, default=uuid4)
    description = models.CharField(max_length=255, null=True)

    class Meta:
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


class CostEntryStatus(models.Model):
    """Information on the state of the cost usage report."""
    provider = models.ForeignKey('Provider', null=True,
                                 on_delete=models.CASCADE)
    report_name = models.CharField(max_length=128, null=False, unique=True)
    cursor_position = models.PositiveIntegerField()
    last_completed_datetime = models.DateTimeField(null=False)
    last_started_datetime = models.DateTimeField(null=False)
