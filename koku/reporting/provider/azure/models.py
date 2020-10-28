#
# Copyright 2019 Red Hat, Inc.
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
"""Models for Azure cost and usage entry tables."""
from uuid import uuid4

from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import JSONField


PRESTO_LINE_ITEM_TABLE = "azure_line_items"

VIEWS = (
    "reporting_azure_compute_summary",
    "reporting_azure_cost_summary",
    "reporting_azure_cost_summary_by_account",
    "reporting_azure_cost_summary_by_location",
    "reporting_azure_cost_summary_by_service",
    "reporting_azure_database_summary",
    "reporting_azure_network_summary",
    "reporting_azure_storage_summary",
)


class AzureCostEntryBill(models.Model):
    """The billing information for a Cost Usage Report.

    The billing period (1 month) will cover many cost entries.

    """

    class Meta:
        """Meta for AzureCostEntryBill."""

        unique_together = ("billing_period_start", "provider")

    billing_period_start = models.DateTimeField(null=False)
    billing_period_end = models.DateTimeField(null=False)
    summary_data_creation_datetime = models.DateTimeField(null=True)
    summary_data_updated_datetime = models.DateTimeField(null=True)
    finalized_datetime = models.DateTimeField(null=True)
    derived_cost_datetime = models.DateTimeField(null=True)

    provider = models.ForeignKey("api.Provider", on_delete=models.CASCADE)


class AzureCostEntryProductService(models.Model):
    """The Azure product identified in a cost entry line item."""

    class Meta:
        """Meta for AzureCostEntryProductService."""

        unique_together = ("instance_id", "instance_type", "service_tier", "service_name")

    instance_id = models.TextField(max_length=512, null=False)
    resource_location = models.TextField(null=True)
    consumed_service = models.TextField(null=True)
    resource_type = models.TextField(null=True)
    resource_group = models.TextField(null=True)
    additional_info = JSONField(null=True)
    service_tier = models.TextField(null=True)
    service_name = models.TextField(null=True)
    service_info1 = models.TextField(null=True)
    service_info2 = models.TextField(null=True)
    instance_type = models.TextField(null=True)

    provider = models.ForeignKey("api.Provider", on_delete=models.CASCADE, null=True)


class AzureMeter(models.Model):
    """The Azure meter."""

    meter_id = models.UUIDField(editable=False, unique=True, null=False)
    meter_name = models.TextField(null=False)
    meter_category = models.TextField(null=True)
    meter_subcategory = models.TextField(null=True)
    meter_region = models.TextField(null=True)
    resource_rate = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.TextField(null=True)
    unit_of_measure = models.TextField(null=True)

    provider = models.ForeignKey("api.Provider", on_delete=models.CASCADE, null=True)


class AzureCostEntryLineItemDaily(models.Model):
    """A line item in a cost entry.

    This identifies specific costs and usage of Azure resources.

    """

    class Meta:
        """Meta for AzureCostEntryLineItemDaily."""

        db_table = "reporting_azurecostentrylineitem_daily"

    id = models.BigAutoField(primary_key=True)
    cost_entry_bill = models.ForeignKey("AzureCostEntryBill", on_delete=models.CASCADE)
    cost_entry_product = models.ForeignKey("AzureCostEntryProductService", on_delete=models.SET_NULL, null=True)
    meter = models.ForeignKey("AzureMeter", on_delete=models.SET_NULL, null=True)
    subscription_guid = models.TextField(null=False)
    tags = JSONField(null=True)
    usage_date = models.DateField(null=False)
    usage_quantity = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    pretax_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)


class AzureCostEntryLineItemDailySummary(models.Model):
    """A line item in a cost entry.

    This identifies specific costs and usage of Azure resources.

    """

    class Meta:
        """Meta for AzureCostEntryLineItemDailySummary."""

        managed = False

        db_table = "reporting_azurecostentrylineitem_daily_summary"
        indexes = [models.Index(fields=["usage_start"], name="ix_azurecstentrydlysumm_start")]
        # A GIN functional index named "ix_azure_costentrydlysumm_service_name" was created manually
        # via RunSQL migration operation
        # Function: (upper(service_name) gin_trgm_ops)

    uuid = models.UUIDField(primary_key=True)
    cost_entry_bill = models.ForeignKey("AzureCostEntryBill", on_delete=models.CASCADE)
    meter = models.ForeignKey("AzureMeter", on_delete=models.SET_NULL, null=True)
    subscription_guid = models.TextField(null=False)
    instance_type = models.TextField(null=True)
    service_name = models.TextField(null=True)
    resource_location = models.TextField(null=True)
    tags = JSONField(null=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=True)
    usage_quantity = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    pretax_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.TextField(null=True)
    instance_ids = ArrayField(models.TextField(), null=True)
    instance_count = models.IntegerField(null=True)
    unit_of_measure = models.TextField(null=True)
    source_uuid = models.UUIDField(unique=False, null=True)


