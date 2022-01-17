#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for AWS cost entry tables."""
from uuid import uuid4

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import JSONField


UI_SUMMARY_TABLES = (
    "reporting_aws_compute_summary_p",
    "reporting_aws_compute_summary_by_account_p",
    "reporting_aws_compute_summary_by_region_p",
    "reporting_aws_compute_summary_by_service_p",
    "reporting_aws_cost_summary_p",
    "reporting_aws_cost_summary_by_account_p",
    "reporting_aws_cost_summary_by_region_p",
    "reporting_aws_cost_summary_by_service_p",
    "reporting_aws_storage_summary_p",
    "reporting_aws_storage_summary_by_account_p",
    "reporting_aws_storage_summary_by_region_p",
    "reporting_aws_storage_summary_by_service_p",
    "reporting_aws_database_summary_p",
    "reporting_aws_network_summary_p",
)

# TODO: Update this subset when we trim out the unecessary ui tables.
UI_SUMMARY_TABLES_MARKUP_SUBSET = UI_SUMMARY_TABLES


PRESTO_LINE_ITEM_TABLE = "aws_line_items"
PRESTO_LINE_ITEM_DAILY_TABLE = "aws_line_items_daily"
PRESTO_OCP_ON_AWS_DAILY_TABLE = "aws_openshift_daily"

PRESTO_REQUIRED_COLUMNS = (
    "lineItem/UsageStartDate",
    "lineItem/ProductCode",
    "product/productFamily",
    "lineItem/UsageAccountId",
    "lineItem/AvailabilityZone",
    "product/region",
    "product/instanceType",
    "pricing/unit",
    "lineItem/UsageAmount",
    "lineItem/NormalizationFactor",
    "lineItem/NormalizedUsageAmount",
    "lineItem/CurrencyCode",
    "lineItem/UnblendedRate",
    "lineItem/UnblendedCost",
    "lineItem/BlendedRate",
    "lineItem/BlendedCost",
    "savingsPlan/SavingsPlanEffectiveCost",
    "pricing/publicOnDemandCost",
    "pricing/publicOnDemandRate",
    "lineItem/ResourceId",
    "resourceTags",
    "savingsPlan/SavingsPlanEffectiveCost",
)


class AWSCostEntryBill(models.Model):
    """The billing information for a Cost Usage Report.

    The billing period (1 month) will cover many cost entries.

    """

    class Meta:
        """Meta for AWSCostEntryBill."""

        unique_together = ("bill_type", "payer_account_id", "billing_period_start", "provider")

    billing_resource = models.CharField(max_length=50, default="aws", null=False)
    bill_type = models.CharField(max_length=50, null=True)
    payer_account_id = models.CharField(max_length=50, null=True)
    billing_period_start = models.DateTimeField(null=False)
    billing_period_end = models.DateTimeField(null=False)
    summary_data_creation_datetime = models.DateTimeField(null=True)
    summary_data_updated_datetime = models.DateTimeField(null=True)
    finalized_datetime = models.DateTimeField(null=True)
    derived_cost_datetime = models.DateTimeField(null=True)

    provider = models.ForeignKey("api.Provider", on_delete=models.CASCADE)


class AWSCostEntry(models.Model):
    """A Cost Entry for an AWS Cost Usage Report.

    A cost entry covers a specific time interval (i.e. 1 hour).

    """

    class Meta:
        """Meta for AWSCostEntry."""

        indexes = [models.Index(fields=["interval_start"], name="interval_start_idx")]

    interval_start = models.DateTimeField(null=False)
    interval_end = models.DateTimeField(null=False)

    bill = models.ForeignKey("AWSCostEntryBill", on_delete=models.CASCADE)


