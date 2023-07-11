#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for OCI cost entry tables."""
from uuid import uuid4

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import JSONField


UI_SUMMARY_TABLES = (
    "reporting_oci_compute_summary_p",
    "reporting_oci_compute_summary_by_account_p",
    "reporting_oci_cost_summary_p",
    "reporting_oci_cost_summary_by_account_p",
    "reporting_oci_cost_summary_by_region_p",
    "reporting_oci_cost_summary_by_service_p",
    "reporting_oci_storage_summary_p",
    "reporting_oci_storage_summary_by_account_p",
    "reporting_oci_database_summary_p",
    "reporting_oci_network_summary_p",
)


TRINO_LINE_ITEM_TABLE_MAP = {"cost": "oci_cost_line_items", "usage": "oci_usage_line_items"}
TRINO_LINE_ITEM_DAILY_TABLE_MAP = {"cost": "oci_cost_line_items_daily", "usage": "oci_usage_line_items_daily"}

TRINO_REQUIRED_COLUMNS = (
    "lineItem/referenceNo",
    "lineItem/tenantId",
    "lineItem/intervalUsageStart",
    "lineItem/intervalUsageEnd",
    "product/service",
    "product/resource",
    "product/compartmentId",
    "product/compartmentName",
    "product/region",
    "product/availabilityDomain",
    "product/resourceId",
    "usage/consumedQuantity",
    "usage/billedQuantity",
    "usage/billedQuantityOverage",
    "usage/consumedQuantityUnits",
    "usage/consumedQuantityMeasure",
    "cost/subscriptionId",
    "cost/productSku",
    "product/Description",
    "cost/unitPrice",
    "cost/unitPriceOverage",
    "cost/myCost",
    "cost/myCostOverage",
    "cost/currencyCode",
    "cost/billingUnitReadable",
    "cost/skuUnitDescription",
    "cost/overageFlag",
    "lineItem/isCorrection",
    "lineItem/backreferenceNo",
    "tags",
)


class OCICostEntryBill(models.Model):
    """The billing information for a Cost Usage Report.

    The billing period (1 month) will cover many cost entries.

    """

    class Meta:
        """Meta for OCICostEntryBill."""

        unique_together = ("bill_type", "payer_tenant_id", "billing_period_start", "provider")

    billing_resource = models.CharField(max_length=80, default="oci", null=False)
    bill_type = models.CharField(max_length=50, null=True)
    payer_tenant_id = models.CharField(max_length=80, null=True)
    billing_period_start = models.DateTimeField(null=False)
    billing_period_end = models.DateTimeField(null=False)
    summary_data_creation_datetime = models.DateTimeField(null=True)
    summary_data_updated_datetime = models.DateTimeField(null=True)
    finalized_datetime = models.DateTimeField(null=True)
    derived_cost_datetime = models.DateTimeField(null=True)

    provider = models.ForeignKey("reporting.TenantAPIProvider", on_delete=models.CASCADE)


class OCICostEntryLineItemDailySummary(models.Model):
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
        """Meta for OCICostEntryLineItemDailySummary."""

        db_table = "reporting_ocicostentrylineitem_daily_summary"

        indexes = [
            models.Index(fields=["usage_start"], name="summary_oci_usage_start_idx"),
            models.Index(fields=["product_service"], name="summary_oci_product_code_idx"),
            models.Index(fields=["payer_tenant_id"], name="summary_oci_payer_tenant_idx"),
            GinIndex(fields=["tags"], name="tags_tags_idx"),
            models.Index(fields=["instance_type"], name="summary_oci_instance_type_idx"),
        ]

    uuid = models.UUIDField(primary_key=True)
    cost_entry_bill = models.ForeignKey("OCICostEntryBill", on_delete=models.CASCADE, null=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=True)
    payer_tenant_id = models.CharField(max_length=80, null=False)
    product_service = models.CharField(max_length=50, null=False)
    region = models.CharField(max_length=50, null=True)
    instance_type = models.CharField(max_length=50, null=True)
    unit = models.CharField(max_length=63, null=True)
    resource_ids = ArrayField(models.TextField(), null=True)
    resource_count = models.IntegerField(null=True)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    tags = JSONField(null=True)
    source_uuid = models.UUIDField(unique=False, null=True)


class OCITagsValues(models.Model):
    class Meta:
        """Meta for OCITagsValues."""

        db_table = "reporting_ocitags_values"
        unique_together = ("key", "value")
        indexes = [models.Index(fields=["key"], name="oci_tags_value_key_idx")]

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    key = models.TextField()
    value = models.TextField()
    payer_tenant_ids = ArrayField(models.TextField())


class OCITagsSummary(models.Model):
    """A collection of all current existing tag key and values."""

    class Meta:
        """Meta for OCITagSummary."""

        db_table = "reporting_ocitags_summary"
        unique_together = ("key", "cost_entry_bill", "payer_tenant_id")

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    key = models.TextField()
    values = ArrayField(models.TextField())
    cost_entry_bill = models.ForeignKey("OCICostEntryBill", on_delete=models.CASCADE)
    payer_tenant_id = models.TextField(null=True)


