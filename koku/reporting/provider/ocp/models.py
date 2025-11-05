#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for OCP cost entry tables."""
from decimal import Decimal
from uuid import uuid4

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import JSONField

TRINO_LINE_ITEM_TABLE_MAP = {
    "pod_usage": "openshift_pod_usage_line_items",
    "storage_usage": "openshift_storage_usage_line_items",
    "node_labels": "openshift_node_labels_line_items",
    "namespace_labels": "openshift_namespace_labels_line_items",
    "vm_usage": "openshift_vm_usage_line_items",
    "gpu_usage": "openshift_gpu_usage_line_items",
}

TRINO_LINE_ITEM_TABLE_DAILY_MAP = {
    "pod_usage": "openshift_pod_usage_line_items_daily",
    "storage_usage": "openshift_storage_usage_line_items_daily",
    "node_labels": "openshift_node_labels_line_items_daily",
    "namespace_labels": "openshift_namespace_labels_line_items_daily",
    "vm_usage": "openshift_vm_usage_line_items_daily",
    "gpu_usage": "openshift_gpu_usage_line_items_daily",
}

VIEWS = (
    "reporting_ocp_cost_summary",
    "reporting_ocp_cost_summary_by_node",
    "reporting_ocp_cost_summary_by_project",
    "reporting_ocp_pod_summary",
    "reporting_ocp_pod_summary_by_project",
    "reporting_ocp_volume_summary",
    "reporting_ocp_volume_summary_by_project",
)

UI_SUMMARY_TABLES_MARKUP_SUBSET = (
    "reporting_ocp_cost_summary_p",
    "reporting_ocp_cost_summary_by_node_p",
    "reporting_ocp_cost_summary_by_project_p",
)

UI_SUMMARY_TABLES = (
    *UI_SUMMARY_TABLES_MARKUP_SUBSET,
    "reporting_ocp_pod_summary_p",
    "reporting_ocp_pod_summary_by_node_p",
    "reporting_ocp_pod_summary_by_project_p",
    "reporting_ocp_volume_summary_p",
    "reporting_ocp_volume_summary_by_project_p",
    "reporting_ocp_network_summary_p",
    "reporting_ocp_network_summary_by_node_p",
    "reporting_ocp_network_summary_by_project_p",
)

# Note the reporting_ocp_vm_summary_p is populated separately.
VM_UI_SUMMARY_TABLE = "reporting_ocp_vm_summary_p"


class OCPUsageReportPeriod(models.Model):
    """The report period information for a Operator Metering report.

    The reporting period (1 month) will cover many reports.

    """

    class Meta:
        """Meta for OCPUsageReportPeriod."""

        unique_together = ("cluster_id", "report_period_start", "provider")

    cluster_id = models.CharField(max_length=50, null=False)
    cluster_alias = models.CharField(max_length=256, null=True)
    report_period_start = models.DateTimeField(null=False)
    report_period_end = models.DateTimeField(null=False)
    summary_data_creation_datetime = models.DateTimeField(null=True)
    summary_data_updated_datetime = models.DateTimeField(null=True)
    ocp_on_cloud_updated_datetime = models.DateTimeField(null=True)
    derived_cost_datetime = models.DateTimeField(null=True)
    provider = models.ForeignKey("reporting.TenantAPIProvider", on_delete=models.CASCADE)


