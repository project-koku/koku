#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Constants file."""
from api.models import Provider

"""Model for our cost model metric map."""
OCP_METRIC_CPU_CORE_USAGE_HOUR = "cpu_core_usage_per_hour"
OCP_METRIC_CPU_CORE_REQUEST_HOUR = "cpu_core_request_per_hour"
OCP_METRIC_CPU_CORE_EFFECTIVE_USAGE_HOUR = "cpu_core_effective_usage_per_hour"
OCP_METRIC_MEM_GB_USAGE_HOUR = "memory_gb_usage_per_hour"
OCP_METRIC_MEM_GB_REQUEST_HOUR = "memory_gb_request_per_hour"
OCP_METRIC_MEM_GB_EFFECTIVE_USAGE_HOUR = "memory_gb_effective_usage_per_hour"
OCP_METRIC_STORAGE_GB_USAGE_MONTH = "storage_gb_usage_per_month"
OCP_METRIC_STORAGE_GB_REQUEST_MONTH = "storage_gb_request_per_month"
OCP_NODE_CORE_HOUR = "node_core_cost_per_hour"
OCP_NODE_MONTH = "node_cost_per_month"
OCP_NODE_CORE_MONTH = "node_core_cost_per_month"
OCP_CLUSTER_MONTH = "cluster_cost_per_month"
OCP_CLUSTER_CORE_HOUR = "cluster_core_cost_per_hour"
OCP_CLUSTER_HOUR = "cluster_cost_per_hour"
OCP_PVC_MONTH = "pvc_cost_per_month"
OCP_VM_MONTH = "vm_cost_per_month"
OCP_VM_HOUR = "vm_cost_per_hour"

CPU = "cpu"
MEM = "memory"
STORAGE = "storage"

PVC_DISTRIBUTION = "pvc"
DEFAULT_DISTRIBUTION_TYPE = CPU
INFRASTRUCTURE_COST_TYPE = "Infrastructure"
SUPPLEMENTARY_COST_TYPE = "Supplementary"

METRIC_CHOICES = (
    (OCP_METRIC_CPU_CORE_USAGE_HOUR, OCP_METRIC_CPU_CORE_USAGE_HOUR),
    (OCP_METRIC_CPU_CORE_REQUEST_HOUR, OCP_METRIC_CPU_CORE_REQUEST_HOUR),
    (OCP_METRIC_CPU_CORE_EFFECTIVE_USAGE_HOUR, OCP_METRIC_CPU_CORE_EFFECTIVE_USAGE_HOUR),
    (OCP_METRIC_MEM_GB_USAGE_HOUR, OCP_METRIC_MEM_GB_USAGE_HOUR),
    (OCP_METRIC_MEM_GB_REQUEST_HOUR, OCP_METRIC_MEM_GB_REQUEST_HOUR),
    (OCP_METRIC_MEM_GB_EFFECTIVE_USAGE_HOUR, OCP_METRIC_MEM_GB_EFFECTIVE_USAGE_HOUR),
    (OCP_METRIC_STORAGE_GB_USAGE_MONTH, OCP_METRIC_STORAGE_GB_USAGE_MONTH),
    (OCP_METRIC_STORAGE_GB_REQUEST_MONTH, OCP_METRIC_STORAGE_GB_REQUEST_MONTH),
    (OCP_NODE_CORE_HOUR, OCP_NODE_CORE_HOUR),
    (OCP_NODE_MONTH, OCP_NODE_MONTH),
    (OCP_NODE_CORE_MONTH, OCP_NODE_CORE_MONTH),
    (OCP_CLUSTER_MONTH, OCP_CLUSTER_MONTH),
    (OCP_CLUSTER_CORE_HOUR, OCP_CLUSTER_CORE_HOUR),
    (OCP_CLUSTER_HOUR, OCP_CLUSTER_HOUR),
    (OCP_PVC_MONTH, OCP_PVC_MONTH),
    (OCP_VM_MONTH, OCP_VM_MONTH),
    (OCP_VM_HOUR, OCP_VM_HOUR),
)

