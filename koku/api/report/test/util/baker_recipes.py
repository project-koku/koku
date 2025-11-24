#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from itertools import cycle

from faker import Faker
from model_bakery.recipe import foreign_key
from model_bakery.recipe import Recipe

from api.report.test.util.constants import AWS_CONSTANTS
from api.report.test.util.constants import AWS_GEOG
from api.report.test.util.constants import AZURE_CONSTANTS
from api.report.test.util.constants import GCP_CONSTANTS
from api.report.test.util.constants import OCP_CONSTANTS

fake = Faker()


def decimal_yielder():
    while True:
        yield fake.pydecimal(left_digits=13, right_digits=8, positive=True)


billing_source = Recipe("ProviderBillingSource", data_source={})
provider = Recipe("Provider", billing_source=foreign_key(billing_source))

aws_daily_summary = Recipe(
    "AWSCostEntryLineItemDailySummary",
    product_code=cycle(AWS_CONSTANTS["product_codes"]),
    product_family=cycle(AWS_CONSTANTS["product_families"]),
    instance_type=cycle(AWS_CONSTANTS["instance_types"]),
    resource_count=cycle(AWS_CONSTANTS["resource_counts"]),
    resource_ids=cycle(AWS_CONSTANTS["resource_ids"]),
    unit=cycle(AWS_CONSTANTS["units"]),
    region=cycle(AWS_GEOG["regions"]),
    availability_zone=cycle(AWS_GEOG["availability_zones"]),
    cost_category=cycle(AWS_CONSTANTS["cost_category"]),
    _fill_optional=True,
    _quantity=10,
)

aws_ec2_compute_summary = Recipe(
    "AWSCostEntryLineItemSummaryByEC2ComputeP",
    resource_id=cycle(f"i-000000{i}" for i in range(AWS_CONSTANTS.length - 1)),
    instance_type=cycle(AWS_CONSTANTS["instance_types"]),
    operating_system=cycle(AWS_CONSTANTS["operating_systems"]),
    unit=cycle(AWS_CONSTANTS["units"]),
    region=cycle(AWS_GEOG["regions"]),
    memory=cycle(AWS_CONSTANTS["memory"]),
    vcpu=cycle(AWS_CONSTANTS["vcpus"]),
    cost_category=cycle(AWS_CONSTANTS["cost_category"]),
    _fill_optional=True,
    _quantity=AWS_CONSTANTS.length,
)

azure_daily_summary = Recipe(
    "AzureCostEntryLineItemDailySummary",
    service_name=cycle(AZURE_CONSTANTS["service_names"]),
    instance_type=cycle(AZURE_CONSTANTS["instance_types"]),
    instance_ids=cycle(AZURE_CONSTANTS["instance_ids"]),
    instance_count=cycle(AZURE_CONSTANTS["instance_counts"]),
    unit_of_measure=cycle(AZURE_CONSTANTS["units_of_measure"]),
    resource_location="US East",
    _fill_optional=True,
    _quantity=AZURE_CONSTANTS.length,
)

gcp_daily_summary = Recipe(
    "GCPCostEntryLineItemDailySummary",
    service_id=cycle(GCP_CONSTANTS["service_ids"]),
    service_alias=cycle(GCP_CONSTANTS["service_aliases"]),
    sku_id=cycle(GCP_CONSTANTS["service_ids"]),
    sku_alias=cycle(GCP_CONSTANTS["sku_aliases"]),
    unit=cycle(GCP_CONSTANTS["units"]),
    usage_amount=cycle(decimal_yielder()),
    unblended_cost=cycle(decimal_yielder()),
    markup_cost=cycle(decimal_yielder()),
    credit_amount=cycle(decimal_yielder()),
    _fill_optional=True,
    _quantity=GCP_CONSTANTS.length,
)

