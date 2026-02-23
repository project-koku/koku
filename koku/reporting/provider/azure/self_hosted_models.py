#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Django models for Azure line item tables (on-prem PostgreSQL storage)."""
from uuid import uuid4

from django.db import models


class AzureLineItem(models.Model):
    """Model for azure_line_items table.

    Azure uses a single table for both raw and daily data (no separate daily table).
    This model replaces the raw SQL table creation for on-prem PostgreSQL storage.
    """

    class Meta:
        db_table = "azure_line_items"
        indexes = [
            models.Index(fields=["source", "year", "month"], name="azure_li_src_yr_mo_idx"),
        ]

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    # UUID primary key for compatibility with SQLAlchemy to_sql and partitioned tables
    id = models.UUIDField(primary_key=True, default=uuid4)

    # Partition column - DateField for proper range partitioning
    usage_start = models.DateField(null=True, db_index=True)

    # Partition-related columns
    source = models.CharField(max_length=64, null=True, db_index=True)
    year = models.CharField(max_length=4, null=True)
    month = models.CharField(max_length=2, null=True)

    # Manifest tracking
    manifestid = models.CharField(max_length=256, null=True)

    # Azure billing columns
    billingperiodstartdate = models.DateTimeField(null=True)
    billingperiodenddate = models.DateTimeField(null=True)
    billingaccountid = models.CharField(max_length=256, null=True)
    billingaccountname = models.CharField(max_length=256, null=True)
    billingprofileid = models.CharField(max_length=256, null=True)
    billingprofilename = models.CharField(max_length=256, null=True)
    billingcurrencycode = models.CharField(max_length=20, null=True)
    billingcurrency = models.CharField(max_length=20, null=True)

    # Date and usage columns
    date = models.DateTimeField(null=True, db_index=True)
    quantity = models.FloatField(null=True)
    unitofmeasure = models.CharField(max_length=256, null=True)
    unitprice = models.FloatField(null=True)

    # Cost columns
    costinbillingcurrency = models.FloatField(null=True)
    effectiveprice = models.FloatField(null=True)
    paygprice = models.FloatField(null=True)
    resourcerate = models.FloatField(null=True)

    # Subscription columns
    subscriptionguid = models.CharField(max_length=256, null=True)
    subscriptionid = models.CharField(max_length=256, null=True)
    subscriptionname = models.CharField(max_length=256, null=True)

    # Resource columns
    resourcegroup = models.CharField(max_length=256, null=True)
    resourceid = models.TextField(null=True)
    resourcelocation = models.CharField(max_length=256, null=True)
    resourcename = models.CharField(max_length=256, null=True)
    resourcetype = models.CharField(max_length=256, null=True)

    # Service columns
    servicename = models.CharField(max_length=256, null=True)
    servicefamily = models.CharField(max_length=256, null=True)
    servicetier = models.CharField(max_length=256, null=True)
    serviceinfo1 = models.TextField(null=True)
    serviceinfo2 = models.TextField(null=True)
    consumedservice = models.CharField(max_length=256, null=True)

    # Meter columns
    metercategory = models.CharField(max_length=256, null=True)
    meterid = models.CharField(max_length=256, null=True)
    metername = models.CharField(max_length=256, null=True)
    meterregion = models.CharField(max_length=256, null=True)
    metersubcategory = models.CharField(max_length=256, null=True)

    # Product columns
    productname = models.CharField(max_length=256, null=True)
    productorderid = models.CharField(max_length=256, null=True)
    productordername = models.CharField(max_length=256, null=True)

    # Other columns
    accountname = models.CharField(max_length=256, null=True)
    accountownerid = models.CharField(max_length=256, null=True)
    additionalinfo = models.TextField(null=True)
    availabilityzone = models.CharField(max_length=256, null=True)
    chargetype = models.CharField(max_length=256, null=True)
    costcenter = models.CharField(max_length=256, null=True)
    frequency = models.CharField(max_length=256, null=True)
    invoicesectionid = models.CharField(max_length=256, null=True)
    invoicesectionname = models.CharField(max_length=256, null=True)
    isazurecrediteligible = models.CharField(max_length=10, null=True)
    offerid = models.CharField(max_length=256, null=True)
    partnumber = models.CharField(max_length=256, null=True)
    planname = models.CharField(max_length=256, null=True)
    pricingmodel = models.CharField(max_length=256, null=True)
    publishername = models.CharField(max_length=256, null=True)
    publishertype = models.CharField(max_length=256, null=True)
    reservationid = models.CharField(max_length=256, null=True)
    reservationname = models.CharField(max_length=256, null=True)
    term = models.CharField(max_length=256, null=True)

    # Tags (stored as JSON text)
    tags = models.TextField(null=True)

    # Invoice columns
    invoiceid = models.TextField(null=True)
    previousinvoiceid = models.TextField(null=True)

    # Reseller columns
    resellername = models.TextField(null=True)
    resellermpnid = models.TextField(null=True)

    # Additional cost columns
    costinpricingcurrency = models.TextField(null=True)
    costinusd = models.TextField(null=True)
    marketprice = models.TextField(null=True)
    paygcostinbillingcurrency = models.TextField(null=True)
    paygcostinusd = models.TextField(null=True)
    pricingcurrency = models.TextField(null=True)
    pricingcurrencycode = models.TextField(null=True)

    # Exchange rate columns
    exchangerate = models.TextField(null=True)
    exchangeratedate = models.TextField(null=True)
    exchangeratepricingtobilling = models.TextField(null=True)

    # Additional product columns
    productid = models.TextField(null=True)
    product = models.TextField(null=True)
    publisherid = models.TextField(null=True)

    # Additional resource column
    instancename = models.TextField(null=True)

    # Additional location column
    location = models.TextField(null=True)

    # Service period columns
    serviceperiodstartdate = models.TextField(null=True)
    serviceperiodenddate = models.TextField(null=True)

    # Row UUID for deduplication
    row_uuid = models.TextField(null=True)


# Azure uses the same table for raw and daily data
SELF_HOSTED_MODEL_MAP = {
    "azure_line_items": AzureLineItem,
}

SELF_HOSTED_DAILY_MODEL_MAP = {
    "azure_line_items": AzureLineItem,
}


def get_self_hosted_models():
    """Get all self-hosted models.

    Returns a list of all Django models used for self-hosted/on-prem data storage.
    """
    return [AzureLineItem]


def get_self_hosted_table_names():
    """Get table names for all self-hosted models."""
    return [model._meta.db_table for model in get_self_hosted_models()]