class OCIEnabledTagKeys(models.Model):
    """A collection of the current enabled tag keys."""

    class Meta:
        """Meta for OCIEnabledTagKeys."""

        indexes = [models.Index(fields=["key", "enabled"], name="oci_enabled_key_index")]
        db_table = "reporting_ocienabledtagkeys"

    key = models.CharField(max_length=253, primary_key=True)
    enabled = models.BooleanField(default=True)


class OCICostSummaryP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCICostSummaryP."""

        db_table = "reporting_oci_cost_summary_p"
        indexes = [models.Index(fields=["usage_start"], name="ocicostsumm_usage_start")]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class OCICostSummaryByServiceP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by service.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCICostSummaryByServiceP."""

        db_table = "reporting_oci_cost_summary_by_service_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocicostsumm_svc_usage_start"),
            models.Index(fields=["product_service"], name="ocicostsumm_svc_prod_cd"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    payer_tenant_id = models.CharField(max_length=80, null=False)
    product_service = models.CharField(max_length=50, null=False)
    cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class OCICostSummaryByAccountP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by account.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCICostSummaryByAccountP."""

        db_table = "reporting_oci_cost_summary_by_account_p"
        indexes = [models.Index(fields=["usage_start"], name="ocicostsumm_acct_usage_start")]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    payer_tenant_id = models.CharField(max_length=80, null=False)
    cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class OCICostSummaryByRegionP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by region.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCICostSummaryByRegionP."""

        db_table = "reporting_oci_cost_summary_by_region_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocicostsumm_reg_usage_start"),
            models.Index(fields=["region"], name="ocicostsumm_reg_region"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    payer_tenant_id = models.CharField(max_length=80, null=False)
    region = models.CharField(max_length=50, null=True)
    cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class OCIComputeSummaryP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCIComputeSummaryP."""

        db_table = "reporting_oci_compute_summary_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocicompsumm_usage_start"),
            models.Index(fields=["instance_type"], name="ocicompsumm_insttyp"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    instance_type = models.CharField(max_length=50, null=True)
    resource_ids = ArrayField(models.CharField(max_length=256), null=True)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    resource_count = models.IntegerField(null=True)
    unit = models.CharField(max_length=63, null=True)
    cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class OCIComputeSummaryByAccountP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by account.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCIComputeSummaryByAccountP."""

        db_table = "reporting_oci_compute_summary_by_account_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocicompsumm_acct_usage_start"),
            models.Index(fields=["instance_type"], name="ocicompsumm_acct_insttyp"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    payer_tenant_id = models.CharField(max_length=80, null=False)
    instance_type = models.CharField(max_length=50, null=True)
    resource_ids = ArrayField(models.CharField(max_length=256), null=True)
    resource_count = models.IntegerField(null=True)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit = models.CharField(max_length=63, null=True)
    cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class OCIStorageSummaryP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of storage usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCIStorageSummaryP."""

        db_table = "reporting_oci_storage_summary_p"
        indexes = [models.Index(fields=["usage_start"], name="ocistorsumm_usage_start")]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    product_service = models.CharField(max_length=50, null=False)
    unit = models.CharField(max_length=63, null=True)
    cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class OCIStorageSummaryByAccountP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of storage by account.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCIStorageSummaryByAccountP."""

        db_table = "reporting_oci_storage_summary_by_account_p"
        indexes = [models.Index(fields=["usage_start"], name="ocistorsumm_acct_usage_start")]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    payer_tenant_id = models.CharField(max_length=80, null=False)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    product_service = models.CharField(max_length=50, null=False)
    unit = models.CharField(max_length=63, null=True)
    cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class OCINetworkSummaryP(models.Model):
    """A summarized partition table specifically for UI API queries.

    This table gives a daily breakdown of network usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCINetworkSummaryP."""

        db_table = "reporting_oci_network_summary_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocinetsumm_usage_start"),
            models.Index(fields=["product_service"], name="ocinetsumm_product_cd"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    payer_tenant_id = models.CharField(max_length=80, null=False)
    product_service = models.CharField(max_length=50, null=False)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit = models.CharField(max_length=63, null=True)
    cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class OCIDatabaseSummaryP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of database usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for OCIDatabaseSummaryP."""

        db_table = "reporting_oci_database_summary_p"
        indexes = [
            models.Index(fields=["usage_start"], name="ocidbsumm_usage_start"),
            models.Index(fields=["product_service"], name="ocidbsumm_product_cd"),
        ]

    id = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    payer_tenant_id = models.CharField(max_length=80, null=False)
    product_service = models.CharField(max_length=50, null=False)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit = models.CharField(max_length=63, null=True)
    cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
