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

"""Models for cost entry tables."""

from django.contrib.postgres.fields import JSONField
from django.db import models


class AWSCostEntryBill(models.Model):
    """The billing information for a Cost Usage Report.

    The billing period (1 month) will cover many cost entries.

    """

    billing_resource = models.CharField(max_length=50, default='aws',
                                        null=False)
    bill_type = models.CharField(max_length=50, null=False)
    payer_account_id = models.CharField(max_length=50, null=False)
    billing_period_start = models.DateTimeField(null=False)
    billing_period_end = models.DateTimeField(null=False)


class AWSCostEntry(models.Model):
    """A Cost Entry for an AWS Cost Usage Report.

    A cost entry covers a specific time interval (i.e. 1 hour).

    """

    interval_start = models.DateTimeField(null=False)
    interval_end = models.DateTimeField(null=False)

    bill = models.ForeignKey('AWSCostEntryBill', on_delete=models.PROTECT)


class AWSCostEntryLineItem(models.Model):
    """A line item in a cost entry.

    This identifies specific costs and usage of AWS resources.

    """

    id = models.BigAutoField(primary_key=True)

    cost_entry = models.ForeignKey('AWSCostEntry',
                                   on_delete=models.PROTECT)
    cost_entry_bill = models.ForeignKey('AWSCostEntryBill',
                                        on_delete=models.PROTECT)
    cost_entry_product = models.ForeignKey('AWSCostEntryProduct',
                                           on_delete=models.PROTECT)
    cost_entry_pricing = models.ForeignKey('AWSCostEntryPricing',
                                           on_delete=models.PROTECT)
    cost_entry_reservation = models.ForeignKey('AWSCostEntryReservation',
                                               on_delete=models.PROTECT)

    # There is a many-to-many relationship between line-items and tags.
    # Want to try JSON to avoid having to check if tags exist in the database
    # for every line item we add.
    tags = JSONField()

    # Invoice ID is null until the bill is finalized
    invoice_id = models.CharField(max_length=63)
    line_item_type = models.CharField(max_length=50, null=False)
    usage_account_id = models.CharField(max_length=50, null=False)
    usage_start = models.DateTimeField(null=False)
    usage_end = models.DateTimeField(null=False)
    product_code = models.CharField(max_length=50, null=False)
    usage_type = models.CharField(max_length=50, null=False)
    operation = models.CharField(max_length=50)
    availability_zone = models.CharField(max_length=50)
    resource_id = models.CharField(max_length=50)
    usage_amount = models.PositiveIntegerField()
    normalization_factor = models.PositiveIntegerField()
    normalized_usage_amount = models.PositiveIntegerField()
    currency_code = models.CharField(max_length=10)
    unblended_rate = models.FloatField()
    unblended_cost = models.FloatField()
    blended_rate = models.FloatField()
    blended_cost = models.FloatField()
    tax_type = models.TextField()


class AWSCostEntryPricing(models.Model):
    """Pricing information for a cost entry line item."""

    line_item = models.ForeignKey('AWSCostEntryLineItem',
                                  on_delete=models.PROTECT)
    public_on_demand_cost = models.FloatField()
    public_on_demand_rate = models.FloatField()
    term = models.CharField(max_length=50)
    unit = models.CharField(max_length=24)


class AWSCostEntryProduct(models.Model):
    """The AWS product identified in a cost entry line item."""

    # AWS unique identifier for the product
    sku = models.CharField(max_length=128, null=False, unique=True)
    product_name = models.CharField(max_length=63, null=False)
    product_family = models.CharField(max_length=150)
    service_code = models.CharField(max_length=50)
    region = models.CharField(max_length=50)
    # The following fields are useful for EC2 instances
    instance_type = models.CharField(max_length=50)
    memory = models.PositiveIntegerField()
    vcpu = models.PositiveIntegerField()


class AWSCostEntryReservation(models.Model):
    """Information on a particular reservation in the AWS account."""

    reservation_arn = models.TextField(unique=True)
    availability_zone = models.CharField(max_length=50)
    number_of_reservations = models.PositiveIntegerField()
    units_per_reservation = models.PositiveIntegerField()
    amortized_upfront_fee = models.FloatField()
    amortized_upfront_cost_for_usage = models.FloatField()
    recurring_fee_for_usage = models.FloatField()
    # Unused fields more useful for later predictions.
    unused_quantity = models.PositiveIntegerField()
    unused_recurring_fee = models.FloatField()
