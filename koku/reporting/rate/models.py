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

from django.db import models


class Rate(models.Model):
    """A rate for calculating costs.

    A rate is (price * metric_usage / timeunit).
    """

    uuid = models.UUIDField(default=uuid4, editable=False,
                            unique=True, null=False)
    name = models.CharField(max_length=255, null=False)
    description = models.TextField()
    timeunit = models.CharField(max_length=100, null=False)
    price = models.DecimalField(max_digits=25, decimal_places=6, null=False)
    metric = models.CharField(max_length=100, null=False)
