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
"""Models for OCP cost entry tables."""
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.fields import JSONField
from django.contrib.postgres.indexes import GinIndex
from django.db import models


class OCPUsageReportPeriod(models.Model):
    """The report period information for a Operator Metering report.

    The reporting period (1 month) will cover many reports.

    """

    class Meta:
        """Meta for OCPUsageReportPeriod."""

        unique_together = ("cluster_id", "report_period_start", "provider")

    cluster_id = models.CharField(max_length=50, null=False)
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

    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE)

    report = models.ForeignKey("OCPUsageReport", on_delete=models.CASCADE)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=False)

    pod = models.CharField(max_length=253, null=False)

    node = models.CharField(max_length=253, null=False)

    # Another node identifier used to tie the node to an EC2 instance
    resource_id = models.CharField(max_length=253, null=True)

    pod_usage_cpu_core_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_request_cpu_core_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_limit_cpu_core_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_usage_memory_byte_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_request_memory_byte_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_limit_memory_byte_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    node_capacity_cpu_cores = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    node_capacity_cpu_core_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    node_capacity_memory_bytes = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    node_capacity_memory_byte_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

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

    pod_usage_cpu_core_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_request_cpu_core_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_limit_cpu_core_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_usage_memory_byte_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_request_memory_byte_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_limit_memory_byte_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    node_capacity_cpu_cores = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    node_capacity_cpu_core_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    node_capacity_memory_bytes = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    node_capacity_memory_byte_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    cluster_capacity_cpu_core_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    cluster_capacity_memory_byte_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    # Total capacity represents the sum of all of the customers clusters
    total_capacity_cpu_core_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    total_capacity_memory_byte_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    total_seconds = models.IntegerField()

    pod_labels = JSONField(null=True)


class OCPUsageLineItemDailySummary(models.Model):
    """A daily aggregation of line items from pod and volume sources.

    This table is aggregated by OCP resource.

    """

    MONTHLY_COST_TYPES = (("Node", "Node"), ("Cluster", "Cluster"))
    MONTHLY_COST_RATE_MAP = {"Node": "node_cost_per_month", "Cluster": "cluster_cost_per_month"}

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

    id = models.BigAutoField(primary_key=True)

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

    pod_usage_cpu_core_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_request_cpu_core_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_limit_cpu_core_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_usage_memory_gigabyte_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_request_memory_gigabyte_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_limit_memory_gigabyte_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    node_capacity_cpu_cores = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    node_capacity_cpu_core_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    node_capacity_memory_gigabytes = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    node_capacity_memory_gigabyte_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    cluster_capacity_cpu_core_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    cluster_capacity_memory_gigabyte_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    # Total capacity represents the sum of all of the customers clusters
    total_capacity_cpu_core_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    total_capacity_memory_gigabyte_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    # Volume specific fields
    persistentvolumeclaim = models.CharField(max_length=253, null=True)

    persistentvolume = models.CharField(max_length=253, null=True)

    storageclass = models.CharField(max_length=50, null=True)

    volume_labels = JSONField(null=True)

    persistentvolumeclaim_capacity_gigabyte = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    persistentvolumeclaim_capacity_gigabyte_months = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    volume_request_storage_gigabyte_months = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    persistentvolumeclaim_usage_gigabyte_months = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    # Cost fields

    # Infrastructure raw cost comes from a Cloud Provider
    infrastructure_raw_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    infrastructure_project_raw_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    infrastructure_usage_cost = JSONField(null=True)

    infrastructure_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    infrastructure_project_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    infrastructure_monthly_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    supplementary_usage_cost = JSONField(null=True)

    supplementary_monthly_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    monthly_cost_type = models.TextField(null=True, choices=MONTHLY_COST_TYPES)

    source_uuid = models.UUIDField(unique=False, null=True)


class OCPUsagePodLabelSummary(models.Model):
    """A collection of all current existing tag key and values."""

    class Meta:
        """Meta for OCPUsageTagSummary."""

        db_table = "reporting_ocpusagepodlabel_summary"
        unique_together = ("key", "report_period")

    id = models.BigAutoField(primary_key=True)

    key = models.CharField(max_length=253)
    values = ArrayField(models.CharField(max_length=253))
    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE)
    namespace = ArrayField(models.CharField(max_length=253))


class OCPStorageLineItem(models.Model):
    """Raw report storage data for OpenShift pods."""

    class Meta:
        """Meta for OCPStorageLineItem."""

        unique_together = ("report", "namespace", "persistentvolumeclaim")

    id = models.BigAutoField(primary_key=True)

    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE)

    report = models.ForeignKey("OCPUsageReport", on_delete=models.CASCADE)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=False)

    pod = models.CharField(max_length=253, null=True)

    persistentvolumeclaim = models.CharField(max_length=253)

    persistentvolume = models.CharField(max_length=253)

    storageclass = models.CharField(max_length=50, null=True)

    persistentvolumeclaim_capacity_bytes = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    persistentvolumeclaim_capacity_byte_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    volume_request_storage_byte_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    persistentvolumeclaim_usage_byte_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

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

    persistentvolumeclaim_capacity_bytes = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    persistentvolumeclaim_capacity_byte_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    volume_request_storage_byte_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    persistentvolumeclaim_usage_byte_seconds = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    total_seconds = models.IntegerField()

    persistentvolume_labels = JSONField(null=True)
    persistentvolumeclaim_labels = JSONField(null=True)


