"""Models for GCP cost and usage entry tables."""
from django.db import models


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


class GCPCostEntryLineItemDaily(models.Model):
    """GCP cost entry daily line item."""

    class Meta:
        """Meta for GCPCostEntryLineItemDaily."""

        # unique_together = ("start_time", "line_item_type", "project")
        db_table = "reporting_gcpcostentrylineitemdaily"

    id = models.BigAutoField(primary_key=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    labels = models.CharField(max_length=256, null=True, blank=True)
    system_labels = models.CharField(max_length=256, null=True, blank=True)
    location = models.CharField(max_length=256, null=True, blank=True)
    country = models.CharField(max_length=256, null=True, blank=True)
    region = models.CharField(max_length=256, null=True, blank=True)
    zone = models.CharField(max_length=256, null=True, blank=True)
    export_time = models.CharField(max_length=256, null=True, blank=True)
    cost = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True)
    currency = models.CharField(max_length=256, null=True, blank=True)
    conversion_rate = models.CharField(max_length=256, null=True, blank=True)
    usage_amount = models.CharField(max_length=256, null=True, blank=True)
    usage_unit = models.CharField(max_length=256, null=True, blank=True)
    usage_to_pricing_units = models.CharField(max_length=256, null=True, blank=True)
    usage_pricing_unit = models.CharField(max_length=256, null=True, blank=True)
    credits = models.CharField(max_length=256, null=True, blank=True)
    invoice_month = models.CharField(max_length=256, null=True, blank=True)
    cost_type = models.CharField(max_length=256, null=True, blank=True)
    line_item_type = models.CharField(max_length=256, null=True)
    cost_entry_product = models.ForeignKey(GCPCostEntryProductService, null=True, on_delete=models.CASCADE)
    cost_entry_bill = models.ForeignKey(GCPCostEntryBill, on_delete=models.CASCADE)
    project = models.ForeignKey(GCPProject, on_delete=models.CASCADE)
