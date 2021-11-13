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

VIEWS = (
    "reporting_gcp_cost_summary",
    "reporting_gcp_cost_summary_by_project",
    "reporting_gcp_cost_summary_by_region",
    "reporting_gcp_cost_summary_by_service",
    "reporting_gcp_cost_summary_by_account",
    "reporting_gcp_compute_summary",
    "reporting_gcp_compute_summary_by_project",
    "reporting_gcp_compute_summary_by_region",
    "reporting_gcp_compute_summary_by_service",
    "reporting_gcp_compute_summary_by_account",
    "reporting_gcp_storage_summary",
    "reporting_gcp_storage_summary_by_project",
    "reporting_gcp_storage_summary_by_region",
    "reporting_gcp_storage_summary_by_service",
    "reporting_gcp_storage_summary_by_account",
    "reporting_gcp_network_summary",
    "reporting_gcp_database_summary",
)


PRESTO_LINE_ITEM_TABLE = "gcp_line_items"


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
    provider = models.ForeignKey("api.Provider", on_delete=models.CASCADE)


class GCPProject(models.Model):
    """The per Project information for GCP."""

    account_id = models.CharField(max_length=20)
    project_id = models.CharField(unique=True, max_length=256)
    project_name = models.CharField(max_length=256)
    project_labels = models.CharField(max_length=256, null=True, blank=True)


class GCPCostEntryProductService(models.Model):
    """The product service and sku information."""

    class Meta:
        """Meta for GCPCostEntryProductService."""

        unique_together = ("service_id", "service_alias", "sku_id", "sku_alias")
        db_table = "reporting_gcpcostentryproductservice"

    id = models.BigAutoField(primary_key=True)
    service_id = models.CharField(max_length=256, null=True)
    service_alias = models.CharField(max_length=256, null=True, blank=True)
    sku_id = models.CharField(max_length=256, null=True)
    sku_alias = models.CharField(max_length=256, null=True)


class GCPCostEntryLineItem(models.Model):
    """GCP cost entry daily line item."""

    class Meta:
        """Meta for GCPCostEntryLineItem."""

        db_table = "reporting_gcpcostentrylineitem"

    id = models.BigAutoField(primary_key=True)
    usage_start = models.DateTimeField()
    usage_end = models.DateTimeField()
    partition_date = models.DateTimeField(null=True)
    tags = JSONField(null=True)
    usage_type = models.CharField(max_length=50, null=True)
    location = models.CharField(max_length=256, null=True, blank=True)
    country = models.CharField(max_length=256, null=True, blank=True)
    region = models.CharField(max_length=256, null=True, blank=True)
    zone = models.CharField(max_length=256, null=True, blank=True)
    export_time = models.CharField(max_length=256, null=True, blank=True)
    cost = models.DecimalField(max_digits=33, decimal_places=15, null=True, blank=True)
    currency = models.CharField(max_length=256, null=True, blank=True)
    conversion_rate = models.CharField(max_length=256, null=True, blank=True)
    usage_to_pricing_units = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    usage_pricing_unit = models.CharField(max_length=256, null=True, blank=True)
    credits = models.CharField(max_length=256, null=True, blank=True)
    invoice_month = models.CharField(max_length=256, null=True, blank=True)
    cost_type = models.CharField(max_length=256, null=True, blank=True)
    line_item_type = models.CharField(max_length=256, null=True)
    cost_entry_product = models.ForeignKey(
        GCPCostEntryProductService, null=True, on_delete=models.CASCADE, db_constraint=False
    )
    cost_entry_bill = models.ForeignKey(GCPCostEntryBill, on_delete=models.CASCADE, db_constraint=False)
    project = models.ForeignKey(GCPProject, on_delete=models.CASCADE, db_constraint=False)