class OCPStorageVolumeLabelSummary(models.Model):
    """A collection of all current existing tag key and values."""

    class Meta:
        """Meta for OCPStorageVolumeLabelSummary."""

        db_table = "reporting_ocpstoragevolumelabel_summary"
        unique_together = ("key", "report_period")

    id = models.BigAutoField(primary_key=True)

    key = models.CharField(max_length=253)
    values = ArrayField(models.CharField(max_length=253))
    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE)
    namespace = ArrayField(models.CharField(max_length=253))


class OCPStorageVolumeClaimLabelSummary(models.Model):
    """A collection of all current existing tag key and values."""

    class Meta:
        """Meta for OCPStorageVolumeClaimLabelSummary."""

        db_table = "reporting_ocpstoragevolumeclaimlabel_summary"
        unique_together = ("key", "report_period")

    id = models.BigAutoField(primary_key=True)

    key = models.CharField(max_length=253)
    values = ArrayField(models.CharField(max_length=253))
    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE)
    namespace = ArrayField(models.CharField(max_length=253))


class OCPNodeLabelLineItem(models.Model):
    """Raw report label data for OpenShift nodes."""

    class Meta:
        """Meta for OCPNodeLabelLineItem."""

        db_table = "reporting_ocpnodelabellineitem"
        unique_together = ("report", "node")

    id = models.BigAutoField(primary_key=True)

    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE)

    report = models.ForeignKey("OCPUsageReport", on_delete=models.CASCADE)

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


class OCPEnabledTagKeys(models.Model):
    """A collection of the current enabled tag keys."""

    class Meta:
        """Meta for OCPEnabledTagKeys."""

        db_table = "reporting_ocpenabledtagkeys"

    id = models.BigAutoField(primary_key=True)
    key = models.CharField(max_length=253, unique=True)


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

    infrastructure_raw_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    infrastructure_usage_cost = JSONField(null=True)

    infrastructure_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    infrastructure_monthly_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    supplementary_usage_cost = JSONField(null=True)

    supplementary_monthly_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

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

    infrastructure_project_raw_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    infrastructure_usage_cost = JSONField(null=True)

    infrastructure_project_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    infrastructure_monthly_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    supplementary_usage_cost = JSONField(null=True)

    supplementary_monthly_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    source_uuid = models.UUIDField(unique=False, null=True)


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

    infrastructure_raw_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    infrastructure_usage_cost = JSONField(null=True)

    infrastructure_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    infrastructure_monthly_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    supplementary_usage_cost = JSONField(null=True)

    supplementary_monthly_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

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

    infrastructure_raw_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    infrastructure_usage_cost = JSONField(null=True)

    infrastructure_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    supplementary_usage_cost = JSONField(null=True)

    pod_usage_cpu_core_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_request_cpu_core_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_limit_cpu_core_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_usage_memory_gigabyte_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_request_memory_gigabyte_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_limit_memory_gigabyte_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    cluster_capacity_cpu_core_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)
    # Total capacity represents the sum of all of the customers clusters
    total_capacity_cpu_core_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    total_capacity_memory_gigabyte_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    cluster_capacity_memory_gigabyte_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

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

    infrastructure_raw_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    infrastructure_usage_cost = JSONField(null=True)

    infrastructure_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    pod_usage_cpu_core_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_request_cpu_core_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_limit_cpu_core_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_usage_memory_gigabyte_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_request_memory_gigabyte_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    pod_limit_memory_gigabyte_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    cluster_capacity_cpu_core_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)
    # Total capacity represents the sum of all of the customers clusters
    total_capacity_cpu_core_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    total_capacity_memory_gigabyte_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    cluster_capacity_memory_gigabyte_hours = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    source_uuid = models.UUIDField(unique=False, null=True)


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

    infrastructure_raw_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    infrastructure_usage_cost = JSONField(null=True)

    infrastructure_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    persistentvolumeclaim_usage_gigabyte_months = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    volume_request_storage_gigabyte_months = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    persistentvolumeclaim_capacity_gigabyte_months = models.DecimalField(max_digits=27, decimal_places=9, null=True)

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

    infrastructure_raw_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    infrastructure_usage_cost = JSONField(null=True)

    infrastructure_markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    persistentvolumeclaim_usage_gigabyte_months = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    volume_request_storage_gigabyte_months = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    persistentvolumeclaim_capacity_gigabyte_months = models.DecimalField(max_digits=27, decimal_places=9, null=True)

    source_uuid = models.UUIDField(unique=False, null=True)
