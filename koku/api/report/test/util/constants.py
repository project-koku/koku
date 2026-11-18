#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from collections import UserDict


class SameLengthDict(UserDict):
    """
    SameLengthDict is used to build dictionaries where the length of the values
    much match for each key. All values must be an iterable.

    This class can be used when the indexes of the values correspond to the same index
    in the value for a diffent key.

    Example:
        SameLengthDict(
            {
                'key1': ('v1', 'v2', 'v3'),
                'key2': (
                    'corresponds to index 0 of key1 and key3',
                    'corresponds to index 1 of key1 and key2',
                    'corresponds to index 2 of key1 and key2',
                ),
                'key3': ('corresponds to index 0 of key1 and key2', etc...),
                etc...
            }
    """

    def __init__(self, val=None):
        self.length = 0
        if val is None:
            val = {}
        super().__init__(val)

    def __setitem__(self, item, value):
        if self.length == 0 and len(value) > 0:
            self.length = len(value)
        super().__setitem__(item, value)
        assert len(value) == self.length


AWS_REGIONS = ("us-east-1", "us-west-2", "eu-west-1", "ap-southeast-2", "af-south-1")
AWS_AVAILABILITY_ZONES = ("us-east-1a", "us-west-2a", "eu-west-1c", "ap-southeast-2b", "af-south-1a")
AWS_GEOG = SameLengthDict({"regions": AWS_REGIONS, "availability_zones": AWS_AVAILABILITY_ZONES})

# Product Code, Product Family, Instances, Units
AWS_PRODUCT_CODES = ("AmazonRDS", "AmazonRDS", "AmazonS3", "AmazonVPC", "AmazonEC2", "AmazonEC2", "AmazonEC2")
AWS_PRODUCT_FAMILIES = (
    "Database Instance",
    "Database Instance",
    "Storage Snapshot",
    "Cloud Connectivity",
    "Compute Instance",
    "Compute Instance",
    "Compute Instance",
)
AWS_INSTANCE_TYPES = ("db.t3.medium", "db.r5.2xlarge", None, None, "m5.large", "r4.large", "t2.micro")
AWS_RESOURCE_COUNTS = (1, 1, 0, 0, 1, 1, 1)
AWS_RESOURCE_IDS = (["i-11111111"], ["i-22222222"], [None], [None], ["i-33333333"], ["i-44444444"], ["i-55555555"])
AWS_UNITS = ("Hrs", "Hrs", "GB-Mo", "Hrs", "Hrs", "Hrs", "Hrs")
AWS_COST_CATEGORIES = (
    {"ninja": "turtle"},
    {"ninja": "naruto"},
    {"ninja": "scorpion"},
    {"env": "stage"},
    None,
    None,
    None,
)
AWS_VCPUS = (2, 4, 8, 32, 48, 96, 128)
AWS_MEMORY = ("16 GiB", "8 GiB", "32 GiB", "128 GiB", "512 GiB", "64 GiB", "1024 GiB")
AWS_OPERATING_SYSTEMS = (
    "Ubuntu",
    "Red Hat Enterprise Linux",
    "Fedora",
    "Debian",
    "CentOS",
    "Oracle Linux",
    "FreeBSD",
)

AWS_CONSTANTS = SameLengthDict(
    {
        "product_codes": AWS_PRODUCT_CODES,
        "product_families": AWS_PRODUCT_FAMILIES,
        "instance_types": AWS_INSTANCE_TYPES,
        "resource_counts": AWS_RESOURCE_COUNTS,
        "resource_ids": AWS_RESOURCE_IDS,
        "units": AWS_UNITS,
        "cost_category": AWS_COST_CATEGORIES,
        "operating_systems": AWS_OPERATING_SYSTEMS,
        "vcpus": AWS_VCPUS,
        "memory": AWS_MEMORY,
    }
)

AZURE_SERVICE_NAMES = (
    "SQL Database",
    "Virtual Machines",
    "Virtual Machines",
    "Virtual Network",
    "DNS",
    "Load Balancer",
    "General Block Blob",
    "Blob Storage",
    "Standard SSD Managed Disks",
)
AZURE_INSTANCE_TYPES = (None, "Standard_A0", "Standard_B2s") + (None,) * 6
AZURE_INSTANCE_IDS = ([None], ["id1"], ["id2"]) + ([None],) * 6
AZURE_INSTANCE_COUNTS = (0, 1, 1) + (0,) * 6
AZURE_UNITS_OF_MEASURE = ("Hrs",) * 3 + (None,) * 3 + ("GB-Mo",) * 3
AZURE_CONSTANTS = SameLengthDict(
    {
        "service_names": AZURE_SERVICE_NAMES,
        "instance_types": AZURE_INSTANCE_TYPES,
        "instance_ids": AZURE_INSTANCE_IDS,
        "instance_counts": AZURE_INSTANCE_COUNTS,
        "units_of_measure": AZURE_UNITS_OF_MEASURE,
    }
)


