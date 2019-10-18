"""Models for GCP cost and usage entry tables."""
from django.db import models


class GCPCostEntryBill(models.Model):
    """The billing information for a Cost Usage Report.

    The billing period (1 month) will cover many cost entries.

    """

    class Meta:
        """Meta for GCPCostEntryBill."""

        unique_together = ('billing_period_start', 'provider_id')

    billing_period_start = models.DateTimeField()
    billing_period_end = models.DateTimeField()
    summary_data_creation_datetime = models.DateTimeField(null=True, blank=True)
    summary_data_updated_datetime = models.DateTimeField(null=True, blank=True)
    finalized_datetime = models.DateTimeField(null=True, blank=True)
    derived_cost_datetime = models.DateTimeField(null=True, blank=True)
    provider_id = models.IntegerField()


class GCPProject(models.Model):
    """The per Project information for GCP."""

    account_id = models.CharField(max_length=20)
    project_number = models.BigIntegerField()
    project_id = models.CharField(unique=True, max_length=256)
    project_name = models.CharField(max_length=256)
    project_labels = models.CharField(max_length=256, null=True, blank=True)


class GCPCostEntryLineItemDaily(models.Model):
    """GCP cost entry daily line item."""

    class Meta:
        """Meta for GCPCostEntryLineItemDaily."""

        unique_together = ('start_time', 'line_item_type', 'project')

    line_item_type = models.CharField(max_length=256)
    cost_entry_bill = models.ForeignKey(
        GCPCostEntryBill, on_delete=models.PROTECT)
    project = models.ForeignKey(GCPProject, on_delete=models.PROTECT)
    measurement_type = models.CharField(max_length=512)
    consumption = models.BigIntegerField()
    unit = models.CharField(max_length=63, null=True, blank=True)
    cost = models.DecimalField(max_digits=17, decimal_places=9,
                               null=True, blank=True)
    currency = models.CharField(max_length=10)
    description = models.CharField(max_length=256, null=True, blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
