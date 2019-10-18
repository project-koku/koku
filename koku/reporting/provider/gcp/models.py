"""Models for GCP cost and usage entry tables."""
from django.db import models

from api.provider.models import Provider


class GCPCostEntryBill(models.Model):
    """The billing information for a Cost Usage Report.

    The billing period (1 month) will cover many cost entries.

    """

    class Meta:
        """Meta for GCPCostEntryBill."""

        unique_together = ('billing_period_start', 'provider')

    billing_period_start = models.DateTimeField(null=False)
    billing_period_end = models.DateTimeField(null=False)
    summary_data_creation_datetime = models.DateTimeField(null=True)
    summary_data_updated_datetime = models.DateTimeField(null=True)
    finalized_datetime = models.DateTimeField(null=True)
    derived_cost_datetime = models.DateTimeField(null=True)

    provider = models.ForeignKey(Provider, null=True, on_delete=models.CASCADE)


class GCPProject(models.Model):
    """The per Project information for GCP."""

    account_id = models.CharField(max_length=20)
    project_number = models.BigIntegerField()
    project_id = models.CharField(null=False, unique=True, max_length=256)
    project_name = models.CharField(max_length=256)
    project_labels = models.CharField(max_length=256)


class GCPCostEntryLineItemDaily(models.Model):
    """GCP cost entry daily line item."""

    line_item_type = models.CharField(max_length=256)
    cost_entry_bill = models.ForeignKey(
        GCPCostEntryBill, on_delete=models.PROTECT)
    project = models.ForeignKey(GCPProject, on_delete=models.PROTECT)
    measurement_type = models.CharField(max_length=512, null=False)
    consumption = models.BigIntegerField()
    unit = models.CharField(max_length=63, null=True)
    cost = models.DecimalField(max_digits=17, decimal_places=9,
                               null=True)
    currency = models.CharField(max_length=10, null=False)
    description = models.CharField(max_length=256,)
    start_time = models.DateTimeField(null=False)
    end_time = models.DateTimeField(null=False)