GCP_SERVICE_IDS = ("6F81-5844-456A", "1111-581D-38E5", "95FF-2EF5-5EA1", "12B3-1234-JK3C", "23C3-JS3K-SDL3")
GCP_SERVICE_ALIASES = ("Compute Engine", "SQL Database", "Cloud Storage", "Network", "VPC")
GCP_SKU_ALIASES = (
    "Instance Core running",
    "Storage PD Snapshot",
    "Standard Storage US Regional",
    "ManagedZone",
    "ManagedZone",
)
GCP_UNITS = ("hour", "gibibyte month", "gibibyte month", "seconds", "seconds")
GCP_CONSTANTS = SameLengthDict(
    {
        "service_ids": GCP_SERVICE_IDS,
        "service_aliases": GCP_SERVICE_ALIASES,
        "sku_aliases": GCP_SKU_ALIASES,
        "units": GCP_UNITS,
    }
)

OCP_PLATFORM_NAMESPACE = "openshift-default"
OCP_NAMESPACES = (OCP_PLATFORM_NAMESPACE, "koku", "koku-dev", "koku-stage", "koku-perf", "koku-prod")
OCP_STORAGE_CLASSES = ("bronze", "silver", "gold", "platinum", "adamantium", "vibranium")
OCP_POD_LABELS = (
    {"app": "mobile", "disabled": "Danilov", "vm_kubevirt_io_name": "test vm name"},
    {"app": "banking", "disabled": "Villabate"},
    {"app": "weather", "disabled": "Elbeuf", "vm_kubevirt_io_name": "test-vm-name"},
    {"app": "messaging", "disabled": "Pekanbaru"},
    {"app": "social", "disabled": "Castelfranco_Emilia", "vm_kubevirt_io_name": "TestVirtualMachineName"},
    {"app": "gaming", "disabled": "Teluk_Intan", "vm_kubevirt_io_name": "test_vm_name"},
)
OCP_PVC_LABELS = (
    {"app": "temperature", "disabled": "Danilov", "storageclass": "Ruby"},
    {"app": "length", "disabled": "Villabate", "storageclass": "Saphire"},
    {"app": "time", "disabled": "Elbeuf", "storageclass": "Pearl"},
    {"app": "luminosity", "disabled": "Pekanbaru", "storageclass": "Diamond"},
    {"app": "current", "disabled": "Castel_Emili", "storageclass": "Emerald"},
    {"app": "molarity", "disabled": "Teluk_Intan", "storageclass": "Garnet"},
)
OCP_GPU_LABELS = (
    {
        "gpu-model": "Tesla T4",
        "gpu-vendor": "nvidia",
        "gpu-memory-mib": "15360",
        "pod-name": "gpu_pod_0",
    },
    {
        "gpu-model": "A100",
        "gpu-vendor": "nvidia",
        "gpu-memory-mib": "40960",
        "pod-name": "gpu_pod_1",
    },
    {
        "gpu-model": "Tesla T4",
        "gpu-vendor": "nvidia",
        "gpu-memory-mib": "15360",
        "pod-name": "gpu_pod_2",
    },
    {
        "gpu-model": "H100",
        "gpu-vendor": "nvidia",
        "gpu-memory-mib": "81920",
        "pod-name": "gpu_pod_3",
    },
    {
        "gpu-model": "V100",
        "gpu-vendor": "nvidia",
        "gpu-memory-mib": "16384",
        "pod-name": "gpu_pod_4",
    },
    {
        "gpu-model": "A100",
        "gpu-vendor": "nvidia",
        "gpu-memory-mib": "40960",
        "pod-name": "gpu_pod_5",
    },
)
OCP_CONSTANTS = SameLengthDict(
    {
        "namespaces": OCP_NAMESPACES,
        "storage_classes": OCP_STORAGE_CLASSES,
        "pod_labels": OCP_POD_LABELS,
        "pvc_labels": OCP_PVC_LABELS,
        "gpu_labels": OCP_GPU_LABELS,
    }
)

