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

"""Models for OCP cost view tables."""

from django.db import models


class CostSummary(models.Model):
    """A summary view of OCP costs."""

    class Meta:
        """Meta for CostSummary."""

        db_table = 'reporting_costs_summary'
        managed = False
    id = models.BigAutoField(primary_key=True)

    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=False)

    pod = models.CharField(max_length=253, null=True)

    node = models.CharField(max_length=253, null=True)

    usage_start = models.DateTimeField(null=False)
    usage_end = models.DateTimeField(null=False)

    pod_charge_cpu_core_hours = models.DecimalField(
        max_digits=24,
        decimal_places=6,
        null=True
    )

    pod_charge_memory_gigabyte_hours = models.DecimalField(
        max_digits=24,
        decimal_places=6,
        null=True
    )

    persistentvolumeclaim_charge_gb_month = models.DecimalField(
        max_digits=24,
        decimal_places=6,
        null=True
    )
