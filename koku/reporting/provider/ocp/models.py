#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for OCP cost entry tables."""
from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import JSONField

PRESTO_LINE_ITEM_TABLE_MAP = {
    "pod_usage": "openshift_pod_usage_line_items",
    "storage_usage": "openshift_storage_usage_line_items",
    "node_labels": "openshift_node_labels_line_items",
    "namespace_labels": "openshift_namespace_labels_line_items",
}

PRESTO_LINE_ITEM_TABLE_DAILY_MAP = {
    "pod_usage": "openshift_pod_usage_line_items_daily",
    "storage_usage": "openshift_storage_usage_line_items_daily",
    "node_labels": "openshift_node_labels_line_items_daily",
    "namespace_labels": "openshift_namespace_labels_line_items_daily",
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
    "reporting_ocp_pod_summary_by_project_p",
    "reporting_ocp_volume_summary_p",
    "reporting_ocp_volume_summary_by_project_p",
)


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
    derived_cost_datetime = models.DateTimeField(null=True)

    provider = models.ForeignKey("api.Provider", on_delete=models.CASCADE)


class OCPUsageReport(models.Model):
    """An entry for a single report from Operator Metering.

    A cost entry covers a specific time interval (e.g. 1 hour).

    """

    class Meta:
        """Meta for OCPUsageReport."""

        unique_together = ("report_period", "interval_start")

        indexes = [models.Index(fields=["interval_start"], name="ocp_interval_start_idx")]

    interval_start = models.DateTimeField(null=False)
    interval_end = models.DateTimeField(null=False)

    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE)


class OCPUsageLineItem(models.Model):
    """Raw report data for OpenShift pods."""

    class Meta:
        """Meta for OCPUsageLineItem."""

        unique_together = ("report", "namespace", "pod", "node")

    id = models.BigAutoField(primary_key=True)

    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE, db_constraint=False)

    report = models.ForeignKey("OCPUsageReport", on_delete=models.CASCADE, db_constraint=False)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=False)

    pod = models.CharField(max_length=253, null=False)

    node = models.CharField(max_length=253, null=False)

    # Another node identifier used to tie the node to an EC2 instance
    resource_id = models.CharField(max_length=253, null=True)

    pod_usage_cpu_core_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    pod_request_cpu_core_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    pod_limit_cpu_core_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    pod_usage_memory_byte_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    pod_request_memory_byte_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    pod_limit_memory_byte_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    node_capacity_cpu_cores = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    node_capacity_cpu_core_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    node_capacity_memory_bytes = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    node_capacity_memory_byte_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    pod_labels = JSONField(null=True)


class OCPUsageLineItemDaily(models.Model):
    """A daily aggregation of line items.

    This table is aggregated by OCP resource.

    """

    class Meta:
        """Meta for OCPUsageLineItemDaily."""

        db_table = "reporting_ocpusagelineitem_daily"

        indexes = [
            models.Index(fields=["usage_start"], name="ocp_usage_idx"),
            models.Index(fields=["namespace"], name="namespace_idx", opclasses=["varchar_pattern_ops"]),
            models.Index(fields=["pod"], name="pod_idx"),
            models.Index(fields=["node"], name="node_idx", opclasses=["varchar_pattern_ops"]),
        ]

    id = models.BigAutoField(primary_key=True)

    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE, null=True)

    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=False)

    pod = models.CharField(max_length=253, null=False)

    node = models.CharField(max_length=253, null=False)

    # Another node identifier used to tie the node to an EC2 instance
    resource_id = models.CharField(max_length=253, null=True)

    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)

    pod_usage_cpu_core_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    pod_request_cpu_core_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    pod_limit_cpu_core_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    pod_usage_memory_byte_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    pod_request_memory_byte_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    pod_limit_memory_byte_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    node_capacity_cpu_cores = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    node_capacity_cpu_core_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    node_capacity_memory_bytes = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    node_capacity_memory_byte_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    cluster_capacity_cpu_core_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    cluster_capacity_memory_byte_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    total_seconds = models.IntegerField()

    pod_labels = JSONField(null=True)


