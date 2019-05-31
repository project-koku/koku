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

"""Models for rates."""
from uuid import uuid4

from django.contrib.postgres.fields import JSONField
from django.db import models

from api.metrics.models import CostModelMetricsMap


class Rate(models.Model):
    """A rate for calculating charge.

    Support various types of rates (flat, fixed, tiered, discount).
    """

    uuid = models.UUIDField(default=uuid4, editable=False,
                            unique=True, null=False)

    metric = models.CharField(max_length=256, null=False,
                              choices=CostModelMetricsMap.METRIC_CHOICES,
                              default=CostModelMetricsMap.OCP_METRIC_CPU_CORE_USAGE_HOUR)
    rates = JSONField(default=dict)

    class Meta:
        """Meta for Rate."""

        ordering = ['-id']


class RateMap(models.Model):
    """Map for provider and rate objects."""

    provider_uuid = models.UUIDField(default=uuid4, editable=False,
                                     unique=False, null=False)

    rate = models.ForeignKey('Rate', null=True, blank=True,
                             on_delete=models.CASCADE)

    class Meta:
        """Meta for Rate."""

        ordering = ['-id']
        unique_together = ('provider_uuid', 'rate')
