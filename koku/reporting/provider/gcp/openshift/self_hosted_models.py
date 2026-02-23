#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Django models for GCP OpenShift managed tables (on-prem PostgreSQL)."""
from django.db import models


class ManagedGCPOpenShiftDaily(models.Model):
    class Meta:
        db_table = "managed_gcp_openshift_daily_temp"
        indexes = [
            models.Index(fields=["ocp_source", "source", "year", "month"], name="gcp_daily_tmp_src_yr_mo_idx"),
            models.Index(fields=["day"], name="gcp_daily_tmp_day_idx"),
        ]

    row_uuid = models.CharField(max_length=256, null=True)
    invoice_month = models.CharField(max_length=256, null=True)
    account_id = models.CharField(max_length=256, null=True)
    project_id = models.CharField(max_length=256, null=True)
    usage_start = models.DateTimeField(null=True)
    data_transfer_direction = models.CharField(max_length=256, null=True)
    service_id = models.CharField(max_length=256, null=True)
    sku_id = models.CharField(max_length=256, null=True)
    system_labels = models.TextField(null=True)
    labels = models.TextField(null=True)
    cost_type = models.CharField(max_length=256, null=True)
    region = models.CharField(max_length=256, null=True)
    resource_name = models.CharField(max_length=256, null=True)
    instance_type = models.CharField(max_length=256, null=True)
    project_name = models.CharField(max_length=256, null=True)
    service_description = models.CharField(max_length=256, null=True)
    service_alias = models.CharField(max_length=256, null=True)
    sku_description = models.CharField(max_length=256, null=True)
    sku_alias = models.CharField(max_length=256, null=True)
    unit = models.CharField(max_length=256, null=True)
    usage_amount = models.FloatField(null=True)
    currency = models.CharField(max_length=256, null=True)
    unblended_cost = models.FloatField(null=True)
    credit_amount = models.FloatField(null=True)
    resource_global_name = models.CharField(max_length=256, null=True)
    resource_id_matched = models.BooleanField(null=True)
    matched_tag = models.CharField(max_length=256, null=True)
    ocp_source = models.CharField(max_length=256, null=True)
    source = models.CharField(max_length=256, null=True)
    year = models.CharField(max_length=4, null=True)
    month = models.CharField(max_length=2, null=True)
    day = models.CharField(max_length=2, null=True)


