#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from collections import UserDict


class SameLengthDict(UserDict):
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

AWS_CONSTANTS = SameLengthDict(
    {
        "product_codes": AWS_PRODUCT_CODES,
        "product_families": AWS_PRODUCT_FAMILIES,
        "instance_types": AWS_INSTANCE_TYPES,
        "resource_counts": AWS_RESOURCE_COUNTS,
        "resource_ids": AWS_RESOURCE_IDS,
        "units": AWS_UNITS,
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

OCP_NAMESPACES = ("default", "koku", "koku-dev", "koku-stage", "koku-perf", "koku-prod")
OCP_STORAGE_CLASSES = ("bronze", "silver", "gold", "platinum", "adamantium", "vibranium")
OCP_POD_LABELS = (
    {"app": "mobile", "disabled": "Danilov"},
    {"app": "banking", "disabled": "Villabate"},
    {"app": "weather", "disabled": "Elbeuf"},
    {"app": "messaging", "disabled": "Pekanbaru"},
    {"app": "social", "disabled": "Castelfranco_Emilia"},
    {"app": "gaming", "disabled": "Teluk_Intan"},
)
OCP_PVC_LABELS = (
    {"app": "mobile", "disabled": "Danilov", "storageclass": "Ruby"},
    {"app": "banking", "disabled": "Villabate", "storageclass": "Saphire"},
    {"app": "weather", "disabled": "Elbeuf", "storageclass": "Pearl"},
    {"app": "messaging", "disabled": "Pekanbaru", "storageclass": "Diamond"},
    {"app": "social", "disabled": "Castel_Emili", "storageclass": "Emerald"},
    {"app": "gaming", "disabled": "Teluk_Intan", "storageclass": "Garnet"},
)
OCP_CONSTANTS = SameLengthDict(
    {
        "namespaces": OCP_NAMESPACES,
        "storage_classes": OCP_STORAGE_CLASSES,
        "pod_labels": OCP_POD_LABELS,
        "pvc_labels": OCP_PVC_LABELS,
    }
)

# OCP-on-Prem Cost Model #
OCP_ON_PREM_COST_MODEL = {
    "name": "Cost Management OpenShift Cost Model",
    "description": "A cost model of on-premises OpenShift clusters.",
    "distribution": "cpu",
    "rates": [
        {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "tiered_rates": [{"unit": "USD", "value": 0.0070000000, "usage_start": None, "usage_end": None}],
            "cost_type": "Supplementary",
        },
        {
            "metric": {"name": "cpu_core_request_per_hour"},
            "tiered_rates": [{"unit": "USD", "value": 0.2000000000, "usage_start": None, "usage_end": None}],
            "cost_type": "Supplementary",
        },
        {
            "metric": {"name": "memory_gb_usage_per_hour"},
            "tiered_rates": [{"unit": "USD", "value": 0.0090000000, "usage_start": None, "usage_end": None}],
            "cost_type": "Supplementary",
        },
        {
            "metric": {"name": "memory_gb_request_per_hour"},
            "tiered_rates": [{"unit": "USD", "value": 0.0500000000, "usage_start": None, "usage_end": None}],
            "cost_type": "Supplementary",
        },
        {
            "metric": {"name": "storage_gb_usage_per_month"},
            "tiered_rates": [{"unit": "USD", "value": 0.01, "usage_start": None, "usage_end": None}],
            "cost_type": "Supplementary",
        },
        {
            "metric": {"name": "storage_gb_request_per_month"},
            "tiered_rates": [{"unit": "USD", "value": 0.01, "usage_start": None, "usage_end": None}],
            "cost_type": "Supplementary",
        },
        {
            "metric": {"name": "node_cost_per_month"},
            "tiered_rates": [{"unit": "USD", "value": 1000.0, "usage_start": None, "usage_end": None}],
            "cost_type": "Infrastructure",
        },
        {
            "metric": {"name": "cluster_cost_per_month"},
            "tiered_rates": [{"unit": "USD", "value": 10000.0, "usage_start": None, "usage_end": None}],
            "cost_type": "Infrastructure",
        },
        {
            "metric": {"name": "pvc_cost_per_month"},
            "tiered_rates": [{"unit": "USD", "value": 10.0, "usage_start": None, "usage_end": None}],
            "cost_type": "Infrastructure",
        },
        {
            "metric": {"name": "node_cost_per_month"},
            "tiered_rates": [{"unit": "USD", "value": 100.0, "usage_start": None, "usage_end": None}],
            "cost_type": "Supplementary",
        },
        {
            "metric": {"name": "cluster_cost_per_month"},
            "tiered_rates": [{"unit": "USD", "value": 1000.0, "usage_start": None, "usage_end": None}],
            "cost_type": "Supplementary",
        },
        {
            "metric": {"name": "pvc_cost_per_month"},
            "tiered_rates": [{"unit": "USD", "value": 20.0, "usage_start": None, "usage_end": None}],
            "cost_type": "Supplementary",
        },
    ],
}