ocp_usage_pod = Recipe(  # Pod data_source
    "OCPUsageLineItemDailySummary",
    data_source="Pod",
    node=cycle(f"node_{i}" for i in range(OCP_CONSTANTS.length - 1)),
    resource_id=cycle(f"i-000000{i}" for i in range(OCP_CONSTANTS.length - 1)),
    namespace=cycle(OCP_CONSTANTS["namespaces"]),
    pod_limit_cpu_core_hours=cycle(decimal_yielder()),
    pod_usage_cpu_core_hours=cycle(decimal_yielder()),
    pod_request_cpu_core_hours=cycle(decimal_yielder()),
    pod_effective_usage_cpu_core_hours=cycle(decimal_yielder()),
    pod_limit_memory_gigabyte_hours=cycle(decimal_yielder()),
    pod_usage_memory_gigabyte_hours=cycle(decimal_yielder()),
    pod_request_memory_gigabyte_hours=cycle(decimal_yielder()),
    pod_effective_usage_memory_gigabyte_hours=cycle(decimal_yielder()),
    node_capacity_cpu_cores=cycle(decimal_yielder()),
    node_capacity_cpu_core_hours=cycle(decimal_yielder()),
    node_capacity_memory_gigabytes=cycle(decimal_yielder()),
    node_capacity_memory_gigabyte_hours=cycle(decimal_yielder()),
    cluster_capacity_cpu_core_hours=cycle(decimal_yielder()),
    cluster_capacity_memory_gigabyte_hours=cycle(decimal_yielder()),
    pod_labels=cycle(OCP_CONSTANTS["pod_labels"]),
    all_labels=cycle(OCP_CONSTANTS["pod_labels"]),
    _fill_optional=False,
    _quantity=OCP_CONSTANTS.length,
)

ocp_usage_storage = Recipe(  # Storage data_source
    "OCPUsageLineItemDailySummary",
    data_source="Storage",
    node=cycle(f"node_{i}" for i in range(OCP_CONSTANTS.length - 1)),
    resource_id=cycle(f"i-000000{i}" for i in range(OCP_CONSTANTS.length - 1)),
    namespace=cycle(OCP_CONSTANTS["namespaces"]),
    persistentvolumeclaim=cycle(f"pvc_{i}" for i in range(OCP_CONSTANTS.length - 1)),
    persistentvolume=cycle(f"pv_{i}" for i in range(OCP_CONSTANTS.length - 1)),
    storageclass=cycle(OCP_CONSTANTS["storage_classes"]),
    persistentvolumeclaim_capacity_gigabyte=cycle(decimal_yielder()),
    persistentvolumeclaim_capacity_gigabyte_months=cycle(decimal_yielder()),
    volume_request_storage_gigabyte_months=cycle(decimal_yielder()),
    persistentvolumeclaim_usage_gigabyte_months=cycle(decimal_yielder()),
    node_capacity_cpu_cores=cycle(decimal_yielder()),
    node_capacity_cpu_core_hours=cycle(decimal_yielder()),
    node_capacity_memory_gigabytes=cycle(decimal_yielder()),
    node_capacity_memory_gigabyte_hours=cycle(decimal_yielder()),
    cluster_capacity_cpu_core_hours=cycle(decimal_yielder()),
    cluster_capacity_memory_gigabyte_hours=cycle(decimal_yielder()),
    volume_labels=cycle(OCP_CONSTANTS["pvc_labels"]),
    all_labels=cycle(OCP_CONSTANTS["pvc_labels"]),
    _fill_optional=False,
    _quantity=OCP_CONSTANTS.length,
)

ocp_usage_gpu = Recipe(  # GPU data_source
    "OCPUsageLineItemDailySummary",
    data_source="GPU",
    node=cycle(f"gpu_node_{i}" for i in range(OCP_CONSTANTS.length - 1)),
    resource_id=cycle(f"GPU-{i:08d}" for i in range(OCP_CONSTANTS.length - 1)),
    namespace=cycle(OCP_CONSTANTS["namespaces"]),
    all_labels=cycle(OCP_CONSTANTS["gpu_labels"]),
    raw_currency="USD",
    cost_model_rate_type="Tag",
    node_capacity_cpu_cores=cycle(decimal_yielder()),
    node_capacity_cpu_core_hours=cycle(decimal_yielder()),
    node_capacity_memory_gigabytes=cycle(decimal_yielder()),
    node_capacity_memory_gigabyte_hours=cycle(decimal_yielder()),
    cluster_capacity_cpu_core_hours=cycle(decimal_yielder()),
    cluster_capacity_memory_gigabyte_hours=cycle(decimal_yielder()),
    _fill_optional=False,
    _quantity=OCP_CONSTANTS.length,
)