COST_TYPE_CHOICES = (
    (INFRASTRUCTURE_COST_TYPE, INFRASTRUCTURE_COST_TYPE),
    (SUPPLEMENTARY_COST_TYPE, SUPPLEMENTARY_COST_TYPE),
)

COST_MODEL_USAGE_RATES = (
    OCP_METRIC_CPU_CORE_USAGE_HOUR,
    OCP_METRIC_CPU_CORE_REQUEST_HOUR,
    OCP_METRIC_CPU_CORE_EFFECTIVE_USAGE_HOUR,
    OCP_METRIC_MEM_GB_USAGE_HOUR,
    OCP_METRIC_MEM_GB_REQUEST_HOUR,
    OCP_METRIC_MEM_GB_EFFECTIVE_USAGE_HOUR,
    OCP_METRIC_STORAGE_GB_USAGE_MONTH,
    OCP_METRIC_STORAGE_GB_REQUEST_MONTH,
    OCP_NODE_CORE_HOUR,
    OCP_VM_HOUR,
    OCP_CLUSTER_CORE_HOUR,
    OCP_CLUSTER_HOUR,
)

COST_MODEL_NODE_RATES = {
    OCP_NODE_MONTH,
    OCP_NODE_CORE_MONTH,
    OCP_NODE_CORE_HOUR,
}

COST_MODEL_MONTHLY_RATES = (
    OCP_CLUSTER_MONTH,
    OCP_PVC_MONTH,
    OCP_VM_MONTH,
)

DISTRIBUTION_CHOICES = ((MEM, MEM), (CPU, CPU))

SOURCE_TYPE_MAP = {
    Provider.PROVIDER_OCP: "OpenShift Container Platform",
    Provider.PROVIDER_AWS: "Amazon Web Services",
    Provider.PROVIDER_AZURE: "Microsoft Azure",
    Provider.PROVIDER_GCP: "Google Cloud Platform",
    Provider.PROVIDER_OCI: "Oracle Cloud Infrastructure",
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
        "metric": "cpu_core_effective_usage_per_hour",
        "label_metric": "CPU",
        "label_measurement": "Effective-usage",
        "label_measurement_unit": "core-hours",
        "default_cost_type": "Supplementary",
    },
    {
        "source_type": "OCP",
        "metric": "memory_gb_usage_per_hour",
        "label_metric": "Memory",
        "label_measurement": "Usage",
        "label_measurement_unit": "GiB-hours",
        "default_cost_type": "Supplementary",
    },
    {
        "source_type": "OCP",
        "metric": "memory_gb_request_per_hour",
        "label_metric": "Memory",
        "label_measurement": "Request",
        "label_measurement_unit": "GiB-hours",
        "default_cost_type": "Supplementary",
    },
    {
        "source_type": "OCP",
        "metric": "memory_gb_effective_usage_per_hour",
        "label_metric": "Memory",
        "label_measurement": "Effective-usage",
        "label_measurement_unit": "GiB-hours",
        "default_cost_type": "Supplementary",
    },
    {
        "source_type": "OCP",
        "metric": "storage_gb_usage_per_month",
        "label_metric": "Storage",
        "label_measurement": "Usage",
        "label_measurement_unit": "GiB-month",
        "default_cost_type": "Supplementary",
    },
    {
        "source_type": "OCP",
        "metric": "storage_gb_request_per_month",
        "label_metric": "Storage",
        "label_measurement": "Request",
        "label_measurement_unit": "GiB-month",
        "default_cost_type": "Supplementary",
    },
    {
        "source_type": "OCP",
        "metric": "node_core_cost_per_hour",
        "label_metric": "Node",
        "label_measurement": "Count",
        "label_measurement_unit": "core-hour",
        "default_cost_type": "Infrastructure",
    },
    {
        "source_type": "OCP",
        "metric": "node_cost_per_month",
        "label_metric": "Node",
        "label_measurement": "Count",
        "label_measurement_unit": "node-month",
        "default_cost_type": "Infrastructure",
    },
    {
        "source_type": "OCP",
        "metric": "node_core_cost_per_month",
        "label_metric": "Node",
        "label_measurement": "Count",
        "label_measurement_unit": "core-month",
        "default_cost_type": "Infrastructure",
    },
    {
        "source_type": "OCP",
        "metric": "cluster_cost_per_month",
        "label_metric": "Cluster",
        "label_measurement": "Count",
        "label_measurement_unit": "cluster-month",
        "default_cost_type": "Infrastructure",
    },
    {
        "source_type": "OCP",
        "metric": "cluster_cost_per_hour",
        "label_metric": "Cluster",
        "label_measurement": "Count",
        "label_measurement_unit": "cluster-hour",
        "default_cost_type": "Infrastructure",
    },
    {
        "source_type": "OCP",
        "metric": "pvc_cost_per_month",
        "label_metric": "Persistent volume claims",
        "label_measurement": "Count",
        "label_measurement_unit": "pvc-month",
        "default_cost_type": "Infrastructure",
    },
    {
        "source_type": "OCP",
        "metric": "vm_cost_per_month",
        "label_metric": "Virtual Machine",
        "label_measurement": "Count",
        "label_measurement_unit": "vm-month",
        "default_cost_type": "Infrastructure",
    },
    {
        "source_type": "OCP",
        "metric": "vm_cost_per_hour",
        "label_metric": "Virtual Machine",
        "label_measurement": "Count",
        "label_measurement_unit": "vm-hour",
        "default_cost_type": "Infrastructure",
    },
    {
        "source_type": "OCP",
        "metric": "cluster_core_cost_per_hour",
        "label_metric": "Cluster",
        "label_measurement": "Count",
        "label_measurement_unit": "core-hour",
        "default_cost_type": "Infrastructure",
    },
]