class AzureTagsValues(models.Model):
    class Meta:
        """Meta for AzureTagsValues."""

        db_table = "reporting_azuretags_values"
        unique_together = ("key", "value")
        indexes = [models.Index(fields=["key"], name="azure_tags_value_key_idx")]

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    key = models.TextField()
    value = models.TextField()
    subscription_guids = ArrayField(models.TextField())


class AzureTagsSummary(models.Model):
    """A collection of all current existing tag key and values."""

    class Meta:
        """Meta for AzureTagsSummary."""

        db_table = "reporting_azuretags_summary"
        unique_together = ("key", "cost_entry_bill", "subscription_guid")

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    key = models.TextField()
    values = ArrayField(models.TextField())
    cost_entry_bill = models.ForeignKey("AzureCostEntryBill", on_delete=models.CASCADE)
    subscription_guid = models.TextField(null=True)


# Materialized Views for UI Reporting
class AzureCostSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost.

    """

    class Meta:
        """Meta for AzureCostSummary."""

        db_table = "reporting_azure_cost_summary"
        managed = False

    id = models.IntegerField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    pretax_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.TextField(null=True)
    source_uuid = models.UUIDField(unique=False, null=True)


class AzureCostSummaryByAccount(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by account.

    """

    class Meta:
        """Meta for AzureCostSummaryByService."""

        db_table = "reporting_azure_cost_summary_by_account"
        managed = False

    id = models.IntegerField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    subscription_guid = models.TextField(null=False)
    pretax_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.TextField(null=True)
    source_uuid = models.UUIDField(unique=False, null=True)


class AzureCostSummaryByLocation(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by location.

    """

    class Meta:
        """Meta for AzureCostSummaryByService."""

        db_table = "reporting_azure_cost_summary_by_location"
        managed = False

    id = models.IntegerField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    subscription_guid = models.TextField(null=False)
    resource_location = models.TextField(null=True)
    pretax_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.TextField(null=True)
    source_uuid = models.UUIDField(unique=False, null=True)


class AzureCostSummaryByService(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of total cost by service.

    """

    class Meta:
        """Meta for AzureCostSummaryByService."""

        db_table = "reporting_azure_cost_summary_by_service"
        managed = False

    id = models.IntegerField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    subscription_guid = models.TextField(null=False)
    service_name = models.TextField(null=False)
    pretax_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.TextField(null=True)
    source_uuid = models.UUIDField(unique=False, null=True)


class AzureComputeSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of compute usage.

    """

    class Meta:
        """Meta for AzureComputeSummary."""

        db_table = "reporting_azure_compute_summary"
        managed = False

    id = models.IntegerField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    subscription_guid = models.TextField(null=False)
    instance_type = models.TextField(null=True)
    instance_ids = ArrayField(models.TextField(), null=True)
    instance_count = models.IntegerField(null=True)
    usage_quantity = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit_of_measure = models.TextField(null=True)
    pretax_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.TextField(null=True)
    source_uuid = models.UUIDField(unique=False, null=True)


class AzureStorageSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of storage usage.

    """

    class Meta:
        """Meta for AzureStorageSummary."""

        db_table = "reporting_azure_storage_summary"
        managed = False

    id = models.IntegerField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    subscription_guid = models.TextField(null=False)
    service_name = models.TextField(null=False)
    usage_quantity = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit_of_measure = models.TextField(null=True)
    pretax_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.TextField(null=True)
    source_uuid = models.UUIDField(unique=False, null=True)


class AzureNetworkSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of network usage.

    """

    class Meta:
        """Meta for AzureNetworkSummary."""

        db_table = "reporting_azure_network_summary"
        managed = False

    id = models.IntegerField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    subscription_guid = models.TextField(null=False)
    service_name = models.TextField(null=False)
    usage_quantity = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit_of_measure = models.TextField(null=True)
    pretax_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.TextField(null=True)
    source_uuid = models.UUIDField(unique=False, null=True)


class AzureDatabaseSummary(models.Model):
    """A MATERIALIZED VIEW specifically for UI API queries.

    This table gives a daily breakdown of database usage.

    """

    class Meta:
        """Meta for AzureDatabaseSummary."""

        db_table = "reporting_azure_database_summary"
        managed = False

    id = models.IntegerField(primary_key=True)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)
    subscription_guid = models.TextField(null=False)
    service_name = models.TextField(null=False)
    usage_quantity = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    unit_of_measure = models.TextField(null=True)
    pretax_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.TextField(null=True)
    source_uuid = models.UUIDField(unique=False, null=True)


class AzureEnabledTagKeys(models.Model):
    """A collection of the current enabled tag keys."""

    class Meta:
        """Meta for AzureEnabledTagKeys."""

        db_table = "reporting_azureenabledtagkeys"

    id = models.BigAutoField(primary_key=True)
    key = models.CharField(max_length=253, unique=True)