ocp_usage_network_in = Recipe(  # Inbound network flow
    "OCPUsageLineItemDailySummary",
    data_source="Pod",
    node=cycle(f"node_{i}" for i in range(OCP_CONSTANTS.length - 1)),
    resource_id=cycle(f"i-000000{i}" for i in range(OCP_CONSTANTS.length - 1)),
    namespace="Network unattributed",
    infrastructure_data_in_gigabytes=cycle(decimal_yielder()),
    infrastructure_data_out_gigabytes=None,
    pod_usage_cpu_core_hours=0,
    pod_request_cpu_core_hours=0,
    pod_limit_cpu_core_hours=0,
    pod_usage_memory_gigabyte_hours=0,
    pod_request_memory_gigabyte_hours=0,
    pod_limit_memory_gigabyte_hours=0,
    node_capacity_cpu_cores=0,
    node_capacity_cpu_core_hours=0,
    node_capacity_memory_gigabytes=0,
    node_capacity_memory_gigabyte_hours=0,
    cluster_capacity_cpu_core_hours=0,
    cluster_capacity_memory_gigabyte_hours=0,
    persistentvolumeclaim_capacity_gigabyte=0,
    persistentvolumeclaim_capacity_gigabyte_months=0,
    volume_request_storage_gigabyte_months=0,
    persistentvolumeclaim_usage_gigabyte_months=0,
    _fill_optional=False,
    _quantity=OCP_CONSTANTS.length,
)

ocp_usage_network_out = Recipe(  # Outbound network flow
    "OCPUsageLineItemDailySummary",
    data_source="Pod",
    node=cycle(f"node_{i}" for i in range(OCP_CONSTANTS.length - 1)),
    resource_id=cycle(f"i-000000{i}" for i in range(OCP_CONSTANTS.length - 1)),
    namespace="Network unattributed",
    infrastructure_data_in_gigabytes=None,
    infrastructure_data_out_gigabytes=cycle(decimal_yielder()),
    pod_usage_cpu_core_hours=0,
    pod_request_cpu_core_hours=0,
    pod_limit_cpu_core_hours=0,
    pod_usage_memory_gigabyte_hours=0,
    pod_request_memory_gigabyte_hours=0,
    pod_limit_memory_gigabyte_hours=0,
    node_capacity_cpu_cores=0,
    node_capacity_cpu_core_hours=0,
    node_capacity_memory_gigabytes=0,
    node_capacity_memory_gigabyte_hours=0,
    cluster_capacity_cpu_core_hours=0,
    cluster_capacity_memory_gigabyte_hours=0,
    persistentvolumeclaim_capacity_gigabyte=0,
    persistentvolumeclaim_capacity_gigabyte_months=0,
    volume_request_storage_gigabyte_months=0,
    persistentvolumeclaim_usage_gigabyte_months=0,
    _fill_optional=False,
    _quantity=OCP_CONSTANTS.length,
)

ocp_on_aws_daily_summary = Recipe(
    "OCPAWSCostLineItemDailySummaryP",
    node=cycle(f"aws_node_{i}" for i in range(AWS_CONSTANTS.length - 1)),
    resource_id=cycle(f"i-0000{i}{i}{i}" for i in range(AWS_CONSTANTS.length - 1)),
    namespace=cycle([ns] for ns in OCP_CONSTANTS["namespaces"]),
    instance_type=cycle(AWS_CONSTANTS["instance_types"]),
    product_code=cycle(AWS_CONSTANTS["product_codes"]),
    product_family=cycle(AWS_CONSTANTS["product_families"]),
    unit=cycle(AWS_CONSTANTS["units"]),
    unblended_cost=cycle(decimal_yielder()),
    markup_cost=cycle(decimal_yielder()),
    blended_cost=cycle(decimal_yielder()),
    markup_cost_blended=cycle(decimal_yielder()),
    savingsplan_effective_cost=cycle(decimal_yielder()),
    markup_cost_savingsplan=cycle(decimal_yielder()),
    calculated_amortized_cost=cycle(decimal_yielder()),
    markup_cost_amortized=cycle(decimal_yielder()),
    _fill_optional=True,
    _quantity=min(AWS_CONSTANTS.length, 9),
)

ocp_on_aws_project_daily_summary_pod = Recipe(  # Pod data_source
    "OCPAWSCostLineItemProjectDailySummaryP",
    data_source="Pod",
    node=cycle(f"aws_node_{i}" for i in range(AWS_CONSTANTS.length - 1)),
    resource_id=cycle(f"i-0000{i}{i}{i}" for i in range(AWS_CONSTANTS.length - 1)),
    namespace=cycle(OCP_CONSTANTS["namespaces"]),
    pod_labels=cycle(OCP_CONSTANTS["pod_labels"]),
    persistentvolumeclaim=None,
    persistentvolume=None,
    storageclass=None,
    instance_type=cycle(AWS_CONSTANTS["instance_types"]),
    product_code=cycle(AWS_CONSTANTS["product_codes"]),
    product_family=cycle(AWS_CONSTANTS["product_families"]),
    unit=cycle(AWS_CONSTANTS["units"]),
    unblended_cost=cycle(decimal_yielder()),
    markup_cost=cycle(decimal_yielder()),
    blended_cost=cycle(decimal_yielder()),
    markup_cost_blended=cycle(decimal_yielder()),
    savingsplan_effective_cost=cycle(decimal_yielder()),
    markup_cost_savingsplan=cycle(decimal_yielder()),
    calculated_amortized_cost=cycle(decimal_yielder()),
    markup_cost_amortized=cycle(decimal_yielder()),
    _fill_optional=True,
    _quantity=min(AWS_CONSTANTS.length, 9),
)

