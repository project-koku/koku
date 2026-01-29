#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Django models for OCP line item tables (on-prem PostgreSQL storage)."""
from uuid import uuid4

from django.db import models


class OCPLineItemBase(models.Model):
    """Abstract base class for OCP line item tables.

    These models replace the raw SQL table creation for on-prem PostgreSQL storage.
    They provide:
    - Django migration support for schema evolution
    - Single-column date partitioning (usage_start) for efficient data management
    - Integration with existing PartitionedTable infrastructure
    """

    class Meta:
        abstract = True

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    # UUID primary key for compatibility with SQLAlchemy to_sql and partitioned tables
    id = models.UUIDField(primary_key=True, default=uuid4)

    # Common columns across all OCP report types
    report_period_start = models.DateTimeField(null=True)
    report_period_end = models.DateTimeField(null=True)
    interval_start = models.DateTimeField(null=True, db_index=True)
    interval_end = models.DateTimeField(null=True)

    # Partition column - DateField for proper range partitioning (matches existing infrastructure)
    usage_start = models.DateField(null=True, db_index=True)

    # Partition-related columns (indexed, not partitioned in PostgreSQL)
    # source is stored as varchar to match Trino/parquet storage and existing SQL joins
    source = models.CharField(max_length=64, null=True, db_index=True)
    year = models.CharField(max_length=4, null=True)
    month = models.CharField(max_length=2, null=True)

    # Manifest tracking
    manifestid = models.CharField(max_length=256, null=True)
    reportnumhours = models.IntegerField(null=True)


class OCPPodUsageLineItem(OCPLineItemBase):
    """Model for openshift_pod_usage_line_items table."""

    class Meta:
        db_table = "openshift_pod_usage_line_items"
        indexes = [
            models.Index(fields=["source", "year", "month"], name="ocp_pod_src_yr_mo_idx"),
        ]

    # Pod identification
    pod = models.CharField(max_length=253, null=True)
    namespace = models.CharField(max_length=253, null=True)
    node = models.CharField(max_length=253, null=True)
    resource_id = models.CharField(max_length=256, null=True)
    pod_labels = models.TextField(null=True)
    node_role = models.CharField(max_length=64, null=True)

    # CPU metrics
    pod_usage_cpu_core_seconds = models.FloatField(null=True)
    pod_request_cpu_core_seconds = models.FloatField(null=True)
    pod_effective_usage_cpu_core_seconds = models.FloatField(null=True)
    pod_limit_cpu_core_seconds = models.FloatField(null=True)

    # Memory metrics
    pod_usage_memory_byte_seconds = models.FloatField(null=True)
    pod_request_memory_byte_seconds = models.FloatField(null=True)
    pod_effective_usage_memory_byte_seconds = models.FloatField(null=True)
    pod_limit_memory_byte_seconds = models.FloatField(null=True)

    # Node capacity
    node_capacity_cpu_cores = models.FloatField(null=True)
    node_capacity_cpu_core_seconds = models.FloatField(null=True)
    node_capacity_memory_bytes = models.FloatField(null=True)
    node_capacity_memory_byte_seconds = models.FloatField(null=True)


class OCPPodUsageLineItemDaily(OCPLineItemBase):
    """Model for openshift_pod_usage_line_items_daily table (aggregated daily data)."""

    class Meta:
        db_table = "openshift_pod_usage_line_items_daily"
        indexes = [
            models.Index(fields=["source", "year", "month"], name="ocp_pod_daily_src_yr_mo_idx"),
        ]

    # Pod identification
    pod = models.CharField(max_length=253, null=True)
    namespace = models.CharField(max_length=253, null=True)
    node = models.CharField(max_length=253, null=True)
    resource_id = models.CharField(max_length=256, null=True)
    pod_labels = models.TextField(null=True)
    node_role = models.CharField(max_length=64, null=True)

    # CPU metrics
    pod_usage_cpu_core_seconds = models.FloatField(null=True)
    pod_request_cpu_core_seconds = models.FloatField(null=True)
    pod_effective_usage_cpu_core_seconds = models.FloatField(null=True)
    pod_limit_cpu_core_seconds = models.FloatField(null=True)

    # Memory metrics
    pod_usage_memory_byte_seconds = models.FloatField(null=True)
    pod_request_memory_byte_seconds = models.FloatField(null=True)
    pod_effective_usage_memory_byte_seconds = models.FloatField(null=True)
    pod_limit_memory_byte_seconds = models.FloatField(null=True)

    # Node capacity
    node_capacity_cpu_cores = models.FloatField(null=True)
    node_capacity_cpu_core_seconds = models.FloatField(null=True)
    node_capacity_memory_bytes = models.FloatField(null=True)
    node_capacity_memory_byte_seconds = models.FloatField(null=True)


