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

from django.contrib.auth.models import Group as DjangoGroup, User as DjangoUser
from django.db import models


class Customer(DjangoGroup):
    """A Koku Customer.

    A customer is an organization of N-number of users

    """

    date_created = models.DateTimeField(auto_now_add=True)
    owner = models.ForeignKey('User', null=False, on_delete=models.PROTECT)
    uuid = models.UUIDField(default=uuid4, editable=False,
                            unique=True, null=False)

    class Meta:
        ordering = ['name']


class User(DjangoUser):
    """A Koku User."""

    uuid = models.UUIDField(default=uuid4, editable=False,
                            unique=True, null=False)

    class Meta:
        ordering = ['username']