class OCPUsageLineItemDailySummary(models.Model):
    """A daily aggregation of line items from pod and volume sources.

    This table is aggregated by OCP resource.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    MONTHLY_COST_TYPES = (("Node", "Node"), ("Cluster", "Cluster"), ("PVC", "PVC"))
    MONTHLY_COST_RATE_MAP = {
        "Node": "node_cost_per_month",
        "Cluster": "cluster_cost_per_month",
        "PVC": "pvc_cost_per_month",
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
            GinIndex(fields=["pod_labels"], name="pod_labels_idx"),
        ]

    uuid = models.UUIDField(primary_key=True)

    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE, null=True)

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

    pod_usage_cpu_core_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_request_cpu_core_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_limit_cpu_core_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_usage_memory_gigabyte_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_request_memory_gigabyte_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_limit_memory_gigabyte_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    node_capacity_cpu_cores = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    node_capacity_cpu_core_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    node_capacity_memory_gigabytes = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    node_capacity_memory_gigabyte_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    cluster_capacity_cpu_core_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    cluster_capacity_memory_gigabyte_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    # Volume specific fields
    persistentvolumeclaim = models.CharField(max_length=253, null=True)

    persistentvolume = models.CharField(max_length=253, null=True)

    storageclass = models.CharField(max_length=50, null=True)

    volume_labels = JSONField(null=True)

    persistentvolumeclaim_capacity_gigabyte = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    persistentvolumeclaim_capacity_gigabyte_months = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    volume_request_storage_gigabyte_months = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    persistentvolumeclaim_usage_gigabyte_months = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    # Cost fields

    # Infrastructure raw cost comes from a Cloud Provider
    infrastructure_raw_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS,
        decimal_places=settings.NUMERIC_DECIMAL_PLACES,
        null=True,
        default=Decimal(0),
    )

    infrastructure_project_raw_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS,
        decimal_places=settings.NUMERIC_DECIMAL_PLACES,
        null=True,
        default=Decimal(0),
    )

    infrastructure_usage_cost = JSONField(null=True)

    infrastructure_markup_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_project_markup_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_monthly_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )
    infrastructure_monthly_cost_json = JSONField(null=True)

    infrastructure_project_monthly_cost = JSONField(null=True)

    supplementary_usage_cost = JSONField(null=True)

    supplementary_monthly_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )
    supplementary_monthly_cost_json = JSONField(null=True)

    infrastructure_project_monthly_cost = JSONField(null=True)

    supplementary_project_monthly_cost = JSONField(null=True)

    monthly_cost_type = models.TextField(null=True, choices=MONTHLY_COST_TYPES)

    source_uuid = models.UUIDField(unique=False, null=True)


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

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    key = models.TextField()
    values = ArrayField(models.TextField())
    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE)
    namespace = models.TextField()
    node = models.TextField(null=True)


class OCPStorageLineItem(models.Model):
    """Raw report storage data for OpenShift pods."""

    class Meta:
        """Meta for OCPStorageLineItem."""

        unique_together = ("report", "namespace", "persistentvolumeclaim")

    id = models.BigAutoField(primary_key=True)

    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE, db_constraint=False)

    report = models.ForeignKey("OCPUsageReport", on_delete=models.CASCADE, db_constraint=False)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=False)

    pod = models.CharField(max_length=253, null=True)

    persistentvolumeclaim = models.CharField(max_length=253)

    persistentvolume = models.CharField(max_length=253)

    storageclass = models.CharField(max_length=50, null=True)

    persistentvolumeclaim_capacity_bytes = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    persistentvolumeclaim_capacity_byte_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    volume_request_storage_byte_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    persistentvolumeclaim_usage_byte_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    persistentvolume_labels = JSONField(null=True)
    persistentvolumeclaim_labels = JSONField(null=True)


class OCPStorageLineItemDaily(models.Model):
    """A daily aggregation of storage line items.

    This table is aggregated by OCP resource.

    """

    class Meta:
        """Meta for OCPUStorageLineItemDaily."""

        db_table = "reporting_ocpstoragelineitem_daily"
        indexes = [
            models.Index(fields=["namespace"], name="ocp_storage_li_namespace_idx", opclasses=["varchar_pattern_ops"]),
            models.Index(fields=["node"], name="ocp_storage_li_node_idx", opclasses=["varchar_pattern_ops"]),
        ]

    id = models.BigAutoField(primary_key=True)

    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE, null=True)

    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=False)

    pod = models.CharField(max_length=253, null=True)

    node = models.CharField(max_length=253, null=True)

    persistentvolumeclaim = models.CharField(max_length=253)

    persistentvolume = models.CharField(max_length=253)

    storageclass = models.CharField(max_length=50, null=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)

    persistentvolumeclaim_capacity_bytes = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    persistentvolumeclaim_capacity_byte_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    volume_request_storage_byte_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    persistentvolumeclaim_usage_byte_seconds = models.DecimalField(max_digits=73, decimal_places=9, null=True)

    total_seconds = models.IntegerField()

    persistentvolume_labels = JSONField(null=True)
    persistentvolumeclaim_labels = JSONField(null=True)


class OCPStorageVolumeLabelSummary(models.Model):
    """A collection of all current existing tag key and values."""

    class Meta:
        """Meta for OCPStorageVolumeLabelSummary."""

        db_table = "reporting_ocpstoragevolumelabel_summary"
        unique_together = ("key", "report_period", "namespace", "node")

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    key = models.TextField()
    values = ArrayField(models.TextField())
    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE)
    namespace = models.TextField()
    node = models.TextField(null=True)


class OCPNodeLabelLineItem(models.Model):
    """Raw report label data for OpenShift nodes."""

    class Meta:
        """Meta for OCPNodeLabelLineItem."""

        db_table = "reporting_ocpnodelabellineitem"
        unique_together = ("report", "node")

    id = models.BigAutoField(primary_key=True)

    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE, db_constraint=False)

    report = models.ForeignKey("OCPUsageReport", on_delete=models.CASCADE, db_constraint=False)

    # Kubernetes objects by convention have a max name length of 253 chars
    node = models.CharField(max_length=253, null=True)

    node_labels = JSONField(null=True)


class OCPNodeLabelLineItemDaily(models.Model):
    """A daily aggregation of node label line items.

    This table is aggregated by OCP resource.

    """

    class Meta:
        """Meta for OCPNodeLabelLineItemDaily."""

        db_table = "reporting_ocpnodelabellineitem_daily"
        indexes = [
            models.Index(fields=["usage_start"], name="ocplblnitdly_usage_start"),
            GinIndex(fields=["node_labels"], name="ocplblnitdly_node_labels"),
        ]

    id = models.BigAutoField(primary_key=True)

    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE, null=True)

    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    node = models.CharField(max_length=253, null=True)

    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)

    node_labels = JSONField(null=True)

    total_seconds = models.IntegerField()


class OCPNamespaceLabelLineItem(models.Model):
    """Raw report label data for OpenShift namespaces."""

    class Meta:
        """Meta for OCPNamespaceLabelLineItem."""

        db_table = "reporting_ocpnamespacelabellineitem"
        unique_together = ("report", "namespace")

    id = models.BigAutoField(primary_key=True)

    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE)

    report = models.ForeignKey("OCPUsageReport", on_delete=models.CASCADE)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=True)

    namespace_labels = JSONField(null=True)


class OCPEnabledTagKeys(models.Model):
    """A collection of the current enabled tag keys."""

    class Meta:
        """Meta for OCPEnabledTagKeys."""

        db_table = "reporting_ocpenabledtagkeys"

    id = models.BigAutoField(primary_key=True)
    key = models.CharField(max_length=253, unique=True)


class OCPCluster(models.Model):
    """All clusters for a tenant."""

    class Meta:
        """Meta for OCPCluster."""

        db_table = "reporting_ocp_clusters"

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    cluster_id = models.TextField()
    cluster_alias = models.TextField(null=True)
    provider = models.ForeignKey("api.Provider", on_delete=models.CASCADE)


class OCPNode(models.Model):
    """All nodes for a cluster."""

    class Meta:
        """Meta for OCPNode."""

        db_table = "reporting_ocp_nodes"

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    node = models.TextField()
    resource_id = models.TextField(null=True)
    node_capacity_cpu_cores = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )
    cluster = models.ForeignKey("OCPCluster", on_delete=models.CASCADE)


class OCPPVC(models.Model):
    """All PVCs for a cluster."""

    class Meta:
        """Meta for OCPPVC."""

        db_table = "reporting_ocp_pvcs"

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    persistent_volume_claim = models.TextField()
    persistent_volume = models.TextField()
    cluster = models.ForeignKey("OCPCluster", on_delete=models.CASCADE)


class OCPProject(models.Model):
    """All Projects for a cluster."""

    class Meta:
        """Meta for OCPProject."""

        db_table = "reporting_ocp_projects"

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    project = models.TextField()
    cluster = models.ForeignKey("OCPCluster", on_delete=models.CASCADE)


class OCPCostSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class Meta:
        """Meta for OCPCostSummary."""

        db_table = "reporting_ocp_cost_summary"
        managed = False

    id = models.IntegerField(primary_key=True)

    cluster_id = models.TextField()

    cluster_alias = models.TextField(null=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    infrastructure_raw_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_usage_cost = JSONField(null=True)

    infrastructure_markup_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_monthly_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )
    infrastructure_monthly_cost_json = JSONField(null=True)

    supplementary_usage_cost = JSONField(null=True)

    supplementary_monthly_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )
    supplementary_monthly_cost_json = JSONField(null=True)

    source_uuid = models.UUIDField(unique=False, null=True)


class OCPCostSummaryByProject(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class Meta:
        """Meta for OCPCostSummaryByProject."""

        db_table = "reporting_ocp_cost_summary_by_project"
        managed = False

    id = models.IntegerField(primary_key=True)

    cluster_id = models.TextField()

    cluster_alias = models.TextField(null=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    infrastructure_project_raw_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_usage_cost = JSONField(null=True)

    infrastructure_project_markup_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    supplementary_usage_cost = JSONField(null=True)

    source_uuid = models.UUIDField(unique=False, null=True)

    infrastructure_monthly_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    supplementary_monthly_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_project_monthly_cost = JSONField(null=True)

    supplementary_project_monthly_cost = JSONField(null=True)


class OCPCostSummaryByNode(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class Meta:
        """Meta for OCPCostSummary."""

        db_table = "reporting_ocp_cost_summary_by_node"
        managed = False

    id = models.IntegerField(primary_key=True)

    cluster_id = models.TextField()

    cluster_alias = models.TextField(null=True)

    node = models.CharField(max_length=253, null=False)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    infrastructure_raw_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_usage_cost = JSONField(null=True)

    infrastructure_markup_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_monthly_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )
    infrastructure_monthly_cost_json = JSONField(null=True)

    supplementary_usage_cost = JSONField(null=True)

    supplementary_monthly_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )
    supplementary_monthly_cost_json = JSONField(null=True)

    source_uuid = models.UUIDField(unique=False, null=True)


class OCPPodSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class Meta:
        """Meta for OCPPodSummary."""

        db_table = "reporting_ocp_pod_summary"
        managed = False

    id = models.IntegerField(primary_key=True)

    cluster_id = models.TextField()

    cluster_alias = models.TextField(null=True)

    resource_ids = ArrayField(models.CharField(max_length=256), null=True)

    resource_count = models.IntegerField(null=True)

    data_source = models.CharField(max_length=64, null=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    infrastructure_raw_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_usage_cost = JSONField(null=True)

    infrastructure_markup_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    supplementary_usage_cost = JSONField(null=True)

    pod_usage_cpu_core_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_request_cpu_core_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_limit_cpu_core_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_usage_memory_gigabyte_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_request_memory_gigabyte_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_limit_memory_gigabyte_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    cluster_capacity_cpu_core_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    cluster_capacity_memory_gigabyte_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_monthly_cost = JSONField(null=True)

    supplementary_monthly_cost = JSONField(null=True)

    infrastructure_monthly_cost_json = JSONField(null=True)

    supplementary_monthly_cost_json = JSONField(null=True)

    source_uuid = models.UUIDField(unique=False, null=True)


class OCPPodSummaryByProject(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class Meta:
        """Meta for OCPPodSummaryByProject."""

        db_table = "reporting_ocp_pod_summary_by_project"
        managed = False

    id = models.IntegerField(primary_key=True)

    cluster_id = models.TextField()

    cluster_alias = models.TextField(null=True)

    namespace = models.CharField(max_length=253, null=True)

    resource_ids = ArrayField(models.CharField(max_length=256), null=True)

    resource_count = models.IntegerField(null=True)

    data_source = models.CharField(max_length=64, null=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    supplementary_usage_cost = JSONField(null=True)

    infrastructure_raw_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_usage_cost = JSONField(null=True)

    infrastructure_markup_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_usage_cpu_core_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_request_cpu_core_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_limit_cpu_core_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_usage_memory_gigabyte_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_request_memory_gigabyte_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_limit_memory_gigabyte_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    cluster_capacity_cpu_core_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    cluster_capacity_memory_gigabyte_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    source_uuid = models.UUIDField(unique=False, null=True)

    infrastructure_monthly_cost = JSONField(null=True)

    supplementary_monthly_cost = JSONField(null=True)

    infrastructure_monthly_cost_json = JSONField(null=True)

    supplementary_monthly_cost_json = JSONField(null=True)


class OCPVolumeSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class Meta:
        """Meta for OCPVolumeSummary."""

        db_table = "reporting_ocp_volume_summary"
        managed = False

    id = models.IntegerField(primary_key=True)

    cluster_id = models.TextField()

    cluster_alias = models.TextField(null=True)

    resource_ids = ArrayField(models.CharField(max_length=256), null=True)

    resource_count = models.IntegerField(null=True)

    data_source = models.CharField(max_length=64, null=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    supplementary_usage_cost = JSONField(null=True)

    infrastructure_raw_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_usage_cost = JSONField(null=True)

    infrastructure_markup_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    persistentvolumeclaim_usage_gigabyte_months = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    volume_request_storage_gigabyte_months = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    persistentvolumeclaim_capacity_gigabyte_months = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_monthly_cost = JSONField(null=True)

    supplementary_monthly_cost = JSONField(null=True)

    infrastructure_monthly_cost_json = JSONField(null=True)

    supplementary_monthly_cost_json = JSONField(null=True)

    source_uuid = models.UUIDField(unique=False, null=True)


class OCPVolumeSummaryByProject(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class Meta:
        """Meta for OCPVolumeSummaryByProject."""

        db_table = "reporting_ocp_volume_summary_by_project"
        managed = False

    id = models.IntegerField(primary_key=True)

    cluster_id = models.TextField()

    cluster_alias = models.TextField(null=True)

    namespace = models.CharField(max_length=253, null=True)

    resource_ids = ArrayField(models.CharField(max_length=256), null=True)

    resource_count = models.IntegerField(null=True)

    data_source = models.CharField(max_length=64, null=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    supplementary_usage_cost = JSONField(null=True)

    infrastructure_raw_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_usage_cost = JSONField(null=True)

    infrastructure_markup_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    persistentvolumeclaim_usage_gigabyte_months = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    volume_request_storage_gigabyte_months = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    persistentvolumeclaim_capacity_gigabyte_months = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    source_uuid = models.UUIDField(unique=False, null=True)

    infrastructure_monthly_cost = JSONField(null=True)

    supplementary_monthly_cost = JSONField(null=True)

    infrastructure_monthly_cost_json = JSONField(null=True)

    supplementary_monthly_cost_json = JSONField(null=True)


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

    infrastructure_raw_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_usage_cost = JSONField(null=True)

    infrastructure_markup_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_monthly_cost_json = JSONField(null=True)

    supplementary_usage_cost = JSONField(null=True)

    supplementary_monthly_cost_json = JSONField(null=True)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


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

    infrastructure_project_raw_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_project_markup_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_project_monthly_cost = JSONField(null=True)

    supplementary_usage_cost = JSONField(null=True)

    supplementary_project_monthly_cost = JSONField(null=True)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


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

    infrastructure_raw_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_usage_cost = JSONField(null=True)

    infrastructure_markup_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_monthly_cost_json = JSONField(null=True)

    supplementary_usage_cost = JSONField(null=True)

    supplementary_monthly_cost_json = JSONField(null=True)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


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

    infrastructure_raw_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_usage_cost = JSONField(null=True)

    infrastructure_markup_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_monthly_cost_json = JSONField(null=True)

    supplementary_usage_cost = JSONField(null=True)

    supplementary_monthly_cost_json = JSONField(null=True)

    pod_usage_cpu_core_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_request_cpu_core_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_limit_cpu_core_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_usage_memory_gigabyte_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_request_memory_gigabyte_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_limit_memory_gigabyte_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    cluster_capacity_cpu_core_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    cluster_capacity_memory_gigabyte_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


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

    infrastructure_raw_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_usage_cost = JSONField(null=True)

    infrastructure_markup_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_monthly_cost_json = JSONField(null=True)

    supplementary_usage_cost = JSONField(null=True)

    supplementary_monthly_cost_json = JSONField(null=True)

    pod_usage_cpu_core_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_request_cpu_core_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_limit_cpu_core_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_usage_memory_gigabyte_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_request_memory_gigabyte_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_limit_memory_gigabyte_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    cluster_capacity_cpu_core_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    cluster_capacity_memory_gigabyte_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


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

    infrastructure_raw_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_usage_cost = JSONField(null=True)

    infrastructure_markup_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_monthly_cost_json = JSONField(null=True)

    supplementary_usage_cost = JSONField(null=True)

    supplementary_monthly_cost_json = JSONField(null=True)

    volume_request_storage_gigabyte_months = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    persistentvolumeclaim_usage_gigabyte_months = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    persistentvolumeclaim_capacity_gigabyte_months = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


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

    infrastructure_raw_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_usage_cost = JSONField(null=True)

    infrastructure_markup_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    infrastructure_monthly_cost_json = JSONField(null=True)

    supplementary_usage_cost = JSONField(null=True)

    supplementary_monthly_cost_json = JSONField(null=True)

    volume_request_storage_gigabyte_months = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    persistentvolumeclaim_usage_gigabyte_months = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    persistentvolumeclaim_capacity_gigabyte_months = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