class OCPStorageUsageLineItem(OCPLineItemBase):
    """Model for openshift_storage_usage_line_items table."""

    class Meta:
        db_table = "openshift_storage_usage_line_items"
        indexes = [
            models.Index(fields=["source", "year", "month"], name="ocp_storage_src_yr_mo_idx"),
        ]

    # Storage identification
    namespace = models.CharField(max_length=253, null=True)
    pod = models.CharField(max_length=253, null=True)
    node = models.CharField(max_length=253, null=True)
    persistentvolumeclaim = models.CharField(max_length=253, null=True)
    persistentvolume = models.CharField(max_length=253, null=True)
    storageclass = models.CharField(max_length=253, null=True)
    csi_driver = models.CharField(max_length=256, null=True)
    csi_volume_handle = models.CharField(max_length=256, null=True)

    # Storage metrics
    persistentvolumeclaim_capacity_bytes = models.FloatField(null=True)
    persistentvolumeclaim_capacity_byte_seconds = models.FloatField(null=True)
    volume_request_storage_byte_seconds = models.FloatField(null=True)
    persistentvolumeclaim_usage_byte_seconds = models.FloatField(null=True)

    # Labels
    persistentvolume_labels = models.TextField(null=True)
    persistentvolumeclaim_labels = models.TextField(null=True)


class OCPStorageUsageLineItemDaily(OCPLineItemBase):
    """Model for openshift_storage_usage_line_items_daily table."""

    class Meta:
        db_table = "openshift_storage_usage_line_items_daily"
        indexes = [
            models.Index(fields=["source", "year", "month"], name="ocp_stor_daily_src_yr_mo_idx"),
        ]

    # Storage identification
    namespace = models.CharField(max_length=253, null=True)
    pod = models.CharField(max_length=253, null=True)
    node = models.CharField(max_length=253, null=True)
    persistentvolumeclaim = models.CharField(max_length=253, null=True)
    persistentvolume = models.CharField(max_length=253, null=True)
    storageclass = models.CharField(max_length=253, null=True)
    csi_driver = models.CharField(max_length=256, null=True)
    csi_volume_handle = models.CharField(max_length=256, null=True)

    # Storage metrics
    persistentvolumeclaim_capacity_bytes = models.FloatField(null=True)
    persistentvolumeclaim_capacity_byte_seconds = models.FloatField(null=True)
    volume_request_storage_byte_seconds = models.FloatField(null=True)
    persistentvolumeclaim_usage_byte_seconds = models.FloatField(null=True)

    # Labels
    persistentvolume_labels = models.TextField(null=True)
    persistentvolumeclaim_labels = models.TextField(null=True)


class OCPNodeLabelsLineItem(OCPLineItemBase):
    """Model for openshift_node_labels_line_items table."""

    class Meta:
        db_table = "openshift_node_labels_line_items"
        indexes = [
            models.Index(fields=["source", "year", "month"], name="ocp_node_lbl_src_yr_mo_idx"),
        ]

    node = models.CharField(max_length=253, null=True)
    node_labels = models.TextField(null=True)


class OCPNodeLabelsLineItemDaily(OCPLineItemBase):
    """Model for openshift_node_labels_line_items_daily table."""

    class Meta:
        db_table = "openshift_node_labels_line_items_daily"
        indexes = [
            models.Index(fields=["source", "year", "month"], name="ocp_node_lbl_dy_src_yr_mo_idx"),
        ]

    node = models.CharField(max_length=253, null=True)
    node_labels = models.TextField(null=True)


