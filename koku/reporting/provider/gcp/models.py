#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for GCP cost and usage entry tables."""
from uuid import uuid4

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import JSONField

TRINO_LINE_ITEM_DAILY_TABLE = "gcp_line_items_daily"
TRINO_LINE_ITEM_TABLE = "gcp_line_items"
TRINO_OCP_ON_GCP_DAILY_TABLE = "gcp_openshift_daily"

UI_SUMMARY_TABLES = (
    "reporting_gcp_cost_summary_p",
    "reporting_gcp_cost_summary_by_account_p",
    "reporting_gcp_cost_summary_by_project_p",
    "reporting_gcp_cost_summary_by_region_p",
    "reporting_gcp_cost_summary_by_service_p",
    "reporting_gcp_compute_summary_p",
    "reporting_gcp_compute_summary_by_account_p",
    "reporting_gcp_storage_summary_p",
    "reporting_gcp_storage_summary_by_project_p",
    "reporting_gcp_storage_summary_by_service_p",
    "reporting_gcp_storage_summary_by_account_p",
    "reporting_gcp_storage_summary_by_region_p",
    "reporting_gcp_network_summary_p",
    "reporting_gcp_database_summary_p",
)


class GCPCostEntryBill(models.Model):
    """The billing information for a Cost Usage Report.

    The billing period (1 month) will cover many cost entries.

    """

    class Meta:
        """Meta for GCPCostEntryBill."""

        unique_together = ("billing_period_start", "provider")

    billing_period_start = models.DateTimeField()
    billing_period_end = models.DateTimeField()
    summary_data_creation_datetime = models.DateTimeField(null=True, blank=True)
    summary_data_updated_datetime = models.DateTimeField(null=True, blank=True)
    finalized_datetime = models.DateTimeField(null=True, blank=True)
    derived_cost_datetime = models.DateTimeField(null=True, blank=True)
    provider = models.ForeignKey("reporting.TenantAPIProvider", on_delete=models.CASCADE)


class GCPCostEntryLineItemDailySummary(models.Model):
    """A daily aggregation of line items.

    This table is aggregated by service, and does not
    have a breakdown by resource or tags. The contents of this table
    should be considered ephemeral. It will be regularly deleted from
    and repopulated.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for GCPCostEntryLineItemDailySummary."""

        db_table = "reporting_gcpcostentrylineitem_daily_summary"
        indexes = [
            models.Index(fields=["usage_start"], name="gcp_summary_usage_start_idx"),
            models.Index(fields=["instance_type"], name="gcp_summary_instance_type_idx"),
            GinIndex(fields=["tags"], name="gcp_tags_idx"),
            models.Index(fields=["project_id"], name="gcp_summary_project_id_idx"),
            models.Index(fields=["project_name"], name="gcp_summary_project_name_idx"),
            models.Index(fields=["service_id"], name="gcp_summary_service_id_idx"),
            models.Index(fields=["service_alias"], name="gcp_summary_service_alias_idx"),
        ]

    uuid = models.UUIDField(primary_key=True)

    cost_entry_bill = models.ForeignKey(GCPCostEntryBill, on_delete=models.CASCADE)
    # The following fields are used for grouping
    account_id = models.CharField(max_length=20)
    project_id = models.CharField(max_length=256)
    project_name = models.CharField(max_length=256)
    service_id = models.CharField(max_length=256, null=True)
    service_alias = models.CharField(max_length=256, null=True, blank=True)
    sku_id = models.CharField(max_length=256, null=True)
    sku_alias = models.CharField(max_length=256, null=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=True)
    region = models.CharField(max_length=50, null=True)
    instance_type = models.CharField(max_length=50, null=True)
    unit = models.CharField(max_length=63, null=True)
    line_item_type = models.CharField(max_length=256, null=True)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    invoice_month = models.CharField(max_length=256, null=True, blank=True)
    # The following fields are aggregates
    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    tags = JSONField(null=True)
    source_uuid = models.UUIDField(unique=False, null=True)
    credit_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True)


