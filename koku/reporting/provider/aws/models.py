#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for AWS cost entry tables."""
from uuid import uuid4

import pandas as pd
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import JSONField


UI_SUMMARY_TABLES = (
    "reporting_aws_compute_summary_p",
    "reporting_aws_compute_summary_by_account_p",
    "reporting_aws_cost_summary_p",
    "reporting_aws_cost_summary_by_account_p",
    "reporting_aws_cost_summary_by_region_p",
    "reporting_aws_cost_summary_by_service_p",
    "reporting_aws_storage_summary_p",
    "reporting_aws_storage_summary_by_account_p",
    "reporting_aws_database_summary_p",
    "reporting_aws_network_summary_p",
)

# TODO: Update this subset when we trim out the unecessary ui tables.
UI_SUMMARY_TABLES_MARKUP_SUBSET = UI_SUMMARY_TABLES


TRINO_LINE_ITEM_TABLE = "aws_line_items"
TRINO_LINE_ITEM_DAILY_TABLE = "aws_line_items_daily"
TRINO_OCP_ON_AWS_DAILY_TABLE = "aws_openshift_daily"
TRINO_OCP_AWS_DAILY_SUMMARY_TABLE = "managed_reporting_ocpawscostlineitem_project_daily_summary"

TRINO_REQUIRED_COLUMNS = {
    "bill/BillingEntity": "",
    "lineItem/UsageStartDate": pd.NaT,
    "lineItem/ProductCode": "",
    "product/productFamily": "",
    "product/ProductName": "",
    "lineItem/UsageAccountId": "",
    "lineItem/LegalEntity": "",
    "lineItem/LineItemDescription": "",
    "lineItem/LineItemType": "",
    "lineItem/AvailabilityZone": "",
    "product/region": "",
    "product/instanceType": "",
    "product/physicalCores": "",
    "product/vcpu": "",
    "product/memory": "",
    "product/operatingSystem": "",
    "pricing/unit": "",
    "lineItem/UsageAmount": 0.0,
    "lineItem/NormalizationFactor": 0.0,
    "lineItem/NormalizedUsageAmount": 0.0,
    "lineItem/CurrencyCode": "",
    "lineItem/UnblendedRate": 0.0,
    "lineItem/UnblendedCost": 0.0,
    "lineItem/BlendedRate": 0.0,
    "lineItem/BlendedCost": 0.0,
    "savingsPlan/SavingsPlanEffectiveCost": 0.0,
    "pricing/publicOnDemandCost": 0.0,
    "pricing/publicOnDemandRate": 0.0,
    "lineItem/ResourceId": "",
    "resourceTags": "",
    "costCategory": "",
}


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
    provider = models.ForeignKey("reporting.TenantAPIProvider", on_delete=models.CASCADE)


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
            GinIndex(fields=["cost_category"], name="cost_category_idx"),
            models.Index(fields=["account_alias"], name="summary_account_alias_idx"),
            models.Index(fields=["product_family"], name="summary_product_family_idx"),
            models.Index(fields=["instance_type"], name="summary_instance_type_idx"),
            models.Index(fields=["region"], name="summary_region_idx"),
            models.Index(fields=["availability_zone"], name="summary_zone_idx"),
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
    product_code = models.TextField(null=False)
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
    calculated_amortized_cost = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_amortized = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    public_on_demand_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    public_on_demand_rate = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    tax_type = models.TextField(null=True)
    tags = JSONField(null=True)
    cost_category = JSONField(null=True)
    source_uuid = models.UUIDField(unique=False, null=True)