class OCPNamespaceLabelsLineItem(OCPLineItemBase):
    """Model for openshift_namespace_labels_line_items table."""

    class Meta:
        db_table = "openshift_namespace_labels_line_items"
        indexes = [
            models.Index(fields=["source", "year", "month"], name="ocp_ns_lbl_src_yr_mo_idx"),
        ]

    namespace = models.CharField(max_length=253, null=True)
    namespace_labels = models.TextField(null=True)


class OCPNamespaceLabelsLineItemDaily(OCPLineItemBase):
    """Model for openshift_namespace_labels_line_items_daily table."""

    class Meta:
        db_table = "openshift_namespace_labels_line_items_daily"
        indexes = [
            models.Index(fields=["source", "year", "month"], name="ocp_ns_lbl_dy_src_yr_mo_idx"),
        ]

    namespace = models.CharField(max_length=253, null=True)
    namespace_labels = models.TextField(null=True)


class OCPVMUsageLineItem(OCPLineItemBase):
    """Model for openshift_vm_usage_line_items table."""

    class Meta:
        db_table = "openshift_vm_usage_line_items"
        indexes = [
            models.Index(fields=["source", "year", "month"], name="ocp_vm_src_yr_mo_idx"),
        ]

    # VM identification
    node = models.CharField(max_length=253, null=True)
    namespace = models.CharField(max_length=253, null=True)
    vm_name = models.CharField(max_length=253, null=True)
    resource_id = models.CharField(max_length=256, null=True)
    vm_instance_type = models.CharField(max_length=256, null=True)
    vm_os = models.CharField(max_length=256, null=True)
    vm_guest_os_arch = models.CharField(max_length=64, null=True)
    vm_guest_os_name = models.CharField(max_length=256, null=True)
    vm_guest_os_version = models.CharField(max_length=256, null=True)
    vm_labels = models.TextField(null=True)

    # VM CPU metrics
    vm_uptime_total_seconds = models.FloatField(null=True)
    vm_cpu_limit_cores = models.FloatField(null=True)
    vm_cpu_limit_core_seconds = models.FloatField(null=True)
    vm_cpu_request_cores = models.FloatField(null=True)
    vm_cpu_request_core_seconds = models.FloatField(null=True)
    vm_cpu_request_sockets = models.FloatField(null=True)
    vm_cpu_request_socket_seconds = models.FloatField(null=True)
    vm_cpu_request_threads = models.FloatField(null=True)
    vm_cpu_request_thread_seconds = models.FloatField(null=True)
    vm_cpu_usage_total_seconds = models.FloatField(null=True)

    # VM memory metrics
    vm_memory_limit_bytes = models.FloatField(null=True)
    vm_memory_limit_byte_seconds = models.FloatField(null=True)
    vm_memory_request_bytes = models.FloatField(null=True)
    vm_memory_request_byte_seconds = models.FloatField(null=True)
    vm_memory_usage_byte_seconds = models.FloatField(null=True)

    # VM disk metrics
    vm_device = models.CharField(max_length=256, null=True)
    vm_volume_mode = models.CharField(max_length=64, null=True)
    vm_persistentvolumeclaim_name = models.CharField(max_length=253, null=True)
    vm_disk_allocated_size_byte_seconds = models.FloatField(null=True)