class ManagedOCPGCPCostLineItemProjectDailySummaryTemp(models.Model):
    class Meta:
        db_table = "managed_reporting_ocpgcpcostlineitem_project_daily_summary_temp"
        indexes = [
            models.Index(fields=["source", "ocp_source", "year", "month"], name="gcp_summ_tmp_src_yr_mo_idx"),
        ]

    row_uuid = models.CharField(max_length=256, null=True)
    cluster_id = models.CharField(max_length=256, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    data_source = models.CharField(max_length=256, null=True)
    namespace = models.CharField(max_length=256, null=True)
    node = models.CharField(max_length=256, null=True)
    persistentvolumeclaim = models.CharField(max_length=256, null=True)
    persistentvolume = models.CharField(max_length=256, null=True)
    storageclass = models.CharField(max_length=256, null=True)
    pod_labels = models.TextField(null=True)
    resource_name = models.CharField(max_length=256, null=True)
    resource_id = models.CharField(max_length=256, null=True)
    usage_start = models.DateTimeField(null=True)
    usage_end = models.DateTimeField(null=True)
    account_id = models.CharField(max_length=256, null=True)
    project_id = models.CharField(max_length=256, null=True)
    project_name = models.CharField(max_length=256, null=True)
    instance_type = models.CharField(max_length=256, null=True)
    service_id = models.CharField(max_length=256, null=True)
    service_alias = models.CharField(max_length=256, null=True)
    sku_id = models.CharField(max_length=256, null=True)
    sku_alias = models.CharField(max_length=256, null=True)
    region = models.CharField(max_length=256, null=True)
    unit = models.CharField(max_length=256, null=True)
    usage_amount = models.FloatField(null=True)
    currency = models.CharField(max_length=256, null=True)
    invoice_month = models.CharField(max_length=256, null=True)
    credit_amount = models.FloatField(null=True)
    unblended_cost = models.FloatField(null=True)
    markup_cost = models.FloatField(null=True)
    project_markup_cost = models.FloatField(null=True)
    pod_cost = models.FloatField(null=True)
    pod_credit = models.FloatField(null=True)
    pod_effective_usage_cpu_core_hours = models.FloatField(null=True)
    pod_effective_usage_memory_gigabyte_hours = models.FloatField(null=True)
    node_capacity_cpu_core_hours = models.FloatField(null=True)
    node_capacity_memory_gigabyte_hours = models.FloatField(null=True)
    volume_labels = models.TextField(null=True)
    tags = models.TextField(null=True)
    cost_category_id = models.IntegerField(null=True)
    project_rank = models.IntegerField(null=True)
    data_source_rank = models.IntegerField(null=True)
    resource_id_matched = models.BooleanField(null=True)
    matched_tag = models.CharField(max_length=256, null=True)
    source = models.CharField(max_length=256, null=True)
    ocp_source = models.CharField(max_length=256, null=True)
    year = models.CharField(max_length=4, null=True)
    month = models.CharField(max_length=2, null=True)


class ManagedOCPGCPCostLineItemProjectDailySummary(models.Model):
    class Meta:
        db_table = "managed_reporting_ocpgcpcostlineitem_project_daily_summary"
        indexes = [
            models.Index(fields=["source", "ocp_source", "year", "month"], name="gcp_summ_src_yr_mo_idx"),
            models.Index(fields=["day"], name="gcp_summ_day_idx"),
            models.Index(fields=["usage_start"], name="gcp_summ_usage_start_idx"),
        ]

    row_uuid = models.CharField(max_length=256, null=True)
    cluster_id = models.CharField(max_length=256, null=True)
    cluster_alias = models.CharField(max_length=256, null=True)
    data_source = models.CharField(max_length=256, null=True)
    namespace = models.CharField(max_length=256, null=True)
    node = models.CharField(max_length=256, null=True)
    persistentvolumeclaim = models.CharField(max_length=256, null=True)
    persistentvolume = models.CharField(max_length=256, null=True)
    storageclass = models.CharField(max_length=256, null=True)
    pod_labels = models.TextField(null=True)
    resource_id = models.CharField(max_length=256, null=True)
    usage_start = models.DateTimeField(null=True)
    usage_end = models.DateTimeField(null=True)
    account_id = models.CharField(max_length=256, null=True)
    project_id = models.CharField(max_length=256, null=True)
    project_name = models.CharField(max_length=256, null=True)
    instance_type = models.CharField(max_length=256, null=True)
    service_id = models.CharField(max_length=256, null=True)
    service_alias = models.CharField(max_length=256, null=True)
    data_transfer_direction = models.CharField(max_length=256, null=True)
    sku_id = models.CharField(max_length=256, null=True)
    sku_alias = models.CharField(max_length=256, null=True)
    region = models.CharField(max_length=256, null=True)
    unit = models.CharField(max_length=256, null=True)
    usage_amount = models.FloatField(null=True)
    currency = models.CharField(max_length=256, null=True)
    invoice_month = models.CharField(max_length=256, null=True)
    credit_amount = models.FloatField(null=True)
    unblended_cost = models.FloatField(null=True)
    markup_cost = models.FloatField(null=True)
    project_markup_cost = models.FloatField(null=True)
    pod_cost = models.FloatField(null=True)
    pod_credit = models.FloatField(null=True)
    node_capacity_cpu_core_hours = models.FloatField(null=True)
    node_capacity_memory_gigabyte_hours = models.FloatField(null=True)
    volume_labels = models.TextField(null=True)
    tags = models.TextField(null=True)
    cost_category_id = models.IntegerField(null=True)
    project_rank = models.IntegerField(null=True)
    data_source_rank = models.IntegerField(null=True)
    resource_id_matched = models.BooleanField(null=True)
    matched_tag = models.CharField(max_length=256, null=True)
    source = models.CharField(max_length=256, null=True)
    ocp_source = models.CharField(max_length=256, null=True)
    year = models.CharField(max_length=4, null=True)
    month = models.CharField(max_length=2, null=True)
    day = models.CharField(max_length=2, null=True)


class ManagedGCPOpenShiftDiskCapacities(models.Model):
    class Meta:
        db_table = "managed_gcp_openshift_disk_capacities_temp"
        indexes = [
            models.Index(fields=["source", "ocp_source", "year", "month"], name="gcp_disk_cap_src_yr_mo_idx"),
        ]

    resource_global_name = models.CharField(max_length=256, null=True)
    resource_name = models.CharField(max_length=256, null=True)
    capacity = models.IntegerField(null=True)
    source = models.CharField(max_length=256, null=True)
    ocp_source = models.CharField(max_length=256, null=True)
    year = models.CharField(max_length=4, null=True)
    month = models.CharField(max_length=2, null=True)
