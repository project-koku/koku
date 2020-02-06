#
# Copyright 2019 Red Hat, Inc.
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
"""Model for our cost model metric map."""
from api.provider.models import Provider
from django.db import models


class CostModelMetricsMap(models.Model):
    """A mapping of data source and cost model metrics."""

    class Meta:
        """Meta for MetricMap."""

        db_table = "cost_models_metrics_map"
        unique_together = ("source_type", "metric")

    OCP_METRIC_CPU_CORE_USAGE_HOUR = "cpu_core_usage_per_hour"
    OCP_METRIC_CPU_CORE_REQUEST_HOUR = "cpu_core_request_per_hour"
    OCP_METRIC_MEM_GB_USAGE_HOUR = "memory_gb_usage_per_hour"
    OCP_METRIC_MEM_GB_REQUEST_HOUR = "memory_gb_request_per_hour"
    OCP_METRIC_STORAGE_GB_USAGE_MONTH = "storage_gb_usage_per_month"
    OCP_METRIC_STORAGE_GB_REQUEST_MONTH = "storage_gb_request_per_month"
    OCP_NODE_MONTH = "node_cost_per_month"

    METRIC_CHOICES = (
        (OCP_METRIC_CPU_CORE_USAGE_HOUR, OCP_METRIC_CPU_CORE_USAGE_HOUR),
        (OCP_METRIC_CPU_CORE_REQUEST_HOUR, OCP_METRIC_CPU_CORE_REQUEST_HOUR),
        (OCP_METRIC_MEM_GB_USAGE_HOUR, OCP_METRIC_MEM_GB_USAGE_HOUR),
        (OCP_METRIC_MEM_GB_REQUEST_HOUR, OCP_METRIC_MEM_GB_REQUEST_HOUR),
        (OCP_METRIC_STORAGE_GB_USAGE_MONTH, OCP_METRIC_STORAGE_GB_USAGE_MONTH),
        (OCP_METRIC_STORAGE_GB_REQUEST_MONTH, OCP_METRIC_STORAGE_GB_REQUEST_MONTH),
        (OCP_NODE_MONTH, OCP_NODE_MONTH),
    )

    source_type = models.CharField(max_length=50, null=False, choices=Provider.PROVIDER_CHOICES)

    metric = models.CharField(max_length=256, null=False, choices=METRIC_CHOICES)

    label_metric = models.CharField(max_length=256, null=False)

    label_measurement = models.CharField(max_length=256, null=False)

    label_measurement_unit = models.CharField(max_length=64, null=False)
