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
"""Models for AWS cost entry tables."""
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.fields import JSONField
from django.contrib.postgres.indexes import GinIndex
from django.db import models


class AWSCostEntryBill(models.Model):
    """The billing information for a Cost Usage Report.

    The billing period (1 month) will cover many cost entries.

    """

    class Meta:
        """Meta for AWSCostEntryBill."""

        unique_together = ("bill_type", "payer_account_id", "billing_period_start", "provider")

    billing_resource = models.CharField(max_length=50, default="aws", null=False)
    bill_type = models.CharField(max_length=50, null=False)
    payer_account_id = models.CharField(max_length=50, null=False)
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

    cost_entry = models.ForeignKey("AWSCostEntry", on_delete=models.CASCADE)
    cost_entry_bill = models.ForeignKey("AWSCostEntryBill", on_delete=models.CASCADE)
    cost_entry_product = models.ForeignKey("AWSCostEntryProduct", on_delete=models.SET_NULL, null=True)
    cost_entry_pricing = models.ForeignKey("AWSCostEntryPricing", on_delete=models.SET_NULL, null=True)
    cost_entry_reservation = models.ForeignKey("AWSCostEntryReservation", on_delete=models.SET_NULL, null=True)

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

    id = models.BigAutoField(primary_key=True)

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
    resource_ids = ArrayField(models.CharField(max_length=256), null=True)
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
    public_on_demand_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    public_on_demand_rate = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    tax_type = models.TextField(null=True)
    tags = JSONField(null=True)


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


class AWSTagsSummary(models.Model):
    """A collection of all current existing tag key and values."""

    class Meta:
        """Meta for OCPUsageTagSummary."""

        db_table = "reporting_awstags_summary"
        unique_together = ("key", "cost_entry_bill")

    id = models.BigAutoField(primary_key=True)

    key = models.CharField(max_length=253)
    values = ArrayField(models.CharField(max_length=253))
    cost_entry_bill = models.ForeignKey("AWSCostEntryBill", on_delete=models.CASCADE)
    accounts = ArrayField(models.CharField(max_length=63))