# OCP-on-Prem Cost Model #
OCP_ON_PREM_COST_MODEL = {
    "name": "Cost Management OpenShift Cost Model",
    "description": "A cost model of on-premises OpenShift clusters.",
    "distribution": "cpu",
    "markup": {"value": 10, "unit": "percent"},
    "rates": [
        {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "tiered_rates": [{"unit": "USD", "value": 0.0070000000, "usage_start": None, "usage_end": None}],
            "cost_type": "Supplementary",
        },
        {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "tiered_rates": [{"unit": "USD", "value": 0.0140000000, "usage_start": None, "usage_end": None}],
            "cost_type": "Infrastructure",
        },
        {
            "metric": {"name": "cpu_core_request_per_hour"},
            "tiered_rates": [{"unit": "USD", "value": 0.2000000000, "usage_start": None, "usage_end": None}],
            "cost_type": "Supplementary",
        },
        {
            "metric": {"name": "cpu_core_request_per_hour"},
            "tiered_rates": [{"unit": "USD", "value": 0.4000000000, "usage_start": None, "usage_end": None}],
            "cost_type": "Infrastructure",
        },
        {
            "metric": {"name": "cpu_core_effective_usage_per_hour"},
            "tiered_rates": [{"unit": "USD", "value": 0.7000000000, "usage_start": None, "usage_end": None}],
            "cost_type": "Supplementary",
        },
        {
            "metric": {"name": "cpu_core_effective_usage_per_hour"},
            "tiered_rates": [{"unit": "USD", "value": 1.4000000000, "usage_start": None, "usage_end": None}],
            "cost_type": "Infrastructure",
        },
        {
            "metric": {"name": "memory_gb_usage_per_hour"},
            "tiered_rates": [{"unit": "USD", "value": 0.0090000000, "usage_start": None, "usage_end": None}],
            "cost_type": "Supplementary",
        },
        {
            "metric": {"name": "memory_gb_usage_per_hour"},
            "tiered_rates": [{"unit": "USD", "value": 0.0180000000, "usage_start": None, "usage_end": None}],
            "cost_type": "Infrastructure",
        },
        {
            "metric": {"name": "memory_gb_request_per_hour"},
            "tiered_rates": [{"unit": "USD", "value": 0.0500000000, "usage_start": None, "usage_end": None}],
            "cost_type": "Supplementary",
        },
        {
            "metric": {"name": "memory_gb_request_per_hour"},
            "tiered_rates": [{"unit": "USD", "value": 0.1000000000, "usage_start": None, "usage_end": None}],
            "cost_type": "Infrastructure",
        },
        {
            "metric": {"name": "memory_gb_effective_usage_per_hour"},
            "tiered_rates": [{"unit": "USD", "value": 0.500000000, "usage_start": None, "usage_end": None}],
            "cost_type": "Supplementary",
        },
        {
            "metric": {"name": "memory_gb_effective_usage_per_hour"},
            "tiered_rates": [{"unit": "USD", "value": 1.0000000000, "usage_start": None, "usage_end": None}],
            "cost_type": "Infrastructure",
        },
        {
            "metric": {"name": "storage_gb_usage_per_month"},
            "tiered_rates": [{"unit": "USD", "value": 0.01, "usage_start": None, "usage_end": None}],
            "cost_type": "Supplementary",
        },
        {
            "metric": {"name": "storage_gb_usage_per_month"},
            "tiered_rates": [{"unit": "USD", "value": 0.02, "usage_start": None, "usage_end": None}],
            "cost_type": "Infrastructure",
        },
        {
            "metric": {"name": "storage_gb_request_per_month"},
            "tiered_rates": [{"unit": "USD", "value": 0.01, "usage_start": None, "usage_end": None}],
            "cost_type": "Supplementary",
        },
        {
            "metric": {"name": "storage_gb_request_per_month"},
            "tiered_rates": [{"unit": "USD", "value": 0.02, "usage_start": None, "usage_end": None}],
            "cost_type": "Infrastructure",
        },
        {
            "metric": {"name": "node_cost_per_month"},
            "tiered_rates": [{"unit": "USD", "value": 1000.0, "usage_start": None, "usage_end": None}],
            "cost_type": "Infrastructure",
        },
        {
            "metric": {"name": "node_cost_per_month"},
            "tiered_rates": [{"unit": "USD", "value": 100.0, "usage_start": None, "usage_end": None}],
            "cost_type": "Supplementary",
        },
        {
            "metric": {"name": "cluster_cost_per_month"},
            "tiered_rates": [{"unit": "USD", "value": 10000.0, "usage_start": None, "usage_end": None}],
            "cost_type": "Infrastructure",
        },
        {
            "metric": {"name": "cluster_cost_per_month"},
            "tiered_rates": [{"unit": "USD", "value": 1000.0, "usage_start": None, "usage_end": None}],
            "cost_type": "Supplementary",
        },
        {
            "metric": {"name": "pvc_cost_per_month"},
            "tiered_rates": [{"unit": "USD", "value": 10.0, "usage_start": None, "usage_end": None}],
            "cost_type": "Infrastructure",
        },
        {
            "metric": {"name": "pvc_cost_per_month"},
            "tiered_rates": [{"unit": "USD", "value": 20.0, "usage_start": None, "usage_end": None}],
            "cost_type": "Supplementary",
        },
    ],
}