ocp_on_aws_project_daily_summary_storage = Recipe(  # Storage data_source
    "OCPAWSCostLineItemProjectDailySummaryP",
    data_source="Storage",
    node=cycle(f"aws_node_{i}" for i in range(AWS_CONSTANTS.length - 1)),
    resource_id=cycle(f"i-0000{i}{i}{i}" for i in range(AWS_CONSTANTS.length - 1)),
    namespace=cycle(OCP_CONSTANTS["namespaces"]),
    persistentvolumeclaim=cycle(f"pvc_aws_{i}" for i in range(AWS_CONSTANTS.length - 1)),
    persistentvolume=cycle(f"pv_aws_{i}" for i in range(AWS_CONSTANTS.length - 1)),
    storageclass=cycle(OCP_CONSTANTS["storage_classes"]),
    instance_type=cycle(AWS_CONSTANTS["instance_types"]),
    product_code=cycle(AWS_CONSTANTS["product_codes"]),
    product_family=cycle(AWS_CONSTANTS["product_families"]),
    aws_cost_category=cycle(AWS_CONSTANTS["cost_category"]),
    unit=cycle(AWS_CONSTANTS["units"]),
    unblended_cost=cycle(decimal_yielder()),
    markup_cost=cycle(decimal_yielder()),
    blended_cost=cycle(decimal_yielder()),
    markup_cost_blended=cycle(decimal_yielder()),
    savingsplan_effective_cost=cycle(decimal_yielder()),
    markup_cost_savingsplan=cycle(decimal_yielder()),
    calculated_amortized_cost=cycle(decimal_yielder()),
    markup_cost_amortized=cycle(decimal_yielder()),
    _fill_optional=True,
    _quantity=min(AWS_CONSTANTS.length, 9),
)

ocp_on_azure_daily_summary = Recipe(
    "OCPAzureCostLineItemDailySummaryP",
    node=cycle(f"azure_node_{i}" for i in range(AZURE_CONSTANTS.length - 1)),
    resource_id=cycle(f"i-000{i}{i}{i}{i}" for i in range(AZURE_CONSTANTS.length - 1)),
    namespace=cycle([ns] for ns in OCP_CONSTANTS["namespaces"]),
    service_name=cycle(AZURE_CONSTANTS["service_names"]),
    instance_type=cycle(AZURE_CONSTANTS["instance_types"]),
    unit_of_measure=cycle(AZURE_CONSTANTS["units_of_measure"]),
    resource_location="US East",
    _fill_optional=True,
    _quantity=min(AZURE_CONSTANTS.length, 9),
)

ocp_on_azure_project_daily_summary_pod = Recipe(  # Pod data_source
    "OCPAzureCostLineItemProjectDailySummaryP",
    data_source="Pod",
    node=cycle(f"azure_node_{i}" for i in range(AZURE_CONSTANTS.length - 1)),
    resource_id=cycle(f"i-000{i}{i}{i}{i}" for i in range(AZURE_CONSTANTS.length - 1)),
    namespace=cycle(OCP_CONSTANTS["namespaces"]),
    pod_labels=cycle(OCP_CONSTANTS["pod_labels"]),
    persistentvolumeclaim=None,
    persistentvolume=None,
    storageclass=None,
    service_name=cycle(AZURE_CONSTANTS["service_names"]),
    instance_type=cycle(AZURE_CONSTANTS["instance_types"]),
    unit_of_measure=cycle(AZURE_CONSTANTS["units_of_measure"]),
    _fill_optional=True,
    _quantity=min(AZURE_CONSTANTS.length, 9),
)