class GCPEnabledTagKeys(models.Model):
    """A collection of the current enabled tag keys."""

    class Meta:
        """Meta for GCPEnabledTagKeys."""

        db_table = "reporting_gcpenabledtagkeys"
        indexes = [models.Index(name="gcp_enabled_covering_ix", fields=["key", "enabled"])]

    id = models.BigAutoField(primary_key=True)
    key = models.CharField(max_length=253, unique=True)
    enabled = models.BooleanField(null=False, default=False)


class GCPTagsSummary(models.Model):
    """A collection of all current existing tag key and values."""

    class Meta:
        """Meta for GCPTagSummary."""

        db_table = "reporting_gcptags_summary"
        unique_together = ("key", "cost_entry_bill", "account_id", "project_id", "project_name")

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    key = models.TextField()
    values = ArrayField(models.TextField())
    cost_entry_bill = models.ForeignKey("GCPCostEntryBill", on_delete=models.CASCADE)
    account_id = models.TextField(null=True)
    project_id = models.TextField(null=True)
    project_name = models.TextField(null=True)


class GCPTagsValues(models.Model):
    class Meta:
        """Meta for GCPTagsValues."""

        db_table = "reporting_gcptags_values"
        unique_together = ("key", "value")
        indexes = [models.Index(fields=["key"], name="gcp_tags_value_key_idx")]

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    key = models.TextField()
    value = models.TextField()
    account_ids = ArrayField(models.TextField())
    project_ids = ArrayField(models.TextField(), null=True)
    project_names = ArrayField(models.TextField(), null=True)


class GCPTopology(models.Model):
    """GCPAccountTopology ORM model."""

    class Meta:
        """Meta for GCPAccountTopology."""

        db_table = "reporting_gcp_topology"

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    source_uuid = models.UUIDField(unique=False, null=True)
    account_id = models.TextField()
    project_id = models.TextField()
    project_name = models.TextField()
    service_id = models.TextField()
    service_alias = models.TextField()
    region = models.TextField()


# ======================================================
#  Partitioned Models to replace matviews
# ======================================================


