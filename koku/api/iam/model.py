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

from django.db import models
from django.contrib.auth.models import User as DjangoUser, \
                                       Group as DjangoGroup

class Customer(DjangoGroup):
    """
        A Koku Customer

        A customer is an organization of N-number of users
    """
    date_created = models.DateTimeField(auto_now_add=True)
    owner = models.ForeignKey('User', null=True, on_delete=models.PROTECT)

class User(DjangoUser):
    """A Koku User"""
