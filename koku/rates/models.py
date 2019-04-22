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


class Rate(models.Model):
    """A rate for calculating charge.

    Support various types of rates (flat, fixed, tiered, discount).
    """

    METRIC_CPU_CORE_USAGE_HOUR = 'cpu_core_usage_per_hour'
    METRIC_CPU_CORE_REQUEST_HOUR = 'cpu_core_request_per_hour'
    METRIC_MEM_GB_USAGE_HOUR = 'memory_gb_usage_per_hour'
    METRIC_MEM_GB_REQUEST_HOUR = 'memory_gb_request_per_hour'
    METRIC_STORAGE_GB_USAGE_MONTH = 'storage_gb_usage_per_month'
    METRIC_STORAGE_GB_REQUEST_MONTH = 'storage_gb_request_per_month'

    METRIC_CHOICES = ((METRIC_CPU_CORE_USAGE_HOUR, METRIC_CPU_CORE_USAGE_HOUR),
                      (METRIC_CPU_CORE_REQUEST_HOUR, METRIC_CPU_CORE_REQUEST_HOUR),
                      (METRIC_MEM_GB_USAGE_HOUR, METRIC_MEM_GB_USAGE_HOUR),
                      (METRIC_MEM_GB_REQUEST_HOUR, METRIC_MEM_GB_REQUEST_HOUR),
                      (METRIC_STORAGE_GB_USAGE_MONTH, METRIC_STORAGE_GB_USAGE_MONTH),
                      (METRIC_STORAGE_GB_REQUEST_MONTH, METRIC_STORAGE_GB_REQUEST_MONTH),)

    uuid = models.UUIDField(default=uuid4, editable=False,
                            unique=True, null=False)

    metric = models.CharField(max_length=256, null=False,
                              choices=METRIC_CHOICES, default=METRIC_CPU_CORE_USAGE_HOUR)
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