class OCPUsageLineItemDailySummary(models.Model):
    """A daily aggregation of line items from pod and volume sources.

    This table is aggregated by OCP resource.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    # Tag cost is actually a usage-based daily cost. We are overloading this field for
    # tag usage rates.
    MONTHLY_COST_TYPES = (
        ("Node", "Node"),
        ("Node_Core_Month", "Node_Core_Month"),
        ("Cluster", "Cluster"),
        ("PVC", "PVC"),
        ("Tag", "Tag"),
        ("OCP_VM", "OCP_VM"),
        ("OCP_VM_CORE", "OCP_VM_CORE"),
    )
    MONTHLY_COST_RATE_MAP = {
        "Node": "node_cost_per_month",
        "Node_Core_Month": "node_core_cost_per_month",
        "Cluster": "cluster_cost_per_month",
        "PVC": "pvc_cost_per_month",
        "OCP_VM": "vm_cost_per_month",
        "OCP_VM_CORE": "vm_core_cost_per_month",
    }
    DISTRIBUTION_COST_TYPES = ["cpu", "memory", "pvc"]

    class Meta:
        """Meta for OCPUsageLineItemDailySummary."""

        db_table = "reporting_ocpusagelineitem_daily_summary"

        indexes = [
            models.Index(fields=["usage_start"], name="summary_ocp_usage_idx"),
            models.Index(fields=["namespace"], name="summary_namespace_idx", opclasses=["varchar_pattern_ops"]),
            models.Index(fields=["node"], name="summary_node_idx", opclasses=["varchar_pattern_ops"]),
            models.Index(fields=["data_source"], name="summary_data_source_idx"),
            models.Index(fields=["monthly_cost_type"], name="monthly_cost_type_idx"),
            models.Index(fields=["cost_model_rate_type"], name="cost_model_rate_type_idx"),
            GinIndex(fields=["all_labels"], name="all_labels_idx"),
            GinIndex(fields=["pod_labels"], name="pod_labels_idx"),
            GinIndex(fields=["volume_labels"], name="volume_labels_idx"),
        ]

    uuid = models.UUIDField(primary_key=True)
    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE, null=True)
    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE, null=True)
    cluster_id = models.CharField(max_length=50, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    # Whether the data comes from a pod or volume report
    data_source = models.CharField(max_length=64, null=True)
    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=True)
    node = models.CharField(max_length=253, null=True)
    # Another node identifier used to tie the node to an EC2 instance
    resource_id = models.CharField(max_length=253, null=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    pod_labels = JSONField(null=True)
    pod_usage_cpu_core_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_request_cpu_core_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_effective_usage_cpu_core_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_limit_cpu_core_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_usage_memory_gigabyte_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_request_memory_gigabyte_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_effective_usage_memory_gigabyte_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_limit_memory_gigabyte_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    node_capacity_cpu_cores = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    node_capacity_cpu_core_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    node_capacity_memory_gigabytes = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    node_capacity_memory_gigabyte_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cluster_capacity_cpu_core_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cluster_capacity_memory_gigabyte_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    # Volume specific fields
    persistentvolumeclaim = models.CharField(max_length=253, null=True)
    persistentvolume = models.CharField(max_length=253, null=True)
    storageclass = models.CharField(max_length=253, null=True)
    volume_labels = JSONField(null=True)
    all_labels = JSONField(null=True)
    persistentvolumeclaim_capacity_gigabyte = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    persistentvolumeclaim_capacity_gigabyte_months = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    volume_request_storage_gigabyte_months = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    persistentvolumeclaim_usage_gigabyte_months = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    # Cost fields
    # Infrastructure raw cost comes from a Cloud Provider
    infrastructure_raw_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True, default=Decimal(0))
    infrastructure_project_raw_cost = models.DecimalField(
        max_digits=33, decimal_places=15, null=True, default=Decimal(0)
    )
    infrastructure_data_in_gigabytes = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_data_out_gigabytes = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_usage_cost = JSONField(null=True)
    infrastructure_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_project_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_monthly_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_monthly_cost_json = JSONField(null=True)
    infrastructure_project_monthly_cost = JSONField(null=True)
    supplementary_usage_cost = JSONField(null=True)
    supplementary_monthly_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    supplementary_monthly_cost_json = JSONField(null=True)
    infrastructure_project_monthly_cost = JSONField(null=True)
    supplementary_project_monthly_cost = JSONField(null=True)

    # Simplified Cost Model Cost terms
    cost_model_cpu_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_memory_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_volume_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_rate_type = models.TextField(null=True)

    monthly_cost_type = models.TextField(null=True, choices=MONTHLY_COST_TYPES)
    source_uuid = models.UUIDField(unique=False, null=True)
    raw_currency = models.TextField(null=True)
    distributed_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)


class OCPTagsValues(models.Model):
    class Meta:
        """Meta for OCPUsageTagValues."""

        db_table = "reporting_ocptags_values"
        unique_together = ("key", "value")
        indexes = [models.Index(fields=["key"], name="openshift_tags_value_key_idx")]

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    key = models.TextField()
    value = models.TextField()
    cluster_ids = ArrayField(models.TextField())
    cluster_aliases = ArrayField(models.TextField())
    namespaces = ArrayField(models.TextField())
    nodes = ArrayField(models.TextField(), null=True)


class OCPUsagePodLabelSummary(models.Model):
    """A collection of all current existing tag key and values."""

    class Meta:
        """Meta for OCPUsagePodLabelSummary."""

        db_table = "reporting_ocpusagepodlabel_summary"
        unique_together = ("key", "report_period", "namespace", "node")
        indexes = [models.Index(fields=["key"], name="openshift_pod_label_key_idx")]

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    key = models.TextField()
    values = ArrayField(models.TextField())
    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE)
    namespace = models.TextField()
    node = models.TextField(null=True)


class OCPStorageVolumeLabelSummary(models.Model):
    """A collection of all current existing tag key and values."""

    class Meta:
        """Meta for OCPStorageVolumeLabelSummary."""

        db_table = "reporting_ocpstoragevolumelabel_summary"
        unique_together = ("key", "report_period", "namespace", "node")
        indexes = [models.Index(fields=["key"], name="openshift_vol_label_key_idx")]

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    key = models.TextField()
    values = ArrayField(models.TextField())
    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE)
    namespace = models.TextField()
    node = models.TextField(null=True)


class OCPCluster(models.Model):
    """All clusters for a tenant."""

    class Meta:
        """Meta for OCPCluster."""

        db_table = "reporting_ocp_clusters"
        unique_together = ("cluster_id", "cluster_alias", "provider")

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    cluster_id = models.TextField()
    cluster_alias = models.TextField(null=True)
    provider = models.ForeignKey("reporting.TenantAPIProvider", on_delete=models.CASCADE)


class OCPNode(models.Model):
    """All nodes for a cluster."""

    class Meta:
        """Meta for OCPNode."""

        db_table = "reporting_ocp_nodes"

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    node = models.TextField()
    resource_id = models.TextField(null=True)
    node_capacity_cpu_cores = models.DecimalField(max_digits=18, decimal_places=2, null=True)
    cluster = models.ForeignKey("OCPCluster", on_delete=models.CASCADE)
    node_role = models.TextField(null=True)
    architecture = models.TextField(null=True)


class OCPNetworkSummaryP(models.Model):
    """Store summary of bytes in, bytes out, and costs per cluster per day"""

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        db_table = "reporting_ocp_network_summary_p"
        indexes = [models.Index(fields=["usage_start"], name="ocp_net_summ_usage_start")]

    id = models.UUIDField(primary_key=True)

    cluster_alias = models.TextField(null=True)
    cluster_id = models.TextField()
    # Cost model fields need to exist even though they are not relevant to this model
    cost_model_cpu_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_memory_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_rate_type = models.TextField(null=True)
    cost_model_volume_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    data_source = models.CharField(max_length=64, null=True)
    distributed_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_data_in_gigabytes = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_data_out_gigabytes = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_raw_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    raw_currency = models.TextField(null=True)
    resource_count = models.IntegerField(null=True)
    resource_ids = ArrayField(models.CharField(max_length=256), null=True)
    usage_end = models.DateField(null=False)
    usage_start = models.DateField(null=False)

    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE, null=True)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class OCPNetworkSummaryByNodeP(models.Model):
    """Network traffic costs in and out per node"""

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        db_table = "reporting_ocp_network_summary_by_node_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocp_net_summ_node_usage_start"),
            models.Index(fields=["node"], name="ocp_net_summ_node_node"),
        ]

    id = models.UUIDField(primary_key=True)

    cluster_alias = models.TextField(null=True)
    cluster_id = models.TextField()
    cost_model_cpu_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_memory_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_rate_type = models.TextField(null=True)
    cost_model_volume_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    data_source = models.CharField(max_length=64, null=True)
    distributed_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_data_in_gigabytes = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_data_out_gigabytes = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_raw_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    node = models.CharField(max_length=253, null=True)
    raw_currency = models.TextField(null=True)
    resource_count = models.IntegerField(null=True)
    resource_ids = ArrayField(models.CharField(max_length=256), null=True)
    usage_end = models.DateField(null=False)
    usage_start = models.DateField(null=False)

    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE, null=True)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class OCPNetworkSummaryByProjectP(models.Model):
    """Network traffic costs in and out per project"""

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        db_table = "reporting_ocp_network_summary_by_project_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocp_net_summ_proj_usage_start"),
            models.Index(fields=["namespace"], name="ocp_net_summ_proj_namespace"),
        ]

    id = models.UUIDField(primary_key=True)

    cluster_alias = models.TextField(null=True)
    cluster_id = models.TextField()
    cost_model_cpu_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_memory_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_rate_type = models.TextField(null=True)
    cost_model_volume_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    data_source = models.CharField(max_length=64, null=True)
    distributed_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_data_in_gigabytes = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_data_out_gigabytes = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_raw_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    namespace = models.CharField(max_length=253, null=True)
    raw_currency = models.TextField(null=True)
    resource_count = models.IntegerField(null=True)
    resource_ids = ArrayField(models.CharField(max_length=256), null=True)
    usage_end = models.DateField(null=False)
    usage_start = models.DateField(null=False)

    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE, null=True)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class OCPVirtualMachineSummaryP(models.Model):
    """Store summary of bytes in, bytes out, and costs per cluster per day"""

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        db_table = "reporting_ocp_vm_summary_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocp_vm_summ_usage_start"),
            models.Index(fields=["cluster_id"], name="ocp_vm_summ_cluster_id"),
            models.Index(fields=["namespace"], name="ocp_vm_summ_namespace"),
            models.Index(fields=["node"], name="ocp_vm_summ_node"),
            models.Index(fields=["vm_name"], name="ocp_vm_summ_vm_name"),
            GinIndex(fields=["pod_labels"], name="ocp_vm_summ_pod_labels_idx"),
        ]
        unique_together = (
            "usage_start",
            "cluster_id",
            "namespace",
            "node",
            "vm_name",
            "cost_model_rate_type",
            "persistentvolumeclaim",
        )

    id = models.UUIDField(primary_key=True)

    cluster_alias = models.TextField(null=True)
    cluster_id = models.TextField(null=True)
    namespace = models.CharField(max_length=253, null=True)
    node = models.CharField(max_length=253, null=True)
    vm_name = models.TextField(null=True)
    # Cost model fields need to exist even though they are not relevant to this model
    cost_model_cpu_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_memory_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_rate_type = models.TextField(null=True)
    cost_model_volume_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    distributed_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    pod_labels = JSONField(null=True)
    pod_request_cpu_core_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_request_memory_gigabyte_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    # Storage
    persistentvolumeclaim = models.CharField(max_length=253, null=True)
    storageclass = models.CharField(max_length=253, null=True)
    persistentvolumeclaim_usage_gigabyte_months = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    persistentvolumeclaim_capacity_gigabyte_months = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    infrastructure_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_raw_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    raw_currency = models.TextField(null=True)

    resource_ids = ArrayField(models.CharField(max_length=256), null=True)
    usage_end = models.DateField(null=False)
    usage_start = models.DateField(null=False)

    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE, null=True)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class OCPPVC(models.Model):
    """All PVCs for a cluster."""

    class Meta:
        """Meta for OCPPVC."""

        db_table = "reporting_ocp_pvcs"
        unique_together = ("persistent_volume", "persistent_volume_claim", "cluster")

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    persistent_volume_claim = models.TextField()
    persistent_volume = models.TextField()
    cluster = models.ForeignKey("OCPCluster", on_delete=models.CASCADE)
    csi_volume_handle = models.TextField(null=True)


class OpenshiftCostCategory(models.Model):
    """OpenshiftCostCategory for bucketing project costs."""

    class Meta:
        """Meta for CostCategories."""

        db_table = "reporting_ocp_cost_category"

    name = models.TextField(unique=True)
    description = models.TextField()
    source_type = models.TextField()
    system_default = models.BooleanField(null=False, default=False)
    label = ArrayField(models.TextField())


class OpenshiftCostCategoryNamespace(models.Model):
    """Namespaces to bucket to category."""

    class Meta:
        """Meta for cost category namespaces."""

        db_table = "reporting_ocp_cost_category_namespace"

    namespace = models.TextField(unique=True)
    system_default = models.BooleanField(null=False, default=False)
    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE)


class OCPProject(models.Model):
    """All Projects for a cluster."""

    class Meta:
        """Meta for OCPProject."""

        db_table = "reporting_ocp_projects"
        unique_together = ("project", "cluster")

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    project = models.TextField()
    cluster = models.ForeignKey("OCPCluster", on_delete=models.CASCADE)


# ======================================================
#  Partitioned Models to replace matviews
# ======================================================


class OCPCostSummaryP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPCostSummaryP."""

        db_table = "reporting_ocp_cost_summary_p"
        indexes = [models.Index(fields=["usage_start"], name="ocpcostsumm_usage_start")]

    id = models.UUIDField(primary_key=True)
    cluster_id = models.TextField()
    cluster_alias = models.TextField(null=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    infrastructure_raw_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_usage_cost = JSONField(null=True)
    infrastructure_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_monthly_cost_json = JSONField(null=True)
    supplementary_usage_cost = JSONField(null=True)
    supplementary_monthly_cost_json = JSONField(null=True)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE, null=True)
    raw_currency = models.TextField(null=True)
    distributed_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    # Simplified Cost Model Cost terms
    cost_model_cpu_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_memory_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_volume_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_rate_type = models.TextField(null=True)