class GCPCostEntryLineItemDaily(models.Model):
    """GCP cost entry daily line item."""

    class Meta:
        """Meta for GCPCostEntryLineItem."""

        db_table = "reporting_gcpcostentrylineitem_daily"
        indexes = [
            models.Index(fields=["usage_start"], name="gcp_usage_start_idx"),
            GinIndex(fields=["tags"], name="gcp_cost_entry"),
        ]

    id = models.BigAutoField(primary_key=True)

    cost_entry_bill = models.ForeignKey(GCPCostEntryBill, on_delete=models.CASCADE)
    cost_entry_product = models.ForeignKey(GCPCostEntryProductService, null=True, on_delete=models.CASCADE)
    project = models.ForeignKey(GCPProject, on_delete=models.CASCADE)

    line_item_type = models.CharField(max_length=256, null=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=True)
    tags = JSONField(null=True)
    usage_type = models.CharField(max_length=50, null=True)
    region = models.CharField(max_length=256, null=True, blank=True)
    cost = models.DecimalField(max_digits=33, decimal_places=15, null=True, blank=True)
    currency = models.CharField(max_length=256, null=True, blank=True)
    conversion_rate = models.CharField(max_length=256, null=True, blank=True)
    usage_in_pricing_units = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    usage_pricing_unit = models.CharField(max_length=256, null=True, blank=True)
    invoice_month = models.CharField(max_length=256, null=True, blank=True)
    tax_type = models.CharField(max_length=256, null=True, blank=True)
    credit_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True, blank=True)


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
    usage_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    currency = models.CharField(max_length=10)
    invoice_month = models.CharField(max_length=256, null=True, blank=True)

    # The following fields are aggregates
    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    tags = JSONField(null=True)
    source_uuid = models.UUIDField(unique=False, null=True)
    credit_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True, blank=True)


class GCPEnabledTagKeys(models.Model):
    """A collection of the current enabled tag keys."""

    class Meta:
        """Meta for GCPEnabledTagKeys."""

        db_table = "reporting_gcpenabledtagkeys"

    id = models.BigAutoField(primary_key=True)
    key = models.CharField(max_length=253, unique=True)


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


# Materialized Views for UI Reporting
class GCPCostSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost.

    """

    class Meta:
        """Meta for GCPCostSummary."""

        db_table = "reporting_gcp_cost_summary"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)

    invoice_month = models.CharField(max_length=256, null=True, blank=True)

    credit_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True, blank=True)


class GCPCostSummaryByAccount(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by account.

    """

    class Meta:
        """Meta for GCPCostSummaryByAccount."""

        db_table = "reporting_gcp_cost_summary_by_account"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    account_id = models.CharField(max_length=50, null=False)

    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)

    invoice_month = models.CharField(max_length=256, null=True, blank=True)

    credit_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True, blank=True)


class GCPCostSummaryByProject(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by account.

    """

    class Meta:
        """Meta for GCPCostSummaryByProject."""

        db_table = "reporting_gcp_cost_summary_by_project"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)

    project_id = models.CharField(unique=True, max_length=256)

    project_name = models.CharField(max_length=256)

    account_id = models.CharField(max_length=50, null=False)

    invoice_month = models.CharField(max_length=256, null=True, blank=True)

    credit_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True, blank=True)


class GCPCostSummaryByRegion(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by region.

    """

    class Meta:
        """Meta for GCPCostSummaryByRegion."""

        db_table = "reporting_gcp_cost_summary_by_region"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    account_id = models.CharField(max_length=50, null=False)

    region = models.CharField(max_length=50, null=True)

    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)

    invoice_month = models.CharField(max_length=256, null=True, blank=True)

    credit_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True, blank=True)


class GCPCostSummaryByService(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by service.

    """

    class Meta:
        """Meta for GCPCostSummaryByService."""

        db_table = "reporting_gcp_cost_summary_by_service"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    account_id = models.CharField(max_length=50, null=False)

    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)

    service_id = models.CharField(max_length=256, null=True)

    service_alias = models.CharField(max_length=256, null=True, blank=True)

    invoice_month = models.CharField(max_length=256, null=True, blank=True)

    credit_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True, blank=True)


class GCPComputeSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class Meta:
        """Meta for GCPComputeSummary."""

        db_table = "reporting_gcp_compute_summary"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    instance_type = models.CharField(max_length=50, null=True)

    usage_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)

    invoice_month = models.CharField(max_length=256, null=True, blank=True)

    credit_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True, blank=True)


class GCPComputeSummaryByProject(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by account.

    """

    class Meta:
        """Meta for GCPComputeSummaryByProject."""

        db_table = "reporting_gcp_compute_summary_by_project"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    instance_type = models.CharField(max_length=50, null=True)

    usage_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)

    project_id = models.CharField(unique=True, max_length=256)

    project_name = models.CharField(max_length=256)

    account_id = models.CharField(max_length=50, null=False)

    invoice_month = models.CharField(max_length=256, null=True, blank=True)

    credit_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True, blank=True)