class AWSCostEntryLineItemSummaryByEC2ComputeP(models.Model):
    """Represents a monthly aggregation of EC2 compute instance usage hours and costs.

    This table stores monthly aggregated data for EC2 compute instances,
    detailing usage hours, associated costs and other key attributes.
    """

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    class Meta:
        """Meta for AWSCostEntryLineItemSummaryByEC2ComputeResource."""

        db_table = "reporting_awscostentrylineitem_summary_by_ec2_compute_p"

        indexes = [
            # 'ec2c' for EC2 Compute
            models.Index(fields=["usage_start"], name="ec2cp_usage_start_idx"),
            models.Index(fields=["usage_account_id"], name="ec2cp_usage_account_id_idx"),
            models.Index(fields=["account_alias"], name="ec2cp_account_alias_idx"),
            models.Index(fields=["resource_id"], name="ec2cp_resource_id_idx"),
            models.Index(fields=["instance_name"], name="ec2cp_instance_name_idx"),
            models.Index(fields=["instance_type"], name="ec2cp_instance_type_idx"),
            models.Index(fields=["region"], name="ec2cp_region_idx"),
            models.Index(fields=["operating_system"], name="ec2cp_os_idx"),
            GinIndex(fields=["tags"], name="ec2cp_tags_idx"),
            GinIndex(fields=["cost_category"], name="ec2cp_cost_category_idx"),
        ]

    uuid = models.UUIDField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=True)
    cost_entry_bill = models.ForeignKey("AWSCostEntryBill", on_delete=models.CASCADE, null=True)
    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.PROTECT, null=True)
    usage_account_id = models.CharField(max_length=50, null=False)
    resource_id = models.CharField(max_length=256, null=False)
    instance_name = models.CharField(max_length=256, null=True)
    instance_type = models.CharField(max_length=50, null=True)
    operating_system = models.CharField(max_length=50, null=True)
    region = models.CharField(max_length=50, null=True)
    vcpu = models.IntegerField(null=True)
    memory = models.CharField(max_length=50, null=True)
    unit = models.CharField(max_length=63, null=True)
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
    calculated_amortized_cost = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_amortized = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    public_on_demand_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    public_on_demand_rate = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    tax_type = models.TextField(null=True)
    tags = JSONField(null=True)
    source_uuid = models.UUIDField(unique=False, null=True)
    cost_category = JSONField(null=True)


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
    provider = models.ForeignKey("reporting.TenantAPIProvider", on_delete=models.CASCADE, null=True)

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


class AWSCategorySummary(models.Model):
    """A collection of all current existing tag key and values."""

    class Meta:
        """Meta for AWSCategorySummary."""

        db_table = "reporting_awscategory_summary"
        unique_together = ("key", "cost_entry_bill", "usage_account_id")

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    key = models.TextField()
    values = ArrayField(models.TextField())
    cost_entry_bill = models.ForeignKey("AWSCostEntryBill", on_delete=models.CASCADE)
    usage_account_id = models.TextField(null=True)
    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)


class AWSEnabledCategoryKeys(models.Model):
    """A collection of the current enabled category keys."""

    class Meta:
        """Meta for AWSCategoryTagKeys."""

        indexes = [models.Index(fields=["key", "enabled"], name="aws_enabled_category_key_index")]
        db_table = "reporting_awsenabledcategorykeys"

    uuid = models.UUIDField(default=uuid4, editable=False, unique=True, primary_key=True)
    key = models.CharField(max_length=253, unique=True)
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
    calculated_amortized_cost = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_amortized = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    currency_code = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
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
    product_code = models.TextField(null=False)
    product_family = models.CharField(max_length=150, null=True)
    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    blended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    savingsplan_effective_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    calculated_amortized_cost = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_amortized = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    currency_code = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
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
    calculated_amortized_cost = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_amortized = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    currency_code = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )


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
    calculated_amortized_cost = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_amortized = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    currency_code = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
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
    calculated_amortized_cost = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_amortized = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    currency_code = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
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
    calculated_amortized_cost = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_amortized = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    currency_code = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
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
    calculated_amortized_cost = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_amortized = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    currency_code = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
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
    calculated_amortized_cost = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_amortized = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    currency_code = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
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
    product_code = models.TextField(null=False)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit = models.CharField(max_length=63, null=True)
    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    blended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    savingsplan_effective_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    calculated_amortized_cost = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_amortized = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    currency_code = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
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
    product_code = models.TextField(null=False)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit = models.CharField(max_length=63, null=True)
    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    blended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    savingsplan_effective_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    calculated_amortized_cost = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_amortized = models.DecimalField(max_digits=33, decimal_places=9, null=True)
    markup_cost_blended = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    markup_cost_savingsplan = models.DecimalField(max_digits=33, decimal_places=15, null=True)
    currency_code = models.CharField(max_length=10)
    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=True, db_column="source_uuid"
    )