class OCPCostSummaryByProjectP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPCostSummaryByProjectP."""

        db_table = "reporting_ocp_cost_summary_by_project_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocpcostsumm_proj_usage_start"),
            models.Index(fields=["namespace"], name="ocpcostsumm_proj_namespace"),
        ]

    id = models.UUIDField(primary_key=True)
    cluster_id = models.TextField()
    cluster_alias = models.TextField(null=True)
    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    infrastructure_usage_cost = JSONField(null=True)
    infrastructure_raw_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_project_monthly_cost = JSONField(null=True)
    supplementary_usage_cost = JSONField(null=True)
    supplementary_project_monthly_cost = JSONField(null=True)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE, null=True)
    raw_currency = models.TextField(null=True)
    distributed_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    # Simplified Cost Model Cost terms
    cost_model_cpu_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_memory_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_volume_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_rate_type = models.TextField(null=True)


class OCPCostSummaryByNodeP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPCostSummaryByNodeP."""

        db_table = "reporting_ocp_cost_summary_by_node_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocpcostsumm_node_usage_start"),
            models.Index(fields=["node"], name="ocpcostsumm_node_node"),
        ]

    id = models.UUIDField(primary_key=True)
    cluster_id = models.TextField()
    cluster_alias = models.TextField(null=True)
    node = models.CharField(max_length=253, null=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    infrastructure_raw_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_usage_cost = JSONField(null=True)
    infrastructure_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_monthly_cost_json = JSONField(null=True)
    supplementary_usage_cost = JSONField(null=True)
    supplementary_monthly_cost_json = JSONField(null=True)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE, null=True)
    raw_currency = models.TextField(null=True)
    distributed_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    # Simplified Cost Model Cost terms
    cost_model_cpu_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_memory_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_volume_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_rate_type = models.TextField(null=True)