class GCPComputeSummaryByService(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of compute usage by service and instance type.

    """

    class Meta:
        """Meta for GCPComputeSummaryByService."""

        db_table = "reporting_gcp_compute_summary_by_service"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    instance_type = models.CharField(max_length=50, null=True)

    usage_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)

    service_id = models.CharField(max_length=256, null=True)

    service_alias = models.CharField(max_length=256, null=True, blank=True)

    account_id = models.CharField(max_length=50, null=False)

    invoice_month = models.CharField(max_length=256, null=True, blank=True)

    credit_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True, blank=True)


class GCPComputeSummaryByAccount(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by service and instance type.

    """

    class Meta:
        """Meta for GCPComputeSummaryByAccount."""

        db_table = "reporting_gcp_compute_summary_by_account"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    instance_type = models.CharField(max_length=50, null=True)

    usage_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)

    account_id = models.CharField(max_length=50, null=False)

    invoice_month = models.CharField(max_length=256, null=True, blank=True)

    credit_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True, blank=True)


class GCPComputeSummaryByRegion(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by service and instance type.

    """

    class Meta:
        """Meta for GCPComputeSummaryByRegion."""

        db_table = "reporting_gcp_compute_summary_by_region"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    instance_type = models.CharField(max_length=50, null=True)

    usage_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)

    account_id = models.CharField(max_length=50, null=False)

    region = models.CharField(max_length=50, null=True)

    invoice_month = models.CharField(max_length=256, null=True, blank=True)

    credit_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True, blank=True)


class GCPStorageSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of storage usage.

    """

    class Meta:
        """Meta for GCPStorageSummary."""

        db_table = "reporting_gcp_storage_summary"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    usage_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)

    invoice_month = models.CharField(max_length=256, null=True, blank=True)

    credit_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True, blank=True)


class GCPStorageSummaryByProject(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by account.

    """

    class Meta:
        """Meta for GCPStorageSummaryByProject."""

        db_table = "reporting_gcp_storage_summary_by_project"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    usage_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)

    project_id = models.CharField(unique=True, max_length=256)

    project_name = models.CharField(max_length=256)

    account_id = models.CharField(max_length=50, null=False)

    invoice_month = models.CharField(max_length=256, null=True, blank=True)

    credit_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True, blank=True)


class GCPStorageSummaryByService(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of compute usage by service and instance type.

    """

    class Meta:
        """Meta for GCPStorageSummaryByService."""

        db_table = "reporting_gcp_storage_summary_by_service"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    usage_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)

    service_id = models.CharField(max_length=256, null=True)

    service_alias = models.CharField(max_length=256, null=True, blank=True)

    account_id = models.CharField(max_length=50, null=False)

    invoice_month = models.CharField(max_length=256, null=True, blank=True)

    credit_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True, blank=True)


class GCPStorageSummaryByAccount(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by service and instance type.

    """

    class Meta:
        """Meta for GCPStorageSummaryByAccount."""

        db_table = "reporting_gcp_storage_summary_by_account"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    instance_type = models.CharField(max_length=50, null=True)

    usage_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)

    account_id = models.CharField(max_length=50, null=False)

    invoice_month = models.CharField(max_length=256, null=True, blank=True)

    credit_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True, blank=True)


class GCPStorageSummaryByRegion(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by service and instance type.

    """

    class Meta:
        """Meta for GCPStorageSummaryByRegion."""

        db_table = "reporting_gcp_storage_summary_by_region"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    instance_type = models.CharField(max_length=50, null=True)

    usage_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)

    account_id = models.CharField(max_length=50, null=False)

    region = models.CharField(max_length=50, null=True)

    invoice_month = models.CharField(max_length=256, null=True, blank=True)

    credit_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True, blank=True)


class GCPNetworkSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of network usage.

    """

    class Meta:
        """Meta for GCPNetworkSummary."""

        db_table = "reporting_gcp_network_summary"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    account_id = models.CharField(max_length=50, null=False)

    usage_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)

    service_id = models.CharField(max_length=256, null=True)

    service_alias = models.CharField(max_length=256, null=True, blank=True)

    invoice_month = models.CharField(max_length=256, null=True, blank=True)

    credit_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True, blank=True)


class GCPDatabaseSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of database usage.

    """

    class Meta:
        """Meta for GCPDatabaseSummary."""

        db_table = "reporting_gcp_database_summary"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    account_id = models.CharField(max_length=50, null=False)

    usage_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency = models.CharField(max_length=10)

    source_uuid = models.UUIDField(unique=False, null=True)

    service_id = models.CharField(max_length=256, null=True)

    service_alias = models.CharField(max_length=256, null=True, blank=True)

    invoice_month = models.CharField(max_length=256, null=True, blank=True)

    credit_amount = models.DecimalField(max_digits=33, decimal_places=15, null=True, blank=True)