class AWSCostEntryLineItem(models.Model):
    """A line item in a cost entry.

    This identifies specific costs and usage of AWS resources.

    """

    id = models.BigAutoField(primary_key=True)

    cost_entry = models.ForeignKey("AWSCostEntry", on_delete=models.CASCADE, db_constraint=False)
    cost_entry_bill = models.ForeignKey("AWSCostEntryBill", on_delete=models.CASCADE, db_constraint=False)
    cost_entry_product = models.ForeignKey(
        "AWSCostEntryProduct", on_delete=models.SET_NULL, null=True, db_constraint=False
    )
    cost_entry_pricing = models.ForeignKey(
        "AWSCostEntryPricing", on_delete=models.SET_NULL, null=True, db_constraint=False
    )
    cost_entry_reservation = models.ForeignKey(
        "AWSCostEntryReservation", on_delete=models.SET_NULL, null=True, db_constraint=False
    )

    tags = JSONField(null=True)

    # Invoice ID is null until the bill is finalized
    invoice_id = models.CharField(max_length=63, null=True)
    line_item_type = models.CharField(max_length=50, null=False)
    usage_account_id = models.CharField(max_length=50, null=False)
    usage_start = models.DateTimeField(null=False)
    usage_end = models.DateTimeField(null=False)
    product_code = models.CharField(max_length=50, null=False)
    usage_type = models.CharField(max_length=50, null=True)
    operation = models.CharField(max_length=50, null=True)
    availability_zone = models.CharField(max_length=50, null=True)
    resource_id = models.CharField(max_length=256, null=True)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    normalization_factor = models.FloatField(null=True)
    normalized_usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency_code = models.CharField(max_length=10)
    unblended_rate = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    blended_rate = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    blended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    savingsplan_effective_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    public_on_demand_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    public_on_demand_rate = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    reservation_amortized_upfront_fee = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    reservation_amortized_upfront_cost_for_usage = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    reservation_recurring_fee_for_usage = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    # Unused reservation fields more useful for later predictions.
    reservation_unused_quantity = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    reservation_unused_recurring_fee = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    tax_type = models.TextField(null=True)


class AWSCostEntryLineItemDaily(models.Model):
    """A daily aggregation of line items.

    This table is aggregated by AWS resource.

    """

    class Meta:
        """Meta for AWSCostEntryLineItemDaily."""

        db_table = "reporting_awscostentrylineitem_daily"

        indexes = [
            models.Index(fields=["usage_start"], name="usage_start_idx"),
            models.Index(fields=["product_code"], name="product_code_idx"),
            models.Index(fields=["usage_account_id"], name="usage_account_id_idx"),
            models.Index(fields=["resource_id"], name="resource_id_idx"),
            GinIndex(fields=["tags"], name="aws_cost_entry"),
            GinIndex(fields=["product_code"], name="aws_cost_pcode_like", opclasses=["gin_trgm_ops"]),
        ]

    id = models.BigAutoField(primary_key=True)

    cost_entry_bill = models.ForeignKey("AWSCostEntryBill", on_delete=models.CASCADE, null=True)
    cost_entry_product = models.ForeignKey("AWSCostEntryProduct", on_delete=models.SET_NULL, null=True)
    cost_entry_pricing = models.ForeignKey("AWSCostEntryPricing", on_delete=models.SET_NULL, null=True)
    cost_entry_reservation = models.ForeignKey("AWSCostEntryReservation", on_delete=models.SET_NULL, null=True)

    line_item_type = models.CharField(max_length=50, null=False)
    usage_account_id = models.CharField(max_length=50, null=False)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=True)
    product_code = models.CharField(max_length=50, null=False)
    usage_type = models.CharField(max_length=50, null=True)
    operation = models.CharField(max_length=50, null=True)
    availability_zone = models.CharField(max_length=50, null=True)
    resource_id = models.CharField(max_length=256, null=True)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    normalization_factor = models.FloatField(null=True)
    normalized_usage_amount = models.FloatField(null=True)
    currency_code = models.CharField(max_length=10)
    unblended_rate = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    blended_rate = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    blended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    savingsplan_effective_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    public_on_demand_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    public_on_demand_rate = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    tax_type = models.TextField(null=True)
    tags = JSONField(null=True)