class OCPPodSummaryP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPPodSummaryP."""

        db_table = "reporting_ocp_pod_summary_p"
        indexes = [models.Index(fields=["usage_start"], name="ocppodsumm_usage_start")]

    id = models.UUIDField(primary_key=True)
    cluster_id = models.TextField()
    cluster_alias = models.TextField(null=True)
    resource_ids = ArrayField(models.CharField(max_length=256), null=True)
    resource_count = models.IntegerField(null=True)
    data_source = models.CharField(max_length=64, null=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    infrastructure_raw_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_usage_cost = JSONField(null=True)
    infrastructure_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_monthly_cost_json = JSONField(null=True)
    supplementary_usage_cost = JSONField(null=True)
    supplementary_monthly_cost_json = JSONField(null=True)
    pod_usage_cpu_core_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_request_cpu_core_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_effective_usage_cpu_core_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_limit_cpu_core_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_usage_memory_gigabyte_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_request_memory_gigabyte_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_effective_usage_memory_gigabyte_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_limit_memory_gigabyte_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cluster_capacity_cpu_core_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cluster_capacity_memory_gigabyte_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE, null=True)
    raw_currency = models.TextField(null=True)
    distributed_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    # Simplified Cost Model Cost terms
    cost_model_cpu_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_memory_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_volume_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_rate_type = models.TextField(null=True)


class OCPPodSummaryByProjectP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPPodSummaryByProjectP."""

        db_table = "reporting_ocp_pod_summary_by_project_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocppodsumm_proj_usage_start"),
            models.Index(fields=["namespace"], name="ocppodsumm_proj_namespace"),
        ]

    id = models.UUIDField(primary_key=True)
    cluster_id = models.TextField()
    cluster_alias = models.TextField(null=True)
    namespace = models.CharField(max_length=253, null=True)
    resource_ids = ArrayField(models.CharField(max_length=256), null=True)
    resource_count = models.IntegerField(null=True)
    data_source = models.CharField(max_length=64, null=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    infrastructure_raw_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_usage_cost = JSONField(null=True)
    infrastructure_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_monthly_cost_json = JSONField(null=True)
    supplementary_usage_cost = JSONField(null=True)
    supplementary_monthly_cost_json = JSONField(null=True)
    pod_usage_cpu_core_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_request_cpu_core_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_effective_usage_cpu_core_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_limit_cpu_core_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_usage_memory_gigabyte_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_request_memory_gigabyte_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_effective_usage_memory_gigabyte_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_limit_memory_gigabyte_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cluster_capacity_cpu_core_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cluster_capacity_memory_gigabyte_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE, null=True)
    raw_currency = models.TextField(null=True)
    distributed_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    # Simplified Cost Model Cost terms
    cost_model_cpu_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_memory_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_volume_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_rate_type = models.TextField(null=True)


