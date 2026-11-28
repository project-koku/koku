#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for Events cost and usage entry tables."""
from uuid import uuid4

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import JSONField

UI_SUMMARY_TABLES = (
    "reporting_events_cost_summary_p",
    "reporting_events_cost_summary_by_tenant_p",
    "reporting_events_cost_summary_by_project_p",
    "reporting_events_cost_summary_by_service_p",
    "reporting_events_usage_summary_by_meter_p",
)


class EventsCostEntryBill(models.Model):
    """The billing information for a monthly Events billing period."""

    class Meta:
        """Meta for EventsCostEntryBill."""

        db_table = "reporting_eventscostentrybill"
        unique_together = ("billing_period_start", "provider")

    billing_period_start = models.DateTimeField()
    billing_period_end = models.DateTimeField()
    summary_data_creation_datetime = models.DateTimeField(null=True, blank=True)
    summary_data_updated_datetime = models.DateTimeField(null=True, blank=True)
    finalized_datetime = models.DateTimeField(null=True, blank=True)
    derived_cost_datetime = models.DateTimeField(null=True, blank=True)
    provider = models.ForeignKey("reporting.TenantAPIProvider", on_delete=models.CASCADE)


class EventsCostEntryLineItemDailySummary(models.Model):
    """A daily aggregation of pre-rated event cost entries from koku-events.

    Stores signed UTC-day rollups (negative usage/cost adjustments are preserved).
    Contents are replaced atomically per dirty usage_start date.
    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for EventsCostEntryLineItemDailySummary."""

        db_table = "reporting_eventscostentrylineitem_daily_summary"
        indexes = [
            models.Index(fields=["usage_start"], name="events_sum_usage_start_idx"),
            models.Index(fields=["usage_start", "source_uuid"], name="events_sum_start_src_idx"),
            models.Index(fields=["tenant_id"], name="events_sum_tenant_id_idx"),
            models.Index(fields=["project_id"], name="events_sum_project_id_idx"),
            models.Index(fields=["service"], name="events_sum_service_idx"),
            models.Index(fields=["meter"], name="events_sum_meter_idx"),
            models.Index(fields=["cluster_id"], name="events_sum_cluster_id_idx"),
            GinIndex(fields=["tags"], name="events_tags_idx"),
        ]

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    cost_entry_bill = models.ForeignKey(EventsCostEntryBill, on_delete=models.CASCADE)
    source_uuid = models.UUIDField(unique=False, null=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=True)

    # Attribution dimensions (OSAC-agnostic; optional fields nullable)
    tenant_id = models.CharField(max_length=256)
    tenant_name = models.CharField(max_length=256, null=True)
    project_id = models.CharField(max_length=256, null=True)
    project_name = models.CharField(max_length=256, null=True)
    user_id = models.CharField(max_length=256, null=True)
    service = models.CharField(max_length=256)
    meter = models.CharField(max_length=256)
    catalog_item = models.CharField(max_length=256, null=True)
    instance_type = models.CharField(max_length=128, null=True)
    resource_id = models.CharField(max_length=256, null=True)
    resource_name = models.CharField(max_length=256, null=True)
    cluster_id = models.CharField(max_length=256, null=True)
    deployment = models.CharField(max_length=128, null=True)
    cost_type = models.CharField(max_length=32, default="Infrastructure", db_default="Infrastructure")

    # Measures & currency (signed to preserve backdated billing corrections)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit = models.CharField(max_length=63, null=True)
    raw_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)
    currency = models.CharField(max_length=10)
    tags = JSONField(null=True)
    entry_count = models.BigIntegerField(null=True)


class EventsTagsSummary(models.Model):
    """A collection of all current existing tag keys and values for Events."""

    class Meta:
        """Meta for EventsTagsSummary."""

        db_table = "reporting_eventstags_summary"
        unique_together = ("key", "cost_entry_bill", "tenant_id", "project_id", "project_name")

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    key = models.TextField()
    values = ArrayField(models.TextField())
    cost_entry_bill = models.ForeignKey("EventsCostEntryBill", on_delete=models.CASCADE)
    tenant_id = models.TextField(null=True)
    project_id = models.TextField(null=True)
    project_name = models.TextField(null=True)


class EventsTagsValues(models.Model):
    """Distinct tag key/value pairs and associated Events tenants and projects."""

    class Meta:
        """Meta for EventsTagsValues."""

        db_table = "reporting_eventstags_values"
        unique_together = ("key", "value")
        indexes = [models.Index(fields=["key"], name="events_tags_val_key_idx")]

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    key = models.TextField()
    value = models.TextField()
    tenant_ids = ArrayField(models.TextField())
    project_ids = ArrayField(models.TextField(), null=True)
    project_names = ArrayField(models.TextField(), null=True)