class AWSCostEntryLineItemDailySummary(models.Model):
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
        """Meta for AWSCostEntryLineItemDailySummary."""

        db_table = "reporting_awscostentrylineitem_daily_summary"

        indexes = [
            models.Index(fields=["usage_start"], name="summary_usage_start_idx"),
            models.Index(fields=["product_code"], name="summary_product_code_idx"),
            models.Index(fields=["usage_account_id"], name="summary_usage_account_id_idx"),
            GinIndex(fields=["tags"], name="tags_idx"),
            models.Index(fields=["account_alias"], name="summary_account_alias_idx"),
            models.Index(fields=["product_family"], name="summary_product_family_idx"),
            models.Index(fields=["instance_type"], name="summary_instance_type_idx"),
            # A GIN functional index named "aws_summ_usage_pfam_ilike" was created manually
            # via RunSQL migration operation
            # Function: (upper(product_family) gin_trgm_ops)
            # A GIN functional index named "aws_summ_usage_pcode_ilike" was created manually
            # via RunSQL migration operation
            # Function: (upper(product_code) gin_trgm_ops)
        ]

    uuid = models.UUIDField(primary_key=True)

    cost_entry_bill = models.ForeignKey("AWSCostEntryBill", on_delete=models.CASCADE, null=True)

    # The following fields are used for grouping
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=True)
    usage_account_id = models.CharField(max_length=50, null=False)
    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.PROTECT, null=True)
    product_code = models.CharField(max_length=50, null=False)
    product_family = models.CharField(max_length=150, null=True)
    availability_zone = models.CharField(max_length=50, null=True)
    region = models.CharField(max_length=50, null=True)
    instance_type = models.CharField(max_length=50, null=True)
    unit = models.CharField(max_length=63, null=True)
    organizational_unit = models.ForeignKey("AWSOrganizationalUnit", on_delete=models.SET_NULL, null=True)

    # The following fields are aggregates
    resource_ids = ArrayField(models.TextField(), null=True)
    resource_count = models.IntegerField(null=True)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    normalization_factor = models.FloatField(null=True)
    normalized_usage_amount = models.FloatField(null=True)
    currency_code = models.CharField(max_length=10)
    unblended_rate = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    blended_rate = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    blended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    savingsplan_effective_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    public_on_demand_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    public_on_demand_rate = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    tax_type = models.TextField(null=True)
    tags = JSONField(null=True)
    source_uuid = models.UUIDField(unique=False, null=True)


class AWSCostEntryPricing(models.Model):
    """Pricing information for a cost entry line item."""

    class Meta:
        """Meta for AWSCostEntryLineItem."""

        unique_together = ("term", "unit")

    term = models.CharField(max_length=63, null=True)
    unit = models.CharField(max_length=63, null=True)


class AWSCostEntryProduct(models.Model):
    """The AWS product identified in a cost entry line item."""

    class Meta:
        """Meta for AWSCostEntryProduct."""

        unique_together = ("sku", "product_name", "region")
        indexes = [models.Index(fields=["region"], name="region_idx")]

    sku = models.CharField(max_length=128, null=True)
    product_name = models.TextField(null=True)
    product_family = models.CharField(max_length=150, null=True)
    service_code = models.CharField(max_length=50, null=True)
    region = models.CharField(max_length=50, null=True)
    # The following fields are useful for EC2 instances
    instance_type = models.CharField(max_length=50, null=True)
    memory = models.FloatField(null=True)
    memory_unit = models.CharField(max_length=24, null=True)
    vcpu = models.PositiveIntegerField(null=True)


class AWSCostEntryReservation(models.Model):
    """Information on a particular reservation in the AWS account."""

    reservation_arn = models.TextField(unique=True)
    number_of_reservations = models.PositiveIntegerField(null=True)
    units_per_reservation = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    start_time = models.DateTimeField(null=True)
    end_time = models.DateTimeField(null=True)


class AWSAccountAlias(models.Model):
    """The alias table for AWS accounts."""

    account_id = models.CharField(max_length=50, null=False, unique=True)
    account_alias = models.CharField(max_length=63, null=True)

    def __str__(self):
        """Convert to string."""
        return f"{{ id : {self.id}, account_id : {self.account_id}, account_alias : {self.account_alias} }}"