class OCPPodSummaryByNodeP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPPodSummaryP."""

        db_table = "reporting_ocp_pod_summary_by_node_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocppodsummnode_usage_start"),
            models.Index(fields=["node"], name="ocppodsummnode_node"),
        ]

    id = models.UUIDField(primary_key=True)
    cluster_id = models.TextField()
    cluster_alias = models.TextField(null=True)
    node = models.CharField(max_length=253, null=True)
    resource_ids = ArrayField(models.CharField(max_length=256), null=True)
    resource_count = models.IntegerField(null=True)
    data_source = models.CharField(max_length=64, null=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    infrastructure_raw_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_usage_cost = JSONField(null=True)
    infrastructure_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_monthly_cost_json = JSONField(null=True)
    supplementary_usage_cost = JSONField(null=True)
    supplementary_monthly_cost_json = JSONField(null=True)
    pod_usage_cpu_core_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_request_cpu_core_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_effective_usage_cpu_core_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_limit_cpu_core_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_usage_memory_gigabyte_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_request_memory_gigabyte_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_effective_usage_memory_gigabyte_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    pod_limit_memory_gigabyte_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cluster_capacity_cpu_core_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cluster_capacity_memory_gigabyte_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    node_capacity_cpu_cores = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    node_capacity_cpu_core_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    node_capacity_memory_gigabytes = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    node_capacity_memory_gigabyte_hours = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE, null=True)
    raw_currency = models.TextField(null=True)
    distributed_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    # Simplified Cost Model Cost terms
    cost_model_cpu_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_memory_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_volume_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_rate_type = models.TextField(null=True)


class OCPVolumeSummaryP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPVolumeSummaryP."""

        db_table = "reporting_ocp_volume_summary_p"
        indexes = [models.Index(fields=["usage_start"], name="ocpvolsumm_usage_start")]

    id = models.UUIDField(primary_key=True)
    cluster_id = models.TextField()
    cluster_alias = models.TextField(null=True)
    resource_ids = ArrayField(models.CharField(max_length=256), null=True)
    resource_count = models.IntegerField(null=True)
    data_source = models.CharField(max_length=64, null=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    infrastructure_raw_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_usage_cost = JSONField(null=True)
    infrastructure_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_monthly_cost_json = JSONField(null=True)
    supplementary_usage_cost = JSONField(null=True)
    supplementary_monthly_cost_json = JSONField(null=True)
    volume_request_storage_gigabyte_months = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    persistentvolumeclaim = models.CharField(max_length=253, null=True)
    storageclass = models.CharField(max_length=253, null=True)
    persistentvolumeclaim_usage_gigabyte_months = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    persistentvolumeclaim_capacity_gigabyte_months = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE, null=True)
    raw_currency = models.TextField(null=True)
    distributed_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    # Simplified Cost Model Cost terms
    cost_model_cpu_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_memory_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_volume_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_rate_type = models.TextField(null=True)


