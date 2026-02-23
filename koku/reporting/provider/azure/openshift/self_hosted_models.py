#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Django models for Azure OpenShift managed tables (on-prem PostgreSQL)."""
from django.db import models


class ManagedAzureOpenShiftDaily(models.Model):
    class Meta:
        db_table = "managed_azure_openshift_daily_temp"
        indexes = [
            models.Index(fields=["source", "ocp_source", "year", "month"], name="azure_daily_tmp_src_yr_mo_idx"),
            models.Index(fields=["day"], name="azure_daily_tmp_day_idx"),
        ]

    row_uuid = models.CharField(max_length=256, null=True)
    usage_start = models.DateTimeField(null=True)
    resource_id = models.CharField(max_length=256, null=True)
    service_name = models.CharField(max_length=256, null=True)
    data_transfer_direction = models.CharField(max_length=256, null=True)
    instance_type = models.CharField(max_length=256, null=True)
    subscription_guid = models.CharField(max_length=256, null=True)
    subscription_name = models.CharField(max_length=256, null=True)
    resource_location = models.CharField(max_length=256, null=True)
    unit_of_measure = models.CharField(max_length=256, null=True)
    usage_quantity = models.FloatField(null=True)
    currency = models.CharField(max_length=256, null=True)
    pretax_cost = models.FloatField(null=True)
    date = models.DateTimeField(null=True)
    metername = models.CharField(max_length=256, null=True)
    complete_resource_id = models.CharField(max_length=256, null=True)
    tags = models.TextField(null=True)
    resource_id_matched = models.BooleanField(null=True)
    matched_tag = models.CharField(max_length=256, null=True)
    source = models.CharField(max_length=256, null=True)
    ocp_source = models.CharField(max_length=256, null=True)
    year = models.CharField(max_length=4, null=True)
    month = models.CharField(max_length=2, null=True)
    day = models.CharField(max_length=2, null=True)


class ManagedOCPAzureCostLineItemProjectDailySummaryTemp(models.Model):
    class Meta:
        db_table = "managed_reporting_ocpazurecostlineitem_project_daily_summary_temp"
        indexes = [
            models.Index(fields=["source", "ocp_source", "year", "month"], name="azure_summ_tmp_src_yr_mo_idx"),
            models.Index(fields=["day"], name="azure_summ_tmp_day_idx"),
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
    resource_id = models.CharField(max_length=256, null=True)
    usage_start = models.DateTimeField(null=True)
    usage_end = models.DateTimeField(null=True)
    service_name = models.CharField(max_length=256, null=True)
    data_transfer_direction = models.CharField(max_length=256, null=True)
    instance_type = models.CharField(max_length=256, null=True)
    subscription_guid = models.CharField(max_length=256, null=True)
    subscription_name = models.CharField(max_length=256, null=True)
    resource_location = models.CharField(max_length=256, null=True)
    unit_of_measure = models.CharField(max_length=256, null=True)
    usage_quantity = models.FloatField(null=True)
    currency = models.CharField(max_length=256, null=True)
    pretax_cost = models.FloatField(null=True)
    markup_cost = models.FloatField(null=True)
    pod_cost = models.FloatField(null=True)
    project_markup_cost = models.FloatField(null=True)
    pod_effective_usage_cpu_core_hours = models.FloatField(null=True)
    pod_effective_usage_memory_gigabyte_hours = models.FloatField(null=True)
    node_capacity_cpu_core_hours = models.FloatField(null=True)
    node_capacity_memory_gigabyte_hours = models.FloatField(null=True)
    pod_labels = models.TextField(null=True)
    volume_labels = models.TextField(null=True)
    tags = models.TextField(null=True)
    project_rank = models.IntegerField(null=True)
    data_source_rank = models.IntegerField(null=True)
    matched_tag = models.CharField(max_length=256, null=True)
    resource_id_matched = models.BooleanField(null=True)
    cost_category_id = models.IntegerField(null=True)
    source = models.CharField(max_length=256, null=True)
    ocp_source = models.CharField(max_length=256, null=True)
    year = models.CharField(max_length=4, null=True)
    month = models.CharField(max_length=2, null=True)
    day = models.CharField(max_length=2, null=True)


class ManagedOCPAzureCostLineItemProjectDailySummary(models.Model):
    class Meta:
        db_table = "managed_reporting_ocpazurecostlineitem_project_daily_summary"
        indexes = [
            models.Index(fields=["source", "ocp_source", "year", "month"], name="azure_summ_src_yr_mo_idx"),
            models.Index(fields=["day"], name="azure_summ_day_idx"),
            models.Index(fields=["usage_start"], name="azure_summ_usage_start_idx"),
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
    resource_id = models.CharField(max_length=256, null=True)
    usage_start = models.DateTimeField(null=True)
    usage_end = models.DateTimeField(null=True)
    service_name = models.CharField(max_length=256, null=True)
    data_transfer_direction = models.CharField(max_length=256, null=True)
    instance_type = models.CharField(max_length=256, null=True)
    subscription_guid = models.CharField(max_length=256, null=True)
    subscription_name = models.CharField(max_length=256, null=True)
    resource_location = models.CharField(max_length=256, null=True)
    unit_of_measure = models.CharField(max_length=256, null=True)
    usage_quantity = models.FloatField(null=True)
    currency = models.CharField(max_length=256, null=True)
    pretax_cost = models.FloatField(null=True)
    markup_cost = models.FloatField(null=True)
    pod_cost = models.FloatField(null=True)
    project_markup_cost = models.FloatField(null=True)
    pod_effective_usage_cpu_core_hours = models.FloatField(null=True)
    pod_effective_usage_memory_gigabyte_hours = models.FloatField(null=True)
    node_capacity_cpu_core_hours = models.FloatField(null=True)
    node_capacity_memory_gigabyte_hours = models.FloatField(null=True)
    pod_labels = models.TextField(null=True)
    volume_labels = models.TextField(null=True)
    tags = models.TextField(null=True)
    project_rank = models.IntegerField(null=True)
    data_source_rank = models.IntegerField(null=True)
    matched_tag = models.CharField(max_length=256, null=True)
    resource_id_matched = models.BooleanField(null=True)
    cost_category_id = models.IntegerField(null=True)
    source = models.CharField(max_length=256, null=True)
    ocp_source = models.CharField(max_length=256, null=True)
    year = models.CharField(max_length=4, null=True)
    month = models.CharField(max_length=2, null=True)
    day = models.CharField(max_length=2, null=True)


class ManagedAzureOpenShiftDiskCapacities(models.Model):
    class Meta:
        db_table = "managed_azure_openshift_disk_capacities_temp"
        indexes = [
            models.Index(fields=["ocp_source", "year", "month"], name="azure_disk_cap_src_yr_mo_idx"),
        ]

    resource_id = models.CharField(max_length=256, null=True)
    capacity = models.IntegerField(null=True)
    usage_start = models.DateTimeField(null=True)
    ocp_source = models.CharField(max_length=256, null=True)
    year = models.CharField(max_length=4, null=True)
    month = models.CharField(max_length=2, null=True)