class AWSTagsValues(models.Model):
    class Meta:
        """Meta for AWSTagsValues."""

        db_table = "reporting_awstags_values"
        unique_together = ("key", "value")
        indexes = [models.Index(fields=["key"], name="aws_tags_value_key_idx")]

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    key = models.TextField()
    value = models.TextField()
    usage_account_ids = ArrayField(models.TextField())
    account_aliases = ArrayField(models.TextField())


class AWSTagsSummary(models.Model):
    """A collection of all current existing tag key and values."""

    class Meta:
        """Meta for AWSTagSummary."""

        db_table = "reporting_awstags_summary"
        unique_together = ("key", "cost_entry_bill", "usage_account_id")

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    key = models.TextField()
    values = ArrayField(models.TextField())
    cost_entry_bill = models.ForeignKey("AWSCostEntryBill", on_delete=models.CASCADE)
    usage_account_id = models.TextField(null=True)
    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)


class AWSOrganizationalUnit(models.Model):
    """The alias table for AWS Organizational Unit."""

    org_unit_name = models.CharField(max_length=250, null=False, unique=False)

    org_unit_id = models.CharField(max_length=50, null=False, unique=False)

    org_unit_path = models.TextField(null=False, unique=False)

    level = models.PositiveSmallIntegerField(null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.PROTECT, null=True)

    created_timestamp = models.DateField(auto_now_add=True)

    deleted_timestamp = models.DateField(null=True)

    provider = models.ForeignKey("api.Provider", on_delete=models.CASCADE, null=True)

    def __str__(self):
        """Convert to string."""
        return (
            "{ id : %s, "
            "org_unit_name : %s, "
            "org_unit_id : %s, "
            "org_unit_path : %s, "
            "level : %s, "
            "account_alias : %s, "
            "created_timestamp : %s, "
            "deleted_timestamp : %s }"
            % (
                self.id,
                self.org_unit_name,
                self.org_unit_id,
                self.org_unit_path,
                self.level,
                self.account_alias,
                self.created_timestamp,
                self.deleted_timestamp,
            )
        )


class AWSEnabledTagKeys(models.Model):
    """A collection of the current enabled tag keys."""

    class Meta:
        """Meta for AWSEnabledTagKeys."""

        indexes = [models.Index(fields=["key", "enabled"], name="aws_enabled_key_index")]
        db_table = "reporting_awsenabledtagkeys"

    key = models.CharField(max_length=253, primary_key=True)
    enabled = models.BooleanField(default=True)


# ======================================================
#  Partitioned Models to replace matviews
# ======================================================