class OCPVolumeSummaryByProjectP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCPVolumeSummaryByProjectP."""

        db_table = "reporting_ocp_volume_summary_by_project_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocpvolsumm_proj_usage_start"),
            models.Index(fields=["namespace"], name="ocpvolsumm_proj_namespace"),
        ]

    id = models.UUIDField(primary_key=True)
    cluster_id = models.TextField()
    cluster_alias = models.TextField(null=True)
    namespace = models.CharField(max_length=253, null=True)
    resource_ids = ArrayField(models.CharField(max_length=256), null=True)
    resource_count = models.IntegerField(null=True)
    data_source = models.CharField(max_length=64, null=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    infrastructure_raw_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_usage_cost = JSONField(null=True)
    infrastructure_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    infrastructure_monthly_cost_json = JSONField(null=True)
    supplementary_usage_cost = JSONField(null=True)
    supplementary_monthly_cost_json = JSONField(null=True)
    volume_request_storage_gigabyte_months = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    persistentvolumeclaim_usage_gigabyte_months = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    persistentvolumeclaim_capacity_gigabyte_months = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    cost_category = models.ForeignKey("OpenshiftCostCategory", on_delete=models.CASCADE, null=True)
    raw_currency = models.TextField(null=True)
    distributed_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    persistentvolumeclaim = models.CharField(max_length=253, null=True)
    storageclass = models.CharField(max_length=253, null=True)

    # Simplified Cost Model Cost terms
    cost_model_cpu_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_memory_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_volume_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    cost_model_rate_type = models.TextField(null=True)