# Materialized Views for UI Reporting
class AWSCostSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost.

    """

    class Meta:
        """Meta for AWSCostSummary."""

        db_table = "reporting_aws_cost_summary"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    currency_code = models.CharField(max_length=10)


class AWSCostSummaryByService(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by service.

    """

    class Meta:
        """Meta for AWSCostSummaryByService."""

        db_table = "reporting_aws_cost_summary_by_service"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    product_code = models.CharField(max_length=50, null=False)

    product_family = models.CharField(max_length=150, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    currency_code = models.CharField(max_length=10)


class AWSCostSummaryByAccount(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by account.

    """

    class Meta:
        """Meta for AWSCostSummaryByService."""

        db_table = "reporting_aws_cost_summary_by_account"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    currency_code = models.CharField(max_length=10)


class AWSCostSummaryByRegion(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by region.

    """

    class Meta:
        """Meta for AWSCostSummaryByService."""

        db_table = "reporting_aws_cost_summary_by_region"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    region = models.CharField(max_length=50, null=True)

    availability_zone = models.CharField(max_length=50, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    currency_code = models.CharField(max_length=10)


class AWSComputeSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class Meta:
        """Meta for AWSComputeSummary."""

        db_table = "reporting_aws_compute_summary"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    instance_type = models.CharField(max_length=50, null=True)

    resource_ids = ArrayField(models.CharField(max_length=256), null=True)

    resource_count = models.IntegerField(null=True)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    currency_code = models.CharField(max_length=10)


class AWSComputeSummaryByService(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of compute usage by service and instance type.

    """

    class Meta:
        """Meta for AWSComputeSummaryByService."""

        db_table = "reporting_aws_compute_summary_by_service"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    product_code = models.CharField(max_length=50, null=False)

    product_family = models.CharField(max_length=150, null=True)

    instance_type = models.CharField(max_length=50, null=True)

    resource_ids = ArrayField(models.CharField(max_length=256), null=True)

    resource_count = models.IntegerField(null=True)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    currency_code = models.CharField(max_length=10)


class AWSComputeSummaryByAccount(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by service and instance type.

    """

    class Meta:
        """Meta for AWSComputeSummaryByAccount."""

        db_table = "reporting_aws_compute_summary_by_account"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)

    instance_type = models.CharField(max_length=50, null=True)

    resource_ids = ArrayField(models.CharField(max_length=256), null=True)

    resource_count = models.IntegerField(null=True)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    currency_code = models.CharField(max_length=10)


class AWSComputeSummaryByRegion(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by service and instance type.

    """

    class Meta:
        """Meta for AWSComputeSummaryByRegion."""

        db_table = "reporting_aws_compute_summary_by_region"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    region = models.CharField(max_length=50, null=True)

    availability_zone = models.CharField(max_length=50, null=True)

    instance_type = models.CharField(max_length=50, null=True)

    resource_ids = ArrayField(models.CharField(max_length=256), null=True)

    resource_count = models.IntegerField(null=True)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    currency_code = models.CharField(max_length=10)


class AWSStorageSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of storage usage.

    """

    class Meta:
        """Meta for AWSStorageSummary."""

        db_table = "reporting_aws_storage_summary"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    product_family = models.CharField(max_length=150, null=True)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    currency_code = models.CharField(max_length=10)


class AWSStorageSummaryByService(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of storage usage by service.

    """

    class Meta:
        """Meta for AWSStorageSummary."""

        db_table = "reporting_aws_storage_summary_by_service"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    product_code = models.CharField(max_length=50, null=False)

    product_family = models.CharField(max_length=150, null=True)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    currency_code = models.CharField(max_length=10)


class AWSStorageSummaryByAccount(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of storage by account.

    """

    class Meta:
        """Meta for AWSStorageSummaryByAccount."""

        db_table = "reporting_aws_storage_summary_by_account"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    usage_account_id = models.CharField(max_length=50, null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.SET_NULL, null=True)

    product_family = models.CharField(max_length=150, null=True)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    currency_code = models.CharField(max_length=10)


class AWSStorageSummaryByRegion(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by service and instance type.

    """

    class Meta:
        """Meta for AWSStorageSummaryByRegion."""

        db_table = "reporting_aws_storage_summary_by_region"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    region = models.CharField(max_length=50, null=True)

    availability_zone = models.CharField(max_length=50, null=True)

    product_family = models.CharField(max_length=150, null=True)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    currency_code = models.CharField(max_length=10)


class AWSNetworkSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of network usage.

    """

    class Meta:
        """Meta for AWSNetworkSummary."""

        db_table = "reporting_aws_network_summary"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    product_code = models.CharField(max_length=50, null=False)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    currency_code = models.CharField(max_length=10)


class AWSDatabaseSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of database usage.

    """

    class Meta:
        """Meta for AWSDatabaseSummary."""

        db_table = "reporting_aws_database_summary"
        managed = False

    id = models.IntegerField(primary_key=True)

    usage_start = models.DateField(null=False)

    usage_end = models.DateField(null=False)

    product_code = models.CharField(max_length=50, null=False)

    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    unit = models.CharField(max_length=63, null=True)

    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)

    currency_code = models.CharField(max_length=10)


class AWSOrganizationalUnit(models.Model):
    """The alias table for AWS Organizational Unit."""

    org_unit_name = models.CharField(max_length=250, null=False, unique=False)

    org_unit_id = models.CharField(max_length=50, null=False, unique=False)

    org_unit_path = models.TextField(null=False, unique=False)

    level = models.PositiveSmallIntegerField(null=False)

    account_alias = models.ForeignKey("AWSAccountAlias", on_delete=models.PROTECT, null=True)

    created_timestamp = models.DateField(auto_now_add=True)

    deleted_timestamp = models.DateField(null=True)

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
