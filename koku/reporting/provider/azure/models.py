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

from django.contrib.postgres.fields import ArrayField, JSONField
from django.db import models


class AzureCostEntryBill(models.Model):
    """The billing information for a Cost Usage Report.

    The billing period (1 month) will cover many cost entries.

    """

    class Meta:
        """Meta for AzureCostEntryBill."""

        unique_together = ('billing_period_start', 'provider')

    billing_period_start = models.DateTimeField(null=False)
    billing_period_end = models.DateTimeField(null=False)
    summary_data_creation_datetime = models.DateTimeField(null=True)
    summary_data_updated_datetime = models.DateTimeField(null=True)
    finalized_datetime = models.DateTimeField(null=True)
    derived_cost_datetime = models.DateTimeField(null=True)

    provider = models.ForeignKey('api.Provider', on_delete=models.CASCADE)


class AzureCostEntryProductService(models.Model):
    """The Azure product identified in a cost entry line item."""

    class Meta:
        """Meta for AzureCostEntryProductService."""

        unique_together = ('instance_id', 'instance_type', 'service_tier', 'service_name')

    instance_id = models.CharField(max_length=512, null=False)
    resource_location = models.CharField(max_length=50, null=False)
    consumed_service = models.CharField(max_length=50, null=False)
    resource_type = models.CharField(max_length=50, null=False)
    resource_group = models.CharField(max_length=50, null=False)
    additional_info = JSONField(null=True)
    service_tier = models.CharField(max_length=50, null=False)
    service_name = models.CharField(max_length=50, null=False)
    service_info1 = models.TextField(null=True)
    service_info2 = models.TextField(null=True)
    instance_type = models.CharField(max_length=50, null=True)

    provider = models.ForeignKey('api.Provider', on_delete=models.CASCADE, null=True)


class AzureMeter(models.Model):
    """The Azure meter."""

    meter_id = models.UUIDField(editable=False, unique=True, null=False)
    meter_name = models.CharField(max_length=50, null=False)
    meter_category = models.CharField(max_length=50, null=True)
    meter_subcategory = models.CharField(max_length=50, null=True)
    meter_region = models.CharField(max_length=50, null=True)
    resource_rate = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    currency = models.CharField(max_length=10, null=False)
    unit_of_measure = models.CharField(max_length=63, null=True)

    provider = models.ForeignKey('api.Provider', on_delete=models.CASCADE, null=True)


class AzureCostEntryLineItemDaily(models.Model):
    """A line item in a cost entry.

    This identifies specific costs and usage of Azure resources.

    """

    class Meta:
        """Meta for AzureCostEntryLineItemDaily."""

        db_table = 'reporting_azurecostentrylineitem_daily'

    id = models.BigAutoField(primary_key=True)
    cost_entry_bill = models.ForeignKey('AzureCostEntryBill', on_delete=models.CASCADE)
    cost_entry_product = models.ForeignKey(
        'AzureCostEntryProductService', on_delete=models.SET_NULL, null=True
    )
    meter = models.ForeignKey('AzureMeter', on_delete=models.SET_NULL, null=True)
    subscription_guid = models.CharField(max_length=50, null=False)
    tags = JSONField(null=True)
    usage_date_time = models.DateTimeField(null=False)
    usage_quantity = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    pretax_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    offer_id = models.PositiveIntegerField(null=True)


class AzureCostEntryLineItemDailySummary(models.Model):
    """A line item in a cost entry.

    This identifies specific costs and usage of Azure resources.

    """

    class Meta:
        """Meta for AzureCostEntryLineItemDailySummary."""

        db_table = 'reporting_azurecostentrylineitem_daily_summary'

    id = models.BigAutoField(primary_key=True)
    cost_entry_bill = models.ForeignKey('AzureCostEntryBill', on_delete=models.CASCADE)
    meter = models.ForeignKey('AzureMeter', on_delete=models.SET_NULL, null=True)
    subscription_guid = models.CharField(max_length=50, null=False)
    instance_type = models.CharField(max_length=50, null=True)
    service_name = models.CharField(max_length=50, null=False)
    resource_location = models.CharField(max_length=50, null=False)
    tags = JSONField(null=True)
    usage_start = models.DateTimeField(null=False)
    usage_end = models.DateTimeField(null=True)
    usage_quantity = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    pretax_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    markup_cost = models.DecimalField(max_digits=24, decimal_places=9, null=True)
    offer_id = models.PositiveIntegerField(null=True)
    currency = models.CharField(max_length=10, null=False, default='USD')
    instance_ids = ArrayField(models.CharField(max_length=256), null=True)
    instance_count = models.IntegerField(null=True)
    unit_of_measure = models.CharField(max_length=63, null=True)


class AzureTagsSummary(models.Model):
    """A collection of all current existing tag key and values."""

    class Meta:
        """Meta for AzureTagsSummary."""

        db_table = 'reporting_azuretags_summary'

    key = models.CharField(primary_key=True, max_length=253)
    values = ArrayField(models.CharField(max_length=253))