PLATFORM_COST = "platform_cost"
PLATFORM_COST_DEFAULT = True
WORKER_UNALLOCATED = "worker_cost"
WORKER_UNALLOCATED_DEFAULT = True
NETWORK_UNATTRIBUTED = "network_unattributed"
NETWORK_UNATTRIBUTED_DEFAULT = False
STORAGE_UNATTRIBUTED = "storage_unattributed"
STORAGE_UNATTRIBUTED_DEFAULT = False
DISTRIBUTION_TYPE = "distribution_type"

DEFAULT_DISTRIBUTION_INFO = {
    DISTRIBUTION_TYPE: DEFAULT_DISTRIBUTION_TYPE,
    PLATFORM_COST: PLATFORM_COST_DEFAULT,
    WORKER_UNALLOCATED: WORKER_UNALLOCATED_DEFAULT,
    NETWORK_UNATTRIBUTED: NETWORK_UNATTRIBUTED_DEFAULT,
    STORAGE_UNATTRIBUTED: STORAGE_UNATTRIBUTED_DEFAULT,
}

# The usage metric map is used for the tag based rates
# to determine the usage metrics used in the sql file.
# it also help determine which labels to search for kv
# pair for pod_labels or storage
USAGE_METRIC_MAP = {
    OCP_METRIC_CPU_CORE_USAGE_HOUR: CPU,
    OCP_METRIC_CPU_CORE_REQUEST_HOUR: CPU,
    OCP_METRIC_CPU_CORE_EFFECTIVE_USAGE_HOUR: CPU,
    OCP_METRIC_MEM_GB_USAGE_HOUR: MEM,
    OCP_METRIC_MEM_GB_REQUEST_HOUR: MEM,
    OCP_METRIC_MEM_GB_EFFECTIVE_USAGE_HOUR: MEM,
    OCP_METRIC_STORAGE_GB_USAGE_MONTH: STORAGE,
    OCP_METRIC_STORAGE_GB_REQUEST_MONTH: STORAGE,
    OCP_CLUSTER_CORE_HOUR: CPU,
}
