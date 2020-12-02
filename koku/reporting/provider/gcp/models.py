#
# Copyright 2020 Red Hat, Inc.
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
"""Models for GCP cost and usage entry tables."""
from uuid import uuid4

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import JSONField


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
    tags = JSONField(null=True)
    usage_type = models.CharField(max_length=50, null=True)
    location = models.CharField(max_length=256, null=True, blank=True)
    country = models.CharField(max_length=256, null=True, blank=True)
    region = models.CharField(max_length=256, null=True, blank=True)
    zone = models.CharField(max_length=256, null=True, blank=True)
    export_time = models.CharField(max_length=256, null=True, blank=True)
    cost = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True)
    currency = models.CharField(max_length=256, null=True, blank=True)
    conversion_rate = models.CharField(max_length=256, null=True, blank=True)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    usage_unit = models.CharField(max_length=256, null=True, blank=True)
    usage_to_pricing_units = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    usage_pricing_unit = models.CharField(max_length=256, null=True, blank=True)
    credits = models.CharField(max_length=256, null=True, blank=True)
    invoice_month = models.CharField(max_length=256, null=True, blank=True)
    cost_type = models.CharField(max_length=256, null=True, blank=True)
    line_item_type = models.CharField(max_length=256, null=True)
    cost_entry_product = models.ForeignKey(GCPCostEntryProductService, null=True, on_delete=models.CASCADE)
    cost_entry_bill = models.ForeignKey(GCPCostEntryBill, on_delete=models.CASCADE)
    project = models.ForeignKey(GCPProject, on_delete=models.CASCADE)


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
    cost = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True)
    currency = models.CharField(max_length=256, null=True, blank=True)
    conversion_rate = models.CharField(max_length=256, null=True, blank=True)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    usage_unit = models.CharField(max_length=256, null=True, blank=True)
    usage_to_pricing_units = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    usage_pricing_unit = models.CharField(max_length=256, null=True, blank=True)
    invoice_month = models.CharField(max_length=256, null=True, blank=True)
    tax_type = models.CharField(max_length=256, null=True, blank=True)


class GCPCostEntryLineItemDailySummary(models.Model):
    """A daily aggregation of line items.

    This table is aggregated by service, and does not
    have a breakdown by resource or tags. The contents of this table
    should be considered ephemeral. It will be regularly deleted from
    and repopulated.

    """

    class Meta:
        """Meta for GCPCostEntryLineItemDailySummary."""

        managed = False  # for partitioning

        db_table = "reporting_gcpcostentrylineitem_daily_summary"
        indexes = [
            models.Index(fields=["usage_start"], name="gcp_summary_usage_start_idx"),
            models.Index(fields=["instance_type"], name="gcp_summary_instance_type_idx"),
            GinIndex(fields=["tags"], name="gcp_tags_idx"),
            models.Index(fields=["project"], name="gcp_summary_project_idx"),
            models.Index(fields=["cost_entry_product"], name="gcp_summary_product_idx"),
        ]

    uuid = models.UUIDField(primary_key=True)

    cost_entry_bill = models.ForeignKey(GCPCostEntryBill, on_delete=models.CASCADE)

    # The following fields are used for grouping
    cost_entry_product = models.ForeignKey(GCPCostEntryProductService, null=True, on_delete=models.CASCADE)
    project = models.ForeignKey(GCPProject, on_delete=models.CASCADE)
    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=True)
    region = models.CharField(max_length=50, null=True)
    instance_type = models.CharField(max_length=50, null=True)
    unit = models.CharField(max_length=63, null=True)
    line_item_type = models.CharField(max_length=256, null=True)
    usage_amount = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10)

    # The following fields are aggregates
    unblended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    tags = JSONField(null=True)
    source_uuid = models.UUIDField(unique=False, null=True)

    # TODO: I am not sure if these are needed or just aws specific. I went ahead
    # commented them out in case we need them.
    # unblended_rate = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    # blended_rate = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    # blended_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)


class GCPEnabledTagKeys(models.Model):
    """A collection of the current enabled tag keys."""

    class Meta:
        """Meta for AWSEnabledTagKeys."""

        db_table = "reporting_gcpenabledtagkeys"

    id = models.BigAutoField(primary_key=True)
    key = models.CharField(max_length=253, unique=True)


class GCPTagsSummary(models.Model):
    """A collection of all current existing tag key and values."""

    class Meta:
        """Meta for GCPTagSummary."""

        db_table = "reporting_gcptags_summary"
        unique_together = ("key", "cost_entry_bill", "project")

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    key = models.TextField()
    values = ArrayField(models.TextField())
    cost_entry_bill = models.ForeignKey("GCPCostEntryBill", on_delete=models.CASCADE)
    project = models.ForeignKey(GCPProject, on_delete=models.CASCADE)


class GCPTagsValues(models.Model):
    class Meta:
        """Meta for GCPTagsValues."""

        db_table = "reporting_gcptags_values"
        unique_together = ("key", "value")
        indexes = [models.Index(fields=["key"], name="gcp_tags_value_key_idx")]

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    key = models.TextField()
    value = models.TextField()
    project_ids = ArrayField(models.TextField())
