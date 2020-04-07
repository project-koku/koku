#
# Copyright 2020 Red Hat, Inc.
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
"""Constants file."""
from api.models import Provider

"""Model for our cost model metric map."""
OCP_METRIC_CPU_CORE_USAGE_HOUR = "cpu_core_usage_per_hour"
OCP_METRIC_CPU_CORE_REQUEST_HOUR = "cpu_core_request_per_hour"
OCP_METRIC_MEM_GB_USAGE_HOUR = "memory_gb_usage_per_hour"
OCP_METRIC_MEM_GB_REQUEST_HOUR = "memory_gb_request_per_hour"
OCP_METRIC_STORAGE_GB_USAGE_MONTH = "storage_gb_usage_per_month"
OCP_METRIC_STORAGE_GB_REQUEST_MONTH = "storage_gb_request_per_month"
OCP_NODE_MONTH = "node_cost_per_month"
OCP_CLUSTER_MONTH = "cluster_cost_per_month"

INFRASTRUCTURE_COST_TYPE = "Infrastructure"
SUPPLEMENTARY_COST_TYPE = "Supplementary"

METRIC_CHOICES = (
    (OCP_METRIC_CPU_CORE_USAGE_HOUR, OCP_METRIC_CPU_CORE_USAGE_HOUR),
    (OCP_METRIC_CPU_CORE_REQUEST_HOUR, OCP_METRIC_CPU_CORE_REQUEST_HOUR),
    (OCP_METRIC_MEM_GB_USAGE_HOUR, OCP_METRIC_MEM_GB_USAGE_HOUR),
    (OCP_METRIC_MEM_GB_REQUEST_HOUR, OCP_METRIC_MEM_GB_REQUEST_HOUR),
    (OCP_METRIC_STORAGE_GB_USAGE_MONTH, OCP_METRIC_STORAGE_GB_USAGE_MONTH),
    (OCP_METRIC_STORAGE_GB_REQUEST_MONTH, OCP_METRIC_STORAGE_GB_REQUEST_MONTH),
    (OCP_NODE_MONTH, OCP_NODE_MONTH),
    (OCP_CLUSTER_MONTH, OCP_CLUSTER_MONTH),
)

COST_TYPE_CHOICES = (
    (INFRASTRUCTURE_COST_TYPE, INFRASTRUCTURE_COST_TYPE),
    (SUPPLEMENTARY_COST_TYPE, SUPPLEMENTARY_COST_TYPE),
)

SOURCE_TYPE_MAP = {
    Provider.PROVIDER_OCP: "OpenShift Container Platform",
    Provider.PROVIDER_AWS: "Amazon Web Services",
    Provider.PROVIDER_AZURE: "Microsoft Azure",
}

COST_MODEL_METRIC_MAP = [
    {
        "source_type": "OCP",
        "metric": "cpu_core_usage_per_hour",
        "label_metric": "CPU",
        "label_measurement": "Usage",
        "label_measurement_unit": "core-hours",
        "default_cost_type": "Supplementary",
    },
    {
        "source_type": "OCP",
        "metric": "cpu_core_request_per_hour",
        "label_metric": "CPU",
        "label_measurement": "Request",
        "label_measurement_unit": "core-hours",
        "default_cost_type": "Supplementary",
    },
    {
        "source_type": "OCP",
        "metric": "memory_gb_usage_per_hour",
        "label_metric": "Memory",
        "label_measurement": "Usage",
        "label_measurement_unit": "GB-hours",
        "default_cost_type": "Supplementary",
    },
    {
        "source_type": "OCP",
        "metric": "memory_gb_request_per_hour",
        "label_metric": "Memory",
        "label_measurement": "Request",
        "label_measurement_unit": "GB-hours",
        "default_cost_type": "Supplementary",
    },
    {
        "source_type": "OCP",
        "metric": "storage_gb_usage_per_month",
        "label_metric": "Storage",
        "label_measurement": "Usage",
        "label_measurement_unit": "GB-month",
        "default_cost_type": "Supplementary",
    },
    {
        "source_type": "OCP",
        "metric": "storage_gb_request_per_month",
        "label_metric": "Storage",
        "label_measurement": "Request",
        "label_measurement_unit": "GB-month",
        "default_cost_type": "Supplementary",
    },
    {
        "source_type": "OCP",
        "metric": "node_cost_per_month",
        "label_metric": "Node",
        "label_measurement": "Currency",
        "label_measurement_unit": "node-month",
        "default_cost_type": "Infrastructure",
    },
    {
        "source_type": "OCP",
        "metric": "cluster_cost_per_month",
        "label_metric": "Cluster",
        "label_measurement": "Currency",
        "label_measurement_unit": "cluster-month",
        "default_cost_type": "Infrastructure",
    },
]