class AWSCostSummaryP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for AWSCostSummaryP."""

        db_table = "reporting_aws_cost_summary_p"
        indexes = [models.Index(fields=["usage_start"], name="awscostsumm_usage_start")]

    id = models.UUIDField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    blended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    savingsplan_effective_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class AWSCostSummaryByServiceP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by service.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for AWSCostSummaryByServiceP."""

        db_table = "reporting_aws_cost_summary_by_service_p"
        indexes = [
            models.Index(fields=["usage_start"], name="awscostsumm_svc_usage_start"),
            models.Index(fields=["product_code"], name="awscostsumm_svc_prod_cd"),
        ]

    id = models.UUIDField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)

    organizational_unit = models.ForeignKey("AWSOrganizationalUnit", on_delete=models.SET_NULL, null=True)

    product_code = models.CharField(max_length=50, null=False)

    product_family = models.CharField(max_length=150, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    blended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    savingsplan_effective_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class AWSCostSummaryByAccountP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by account.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for AWSCostSummaryByAccountP."""

        db_table = "reporting_aws_cost_summary_by_account_p"
        indexes = [models.Index(fields=["usage_start"], name="awscostsumm_acct_usage_start")]

    id = models.UUIDField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)

    organizational_unit = models.ForeignKey("AWSOrganizationalUnit", on_delete=models.SET_NULL, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    blended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    savingsplan_effective_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


# EXAMPLE FROM HAP
class AWSCostSummaryByRegionP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by region.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for AWSCostSummaryByRegionP."""

        db_table = "reporting_aws_cost_summary_by_region_p"
        indexes = [
            models.Index(fields=["usage_start"], name="awscostsumm_reg_usage_start"),
            models.Index(fields=["region"], name="awscostsumm_reg_region"),
            models.Index(fields=["availability_zone"], name="awscostsumm_reg_zone"),
        ]

    id = models.UUIDField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)

    organizational_unit = models.ForeignKey("AWSOrganizationalUnit", on_delete=models.SET_NULL, null=True)

    region = models.CharField(max_length=50, null=True)

    availability_zone = models.CharField(max_length=50, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    blended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    savingsplan_effective_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class AWSComputeSummaryP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for AWSComputeSummaryP."""

        db_table = "reporting_aws_compute_summary_p"
        indexes = [
            models.Index(fields=["usage_start"], name="awscompsumm_usage_start"),
            models.Index(fields=["instance_type"], name="awscompsumm_insttyp"),
        ]

    id = models.UUIDField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    instance_type = models.CharField(max_length=50, null=True)

    resource_ids = ArrayField(models.CharField(max_length=256), null=True)

    resource_count = models.IntegerField(null=True)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    blended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    savingsplan_effective_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class AWSComputeSummaryByServiceP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of compute usage by service and instance type.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for AWSComputeSummaryByServiceP."""

        db_table = "reporting_aws_compute_summary_by_service_p"
        indexes = [
            models.Index(fields=["usage_start"], name="awscompsumm_svc_usage_start"),
            models.Index(fields=["instance_type"], name="awscompsumm_svc_insttyp"),
        ]

    id = models.UUIDField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)

    organizational_unit = models.ForeignKey("AWSOrganizationalUnit", on_delete=models.SET_NULL, null=True)

    product_code = models.CharField(max_length=50, null=False)

    product_family = models.CharField(max_length=150, null=True)

    instance_type = models.CharField(max_length=50, null=True)

    resource_ids = ArrayField(models.CharField(max_length=256), null=True)

    resource_count = models.IntegerField(null=True)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    blended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    savingsplan_effective_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class AWSComputeSummaryByAccountP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by account.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for AWSComputeSummaryByAccountP."""

        db_table = "reporting_aws_compute_summary_by_account_p"
        indexes = [
            models.Index(fields=["usage_start"], name="awscompsumm_acct_usage_start"),
            models.Index(fields=["instance_type"], name="awscompsumm_acct_insttyp"),
        ]

    id = models.UUIDField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)

    organizational_unit = models.ForeignKey("AWSOrganizationalUnit", on_delete=models.SET_NULL, null=True)

    instance_type = models.CharField(max_length=50, null=True)

    resource_ids = ArrayField(models.CharField(max_length=256), null=True)

    resource_count = models.IntegerField(null=True)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    blended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    savingsplan_effective_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class AWSComputeSummaryByRegionP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by region.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for AWSComputeSummaryByRegionP."""

        db_table = "reporting_aws_compute_summary_by_region_p"
        indexes = [
            models.Index(fields=["usage_start"], name="awscompsumm_reg_usage_start"),
            models.Index(fields=["region"], name="awscompsumm_reg_region"),
            models.Index(fields=["availability_zone"], name="awscompsumm_reg_zone"),
            models.Index(fields=["instance_type"], name="awscompsumm_reg_insttyp"),
        ]

    id = models.UUIDField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)

    organizational_unit = models.ForeignKey("AWSOrganizationalUnit", on_delete=models.SET_NULL, null=True)

    region = models.CharField(max_length=50, null=True)

    availability_zone = models.CharField(max_length=50, null=True)

    instance_type = models.CharField(max_length=50, null=True)

    resource_ids = ArrayField(models.CharField(max_length=256), null=True)

    resource_count = models.IntegerField(null=True)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    blended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    savingsplan_effective_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class AWSStorageSummaryP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of storage usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for AWSStorageSummaryP."""

        db_table = "reporting_aws_storage_summary_p"
        indexes = [
            models.Index(fields=["usage_start"], name="awsstorsumm_usage_start"),
            models.Index(fields=["product_family"], name="awsstorsumm_product_fam"),
        ]

    id = models.UUIDField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    product_family = models.CharField(max_length=150, null=True)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    blended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    savingsplan_effective_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class AWSStorageSummaryByServiceP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of storage usage by service.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for AWSStorageSummaryP."""

        db_table = "reporting_aws_storage_summary_by_service_p"
        indexes = [
            models.Index(fields=["usage_start"], name="awsstorsumm_svc_usage_start"),
            models.Index(fields=["product_family"], name="awsstorsumm_product_svc_fam"),
        ]

    id = models.UUIDField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)

    organizational_unit = models.ForeignKey("AWSOrganizationalUnit", on_delete=models.SET_NULL, null=True)

    product_code = models.CharField(max_length=50, null=False)

    product_family = models.CharField(max_length=150, null=True)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    blended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    savingsplan_effective_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class AWSStorageSummaryByAccountP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of storage by account.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for AWSStorageSummaryByAccountP."""

        db_table = "reporting_aws_storage_summary_by_account_p"
        indexes = [
            models.Index(fields=["usage_start"], name="awsstorsumm_acct_usage_start"),
            models.Index(fields=["product_family"], name="awsstorsumm_product_acct_fam"),
        ]

    id = models.UUIDField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)

    organizational_unit = models.ForeignKey("AWSOrganizationalUnit", on_delete=models.SET_NULL, null=True)

    product_family = models.CharField(max_length=150, null=True)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    blended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    savingsplan_effective_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class AWSStorageSummaryByRegionP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of total cost by region.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for AWSStorageSummaryByRegionP."""

        db_table = "reporting_aws_storage_summary_by_region_p"
        indexes = [
            models.Index(fields=["usage_start"], name="awsstorsumm_reg_usage_start"),
            models.Index(fields=["region"], name="awsstorsumm_reg_region"),
            models.Index(fields=["availability_zone"], name="awsstorsumm_reg_zone"),
            models.Index(fields=["product_family"], name="awsstorsumm_reg_product_fam"),
        ]

    id = models.UUIDField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)

    organizational_unit = models.ForeignKey("AWSOrganizationalUnit", on_delete=models.SET_NULL, null=True)

    region = models.CharField(max_length=50, null=True)

    availability_zone = models.CharField(max_length=50, null=True)

    product_family = models.CharField(max_length=150, null=True)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    blended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    savingsplan_effective_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class AWSNetworkSummaryP(models.Model):
    """A summarized partition table specifically for UI API queries.

    This table gives a daily breakdown of network usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for AWSNetworkSummaryP."""

        db_table = "reporting_aws_network_summary_p"
        indexes = [
            models.Index(fields=["usage_start"], name="awsnetsumm_usage_start"),
            models.Index(fields=["product_code"], name="awsnetsumm_product_cd"),
        ]

    id = models.UUIDField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)

    organizational_unit = models.ForeignKey("AWSOrganizationalUnit", on_delete=models.SET_NULL, null=True)

    product_code = models.CharField(max_length=50, null=False)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    blended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    savingsplan_effective_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


class AWSDatabaseSummaryP(models.Model):
    """A summarized partitioned table specifically for UI API queries.

    This table gives a daily breakdown of database usage.

    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for AWSDatabaseSummaryP."""

        db_table = "reporting_aws_database_summary_p"
        indexes = [
            models.Index(fields=["usage_start"], name="awsdbsumm_usage_start"),
            models.Index(fields=["product_code"], name="awsdbsumm_product_cd"),
        ]

    id = models.UUIDField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)

    organizational_unit = models.ForeignKey("AWSOrganizationalUnit", on_delete=models.SET_NULL, null=True)

    product_code = models.CharField(max_length=50, null=False)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    blended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    savingsplan_effective_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    currency_code = models.CharField(max_length=10)

    source_uuid = models.ForeignKey(
        "api.Provider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