ocp_on_azure_project_daily_summary_storage = Recipe(  # Storage data_source
    "OCPAzureCostLineItemProjectDailySummaryP",
    data_source="Storage",
    node=cycle(f"azure_node_{i}" for i in range(AZURE_CONSTANTS.length - 1)),
    resource_id=cycle(f"i-000{i}{i}{i}{i}" for i in range(AZURE_CONSTANTS.length - 1)),
    namespace=cycle(OCP_CONSTANTS["namespaces"]),
    persistentvolumeclaim=cycle(f"pvc_azure_{i}" for i in range(AZURE_CONSTANTS.length - 1)),
    persistentvolume=cycle(f"pv_azure{i}" for i in range(AZURE_CONSTANTS.length - 1)),
    storageclass=cycle(OCP_CONSTANTS["storage_classes"]),
    service_name=cycle(AZURE_CONSTANTS["service_names"]),
    instance_type=cycle(AZURE_CONSTANTS["instance_types"]),
    unit_of_measure=cycle(AZURE_CONSTANTS["units_of_measure"]),
    _fill_optional=True,
    _quantity=min(AZURE_CONSTANTS.length, 9),
)

ocp_on_gcp_daily_summary = Recipe(
    "OCPGCPCostLineItemDailySummaryP",
    namespace=cycle([ns] for ns in OCP_CONSTANTS["namespaces"]),
    node=cycle(f"gcp_node_{i}" for i in range(GCP_CONSTANTS.length - 1)),
    resource_id=cycle(f"i-{i}{i}{i}{i}{i}{i}{i}" for i in range(GCP_CONSTANTS.length - 1)),
    project_id=cycle(OCP_CONSTANTS["namespaces"]),
    project_name=cycle(OCP_CONSTANTS["storage_classes"]),  # maybe this can change, idk
    service_id=cycle(GCP_CONSTANTS["service_ids"]),
    service_alias=cycle(GCP_CONSTANTS["service_aliases"]),
    unit=cycle(GCP_CONSTANTS["units"]),
    _fill_optional=True,
    _quantity=min(GCP_CONSTANTS.length, 9),
)

ocp_on_gcp_project_daily_summary_pod = Recipe(  # Pod data_source
    "OCPGCPCostLineItemProjectDailySummaryP",
    data_source="Pod",
    namespace=cycle(OCP_CONSTANTS["namespaces"]),
    node=cycle(f"gcp_node_{i}" for i in range(GCP_CONSTANTS.length - 1)),
    resource_id=cycle(f"i-{i}{i}{i}{i}{i}{i}{i}" for i in range(GCP_CONSTANTS.length - 1)),
    project_id=cycle(OCP_CONSTANTS["namespaces"]),
    project_name=cycle(OCP_CONSTANTS["storage_classes"]),  # maybe this can change, idk
    pod_labels=cycle(OCP_CONSTANTS["pod_labels"]),
    persistentvolumeclaim=None,
    persistentvolume=None,
    storageclass=None,
    service_id=cycle(GCP_CONSTANTS["service_ids"]),
    service_alias=cycle(GCP_CONSTANTS["service_aliases"]),
    sku_id=cycle(GCP_CONSTANTS["service_ids"]),
    sku_alias=cycle(GCP_CONSTANTS["sku_aliases"]),
    unit=cycle(GCP_CONSTANTS["units"]),
    _fill_optional=True,
    _quantity=min(GCP_CONSTANTS.length, 9),
)

ocp_on_gcp_project_daily_summary_storage = Recipe(  # Storage data_source
    "OCPGCPCostLineItemProjectDailySummaryP",
    data_source="Storage",
    namespace=cycle(OCP_CONSTANTS["namespaces"]),
    node=cycle(f"gcp_node_{i}" for i in range(GCP_CONSTANTS.length - 1)),
    resource_id=cycle(f"i-{i}{i}{i}{i}{i}{i}{i}" for i in range(GCP_CONSTANTS.length - 1)),
    project_id=cycle(OCP_CONSTANTS["namespaces"]),
    project_name=cycle(OCP_CONSTANTS["storage_classes"]),  # maybe this can change, idk
    persistentvolumeclaim=cycle(f"pvc_gcp_{i}" for i in range(GCP_CONSTANTS.length - 1)),
    persistentvolume=cycle(f"pv_gcp{i}" for i in range(GCP_CONSTANTS.length - 1)),
    storageclass=cycle(OCP_CONSTANTS["storage_classes"]),
    service_id=cycle(GCP_CONSTANTS["service_ids"]),
    service_alias=cycle(GCP_CONSTANTS["service_aliases"]),
    sku_id=cycle(GCP_CONSTANTS["service_ids"]),
    sku_alias=cycle(GCP_CONSTANTS["sku_aliases"]),
    unit=cycle(GCP_CONSTANTS["units"]),
    _fill_optional=True,
    _quantity=min(GCP_CONSTANTS.length, 9),
)