# ======================================================
#  Partitioned UI Summary Tables
# ======================================================


class EventsCostSummaryP(models.Model):
    """Partitioned UI summary table for total daily Events cost."""

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for EventsCostSummaryP."""

        db_table = "reporting_events_cost_summary_p"
        indexes = [
            models.Index(fields=["usage_start"], name="evcostsumm_usage_start"),
            models.Index(fields=["usage_start", "source_uuid"], name="evcostsumm_start_src_idx"),
        ]

    id = models.UUIDField(primary_key=True, default=uuid4)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cost_type = models.CharField(max_length=32, default="Infrastructure", db_default="Infrastructure")
    raw_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class EventsCostSummaryByTenantP(models.Model):
    """Partitioned UI summary table for daily Events cost grouped by tenant."""

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for EventsCostSummaryByTenantP."""

        db_table = "reporting_events_cost_summary_by_tenant_p"
        indexes = [
            models.Index(fields=["usage_start"], name="evcostsumm_ten_usage_start"),
            models.Index(fields=["tenant_id"], name="evcostsumm_ten_tenant_id"),
            models.Index(fields=["usage_start", "source_uuid"], name="evcostsumm_ten_start_src"),
        ]

    id = models.UUIDField(primary_key=True, default=uuid4)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    tenant_id = models.CharField(max_length=256)
    tenant_name = models.CharField(max_length=256, null=True)
    cost_type = models.CharField(max_length=32, default="Infrastructure", db_default="Infrastructure")
    raw_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class EventsCostSummaryByProjectP(models.Model):
    """Partitioned UI summary table for daily Events cost grouped by project."""

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for EventsCostSummaryByProjectP."""

        db_table = "reporting_events_cost_summary_by_project_p"
        indexes = [
            models.Index(fields=["usage_start"], name="evcostsumm_pro_usage_start"),
            models.Index(fields=["tenant_id"], name="evcostsumm_pro_tenant_id"),
            models.Index(fields=["project_id"], name="evcostsumm_pro_project_id"),
            models.Index(fields=["usage_start", "source_uuid"], name="evcostsumm_pro_start_src"),
        ]

    id = models.UUIDField(primary_key=True, default=uuid4)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    tenant_id = models.CharField(max_length=256)
    project_id = models.CharField(max_length=256, null=True)
    project_name = models.CharField(max_length=256, null=True)
    cost_type = models.CharField(max_length=32, default="Infrastructure", db_default="Infrastructure")
    raw_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class EventsCostSummaryByServiceP(models.Model):
    """Partitioned UI summary table for daily Events cost grouped by service/deployment."""

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for EventsCostSummaryByServiceP."""

        db_table = "reporting_events_cost_summary_by_service_p"
        indexes = [
            models.Index(fields=["usage_start"], name="evcostsumm_ser_usage_start"),
            models.Index(fields=["service"], name="evcostsumm_ser_service"),
            models.Index(fields=["deployment"], name="evcostsumm_ser_deployment"),
            models.Index(fields=["usage_start", "source_uuid"], name="evcostsumm_ser_start_src"),
        ]

    id = models.UUIDField(primary_key=True, default=uuid4)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    tenant_id = models.CharField(max_length=256)
    project_id = models.CharField(max_length=256, null=True)
    service = models.CharField(max_length=256)
    deployment = models.CharField(max_length=128, null=True)
    cost_type = models.CharField(max_length=32, default="Infrastructure", db_default="Infrastructure")
    raw_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class EventsUsageSummaryByMeterP(models.Model):
    """Partitioned UI summary table for daily Events usage and cost grouped by meter."""

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for EventsUsageSummaryByMeterP."""

        db_table = "reporting_events_usage_summary_by_meter_p"
        indexes = [
            models.Index(fields=["usage_start"], name="evusagesumm_met_usage_start"),
            models.Index(fields=["service"], name="evusagesumm_met_service"),
            models.Index(fields=["meter"], name="evusagesumm_met_meter"),
            models.Index(fields=["instance_type"], name="evusagesumm_met_inst_type"),
            models.Index(fields=["usage_start", "source_uuid"], name="evusagesumm_met_start_src"),
        ]

    id = models.UUIDField(primary_key=True, default=uuid4)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    tenant_id = models.CharField(max_length=256)
    project_id = models.CharField(max_length=256, null=True)
    service = models.CharField(max_length=256)
    meter = models.CharField(max_length=256)
    instance_type = models.CharField(max_length=128, null=True)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit = models.CharField(max_length=63, null=True)
    cost_type = models.CharField(max_length=32, default="Infrastructure", db_default="Infrastructure")
    raw_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=30, decimal_places=15, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