class GCPCostSummaryP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for GCPCostSummaryP."""

        db_table = "reporting_gcp_cost_summary_p"
        indexes = [
            models.Index(fields=["usage_start"], name="gcpcostsumm_usage_start"),
            models.Index(fields=["invoice_month"], name="gcpcostsumm_invmonth"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    invoice_month = models.CharField(max_length=256, null=True, blank=True)
    credit_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True)


class GCPCostSummaryByAccountP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by account.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for GCPCostSummaryByAccountP."""

        db_table = "reporting_gcp_cost_summary_by_account_p"
        indexes = [
            models.Index(fields=["usage_start"], name="gcpcostsumm_acc_usage_start"),
            models.Index(fields=["account_id"], name="gcpcostsumm_acc_account_id"),
            models.Index(fields=["invoice_month"], name="gcpcostsumm_acc_invmonth"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    account_id = models.CharField(max_length=50, null=False)
    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    invoice_month = models.CharField(max_length=256, null=True, blank=True)
    credit_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True)


class GCPCostSummaryByProjectP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by account.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for GCPCostSummaryByProjectP."""

        db_table = "reporting_gcp_cost_summary_by_project_p"
        indexes = [
            models.Index(fields=["usage_start"], name="gcpcostsumm_pro_usage_start"),
            models.Index(fields=["project_id"], name="gcpcostsumm_pro_project_id"),
            models.Index(fields=["invoice_month"], name="gcpcostsumm_pro_invmonth"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    project_id = models.CharField(unique=False, max_length=256)
    project_name = models.CharField(max_length=256)
    account_id = models.CharField(max_length=50, null=False)
    invoice_month = models.CharField(max_length=256, null=True, blank=True)
    credit_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True)


class GCPCostSummaryByRegionP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by region.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for GCPCostSummaryByRegionP."""

        db_table = "reporting_gcp_cost_summary_by_region_p"
        indexes = [
            models.Index(fields=["usage_start"], name="gcpcostsumm_reg_usage_start"),
            models.Index(fields=["region"], name="gcpcostsumm_reg_region"),
            models.Index(fields=["invoice_month"], name="gcpcostsumm_reg_invmonth"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    account_id = models.CharField(max_length=50, null=False)
    region = models.CharField(max_length=50, null=True)
    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    invoice_month = models.CharField(max_length=256, null=True, blank=True)
    credit_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True)


class GCPCostSummaryByServiceP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by service.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for GCPCostSummaryByServiceP."""

        db_table = "reporting_gcp_cost_summary_by_service_p"
        indexes = [
            models.Index(fields=["usage_start"], name="gcpcostsumm_ser_usage_start"),
            models.Index(fields=["service_id"], name="gcpcostsumm_ser_service_id"),
            models.Index(fields=["invoice_month"], name="gcpcostsumm_ser_invmonth"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    account_id = models.CharField(max_length=50, null=False)
    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    service_id = models.CharField(max_length=256, null=True)
    service_alias = models.CharField(max_length=256, null=True, blank=True)
    invoice_month = models.CharField(max_length=256, null=True, blank=True)
    credit_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True)


class GCPComputeSummaryP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for GCPComputeSummaryP."""

        db_table = "reporting_gcp_compute_summary_p"
        indexes = [
            models.Index(fields=["usage_start"], name="gcpcompsumm_usage_start"),
            models.Index(fields=["instance_type"], name="gcpcompsumm_insttyp"),
            models.Index(fields=["invoice_month"], name="gcpcompsumm_invmonth"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    instance_type = models.CharField(max_length=50, null=True)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit = models.CharField(max_length=63, null=True)
    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    invoice_month = models.CharField(max_length=256, null=True, blank=True)
    credit_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True)


class GCPComputeSummaryByAccountP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by service and instance type.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for GCPComputeSummaryByAccountP."""

        db_table = "reporting_gcp_compute_summary_by_account_p"
        indexes = [
            models.Index(fields=["account_id"], name="gcpcompsumm_acc_account_id"),
            models.Index(fields=["usage_start"], name="gcpcompsumm_acc_usage_start"),
            models.Index(fields=["instance_type"], name="gcpcompsumm_acc_insttyp"),
            models.Index(fields=["invoice_month"], name="gcpcompsumm_acc_invmonth"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    instance_type = models.CharField(max_length=50, null=True)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit = models.CharField(max_length=63, null=True)
    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    account_id = models.CharField(max_length=50, null=False)
    invoice_month = models.CharField(max_length=256, null=True, blank=True)
    credit_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True)


class GCPStorageSummaryP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of storage usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for GCPStorageSummaryP."""

        db_table = "reporting_gcp_storage_summary_p"
        indexes = [
            models.Index(fields=["usage_start"], name="gcpstorsumm_usage_start"),
            models.Index(fields=["invoice_month"], name="gcpstorsumm_invmonth"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit = models.CharField(max_length=63, null=True)
    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    invoice_month = models.CharField(max_length=256, null=True, blank=True)
    credit_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True)


class GCPStorageSummaryByProjectP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by account.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for GCPStorageSummaryByProjectP."""

        db_table = "reporting_gcp_storage_summary_by_project_p"
        indexes = [
            models.Index(fields=["usage_start"], name="gcpstorsumm_pro_usage_start"),
            models.Index(fields=["project_id"], name="gcpstorsumm_pro_project_id"),
            models.Index(fields=["account_id"], name="gcpstorsumm_pro_account_id"),
            models.Index(fields=["invoice_month"], name="gcpstorsumm_pro_invmonth"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit = models.CharField(max_length=63, null=True)
    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    project_id = models.CharField(unique=False, max_length=256)
    project_name = models.CharField(max_length=256)
    account_id = models.CharField(max_length=50, null=False)
    invoice_month = models.CharField(max_length=256, null=True, blank=True)
    credit_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True)


class GCPStorageSummaryByServiceP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of compute usage by service and instance type.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for GCPStorageSummaryByServiceP."""

        db_table = "reporting_gcp_storage_summary_by_service_p"
        indexes = [
            models.Index(fields=["usage_start"], name="gcpstorsumm_ser_usage_start"),
            models.Index(fields=["service_id"], name="gcpstorsumm_ser_service_id"),
            models.Index(fields=["account_id"], name="gcpstorsumm_ser_account_id"),
            models.Index(fields=["invoice_month"], name="gcpstorsumm_ser_invmonth"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit = models.CharField(max_length=63, null=True)
    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    service_id = models.CharField(max_length=256, null=True)
    service_alias = models.CharField(max_length=256, null=True, blank=True)
    account_id = models.CharField(max_length=50, null=False)
    invoice_month = models.CharField(max_length=256, null=True, blank=True)
    credit_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True)


class GCPStorageSummaryByAccountP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by service and instance type.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for GCPStorageSummaryByAccountP."""

        db_table = "reporting_gcp_storage_summary_by_account_p"
        indexes = [
            models.Index(fields=["usage_start"], name="gcpstorsumm_acc_usage_start"),
            models.Index(fields=["account_id"], name="gcpstorsumm_acc_account_id"),
            models.Index(fields=["invoice_month"], name="gcpstorsumm_acc_invmonth"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit = models.CharField(max_length=63, null=True)
    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    account_id = models.CharField(max_length=50, null=False)
    invoice_month = models.CharField(max_length=256, null=True, blank=True)
    credit_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True)


class GCPStorageSummaryByRegionP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by service and instance type.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for GCPStorageSummaryByRegionP."""

        db_table = "reporting_gcp_storage_summary_by_region_p"
        indexes = [
            models.Index(fields=["usage_start"], name="gcpstorsumm_reg_usage_start"),
            models.Index(fields=["account_id"], name="gcpstorsumm_reg_account_id"),
            models.Index(fields=["invoice_month"], name="gcpstorsumm_reg_invmonth"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit = models.CharField(max_length=63, null=True)
    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    account_id = models.CharField(max_length=50, null=False)
    region = models.CharField(max_length=50, null=True)
    invoice_month = models.CharField(max_length=256, null=True, blank=True)
    credit_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True)


class GCPNetworkSummaryP(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of network usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for GCPNetworkSummaryP."""

        db_table = "reporting_gcp_network_summary_p"
        indexes = [
            models.Index(fields=["usage_start"], name="gcpnetsumm_usage_start"),
            models.Index(fields=["invoice_month"], name="gcpnetsumm_invmonth"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    account_id = models.CharField(max_length=50, null=False)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit = models.CharField(max_length=63, null=True)
    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    service_id = models.CharField(max_length=256, null=True)
    service_alias = models.CharField(max_length=256, null=True, blank=True)
    invoice_month = models.CharField(max_length=256, null=True, blank=True)
    credit_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True)


class GCPDatabaseSummaryP(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of database usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for GCPDatabaseSummaryP."""

        db_table = "reporting_gcp_database_summary_p"
        indexes = [
            models.Index(fields=["usage_start"], name="gcpdbsumm_usage_start"),
            models.Index(fields=["invoice_month"], name="gcpdbsumm_invmonth"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    account_id = models.CharField(max_length=50, null=False)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit = models.CharField(max_length=63, null=True)
    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
    service_id = models.CharField(max_length=256, null=True)
    service_alias = models.CharField(max_length=256, null=True, blank=True)
    invoice_month = models.CharField(max_length=256, null=True, blank=True)
    credit_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True)
