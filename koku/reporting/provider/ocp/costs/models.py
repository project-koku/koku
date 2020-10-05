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
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import JSONField


class CostSummary(models.Model):
    """A summary table of OCP costs."""

    class Meta:
        """Meta for CostSummary."""

        db_table = "reporting_ocpcosts_summary"
        indexes = [
            models.Index(fields=["usage_start"], name="ocpcostsum_usage_start_idx"),
            models.Index(fields=["namespace"], name="ocpcostsum_namespace_idx", opclasses=["varchar_pattern_ops"]),
            models.Index(fields=["node"], name="ocpcostsum_node_idx", opclasses=["varchar_pattern_ops"]),
            GinIndex(fields=["pod_labels"], name="ocpcostsum_pod_labels_idx"),
        ]

    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE, null=True)

    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=True)

    pod = models.CharField(max_length=253, null=True)

    node = models.CharField(max_length=253, null=True)

    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)

    pod_charge_cpu_core_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_charge_memory_gigabyte_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    persistentvolumeclaim_charge_gb_month = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    # Need more precision on calculated fields, otherwise there will be
    # Rounding errors
    infra_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    # This field is used in place of infrastructure_cost when
    # grouping by project
    project_infra_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    project_markup_cost = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_labels = JSONField(null=True)

    monthly_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