class OCPVMUsageLineItemDaily(OCPLineItemBase):
    """Model for openshift_vm_usage_line_items_daily table."""

    class Meta:
        db_table = "openshift_vm_usage_line_items_daily"
        indexes = [
            models.Index(fields=["source", "year", "month"], name="ocp_vm_daily_src_yr_mo_idx"),
        ]

    # VM identification
    node = models.CharField(max_length=253, null=True)
    namespace = models.CharField(max_length=253, null=True)
    vm_name = models.CharField(max_length=253, null=True)
    resource_id = models.CharField(max_length=256, null=True)
    vm_instance_type = models.CharField(max_length=256, null=True)
    vm_os = models.CharField(max_length=256, null=True)
    vm_guest_os_arch = models.CharField(max_length=64, null=True)
    vm_guest_os_name = models.CharField(max_length=256, null=True)
    vm_guest_os_version = models.CharField(max_length=256, null=True)
    vm_labels = models.TextField(null=True)

    # VM CPU metrics
    vm_uptime_total_seconds = models.FloatField(null=True)
    vm_cpu_limit_cores = models.FloatField(null=True)
    vm_cpu_limit_core_seconds = models.FloatField(null=True)
    vm_cpu_request_cores = models.FloatField(null=True)
    vm_cpu_request_core_seconds = models.FloatField(null=True)
    vm_cpu_request_sockets = models.FloatField(null=True)
    vm_cpu_request_socket_seconds = models.FloatField(null=True)
    vm_cpu_request_threads = models.FloatField(null=True)
    vm_cpu_request_thread_seconds = models.FloatField(null=True)
    vm_cpu_usage_total_seconds = models.FloatField(null=True)

    # VM memory metrics
    vm_memory_limit_bytes = models.FloatField(null=True)
    vm_memory_limit_byte_seconds = models.FloatField(null=True)
    vm_memory_request_bytes = models.FloatField(null=True)
    vm_memory_request_byte_seconds = models.FloatField(null=True)
    vm_memory_usage_byte_seconds = models.FloatField(null=True)

    # VM disk metrics
    vm_device = models.CharField(max_length=256, null=True)
    vm_volume_mode = models.CharField(max_length=64, null=True)
    vm_persistentvolumeclaim_name = models.CharField(max_length=253, null=True)
    vm_disk_allocated_size_byte_seconds = models.FloatField(null=True)


class OCPGPUUsageLineItem(OCPLineItemBase):
    """Model for openshift_gpu_usage_line_items table."""

    class Meta:
        db_table = "openshift_gpu_usage_line_items"
        indexes = [
            models.Index(fields=["source", "year", "month"], name="ocp_gpu_src_yr_mo_idx"),
        ]

    # GPU identification
    node = models.CharField(max_length=253, null=True)
    namespace = models.CharField(max_length=253, null=True)
    pod = models.CharField(max_length=253, null=True)
    gpu_uuid = models.CharField(max_length=256, null=True)
    gpu_model_name = models.CharField(max_length=256, null=True)
    gpu_vendor_name = models.CharField(max_length=256, null=True)

    # GPU metrics
    gpu_memory_capacity_mib = models.FloatField(null=True)
    gpu_pod_uptime = models.FloatField(null=True)


class OCPGPUUsageLineItemDaily(OCPLineItemBase):
    """Model for openshift_gpu_usage_line_items_daily table."""

    class Meta:
        db_table = "openshift_gpu_usage_line_items_daily"
        indexes = [
            models.Index(fields=["source", "year", "month"], name="ocp_gpu_daily_src_yr_mo_idx"),
        ]

    # GPU identification
    node = models.CharField(max_length=253, null=True)
    namespace = models.CharField(max_length=253, null=True)
    pod = models.CharField(max_length=253, null=True)
    gpu_uuid = models.CharField(max_length=256, null=True)
    gpu_model_name = models.CharField(max_length=256, null=True)
    gpu_vendor_name = models.CharField(max_length=256, null=True)

    # GPU metrics
    gpu_memory_capacity_mib = models.FloatField(null=True)
    gpu_pod_uptime = models.FloatField(null=True)


# Mapping from report type to Django model (for on-prem PostgreSQL)
OCP_LINE_ITEM_MODEL_MAP = {
    "pod_usage": OCPPodUsageLineItem,
    "storage_usage": OCPStorageUsageLineItem,
    "node_labels": OCPNodeLabelsLineItem,
    "namespace_labels": OCPNamespaceLabelsLineItem,
    "vm_usage": OCPVMUsageLineItem,
    "gpu_usage": OCPGPUUsageLineItem,
}

OCP_LINE_ITEM_DAILY_MODEL_MAP = {
    "pod_usage": OCPPodUsageLineItemDaily,
    "storage_usage": OCPStorageUsageLineItemDaily,
    "node_labels": OCPNodeLabelsLineItemDaily,
    "namespace_labels": OCPNamespaceLabelsLineItemDaily,
    "vm_usage": OCPVMUsageLineItemDaily,
    "gpu_usage": OCPGPUUsageLineItemDaily,
}
