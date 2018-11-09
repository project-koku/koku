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

TIMEUNITS = (('hour', 'hour'),
             ('minute', 'minute'),
             ('second', 'second'),
             ('day', 'day'),
             ('month', 'month'),
             ('year', 'year'),
             ('onetime', 'onetime'),
             ('nil', 'nil'))


class Rate(models.Model):
    """A rate for calculating costs.

    A rate is (price * metric_usage / timeunit).
    """

    class Meta:
        """Meta for Rate."""

        unique_together = ('metric', 'price', 'timeunit')

    description = models.TextField()
    metric = models.CharField(max_length=100, null=False)
    name = models.CharField(max_length=255, null=False)
    price = models.DecimalField(max_digits=25, decimal_places=6, null=False)
    timeunit = models.CharField(max_length=100, null=False, choices=TIMEUNITS,
                                default=TIMEUNITS[[0][0]])
