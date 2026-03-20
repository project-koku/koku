#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Django models for AWS line item tables (on-prem PostgreSQL storage)."""
from uuid import uuid4

from django.db import models


class AWSLineItemBase(models.Model):
    """Abstract base class for AWS line item tables.

    These models replace the raw SQL table creation for on-prem PostgreSQL storage.
    They provide:
    - Django migration support for schema evolution
    - Single-column date partitioning (usage_start) for efficient data management
    - Integration with existing PartitionedTable infrastructure
    """

    class Meta:
        abstract = True

    class PartitionInfo:
        partition_type = "RANGE"
        partition_cols = ["usage_start"]

    # UUID primary key for compatibility with SQLAlchemy to_sql and partitioned tables
    id = models.UUIDField(primary_key=True, default=uuid4)

    # Partition column - DateField for proper range partitioning (matches existing infrastructure)
    usage_start = models.DateField(null=True, db_index=True)

    # Partition-related columns (indexed, not partitioned in PostgreSQL)
    # source is stored as varchar to match Trino/parquet storage and existing SQL joins
    source = models.CharField(max_length=64, null=True, db_index=True)
    year = models.CharField(max_length=4, null=True)
    month = models.CharField(max_length=2, null=True)

    # Manifest tracking (AWS uses manifestid instead of reportnumhours)
    manifestid = models.CharField(max_length=256, null=True)

    # AWS billing columns
    bill_payeraccountid = models.CharField(max_length=50, null=True)
    bill_billingentity = models.CharField(max_length=50, null=True)
    bill_billingperiodstartdate = models.DateTimeField(null=True)
    bill_billingperiodenddate = models.DateTimeField(null=True)
    bill_billtype = models.TextField(null=True)
    bill_invoiceid = models.TextField(null=True)

    # Identity columns
    identity_timeinterval = models.TextField(null=True)

    # Line item identification
    lineitem_usagestartdate = models.DateTimeField(null=True, db_index=True)
    lineitem_usageenddate = models.DateTimeField(null=True)
    lineitem_productcode = models.CharField(max_length=256, null=True)
    lineitem_usageaccountid = models.CharField(max_length=50, null=True)
    lineitem_availabilityzone = models.CharField(max_length=50, null=True)
    lineitem_resourceid = models.CharField(max_length=256, null=True)
    lineitem_lineitemtype = models.CharField(max_length=50, null=True)
    lineitem_lineitemdescription = models.TextField(null=True)
    lineitem_legalentity = models.CharField(max_length=256, null=True)
    lineitem_usagetype = models.TextField(null=True)
    lineitem_operation = models.TextField(null=True)
    lineitem_taxtype = models.TextField(null=True)

    # Usage metrics
    lineitem_usageamount = models.FloatField(null=True)
    lineitem_normalizationfactor = models.FloatField(null=True)
    lineitem_normalizedusageamount = models.FloatField(null=True)

    # Cost metrics
    lineitem_currencycode = models.CharField(max_length=10, null=True)
    lineitem_unblendedrate = models.FloatField(null=True)
    lineitem_unblendedcost = models.FloatField(null=True)
    lineitem_blendedrate = models.FloatField(null=True)
    lineitem_blendedcost = models.FloatField(null=True)

    # Product details
    product_productfamily = models.CharField(max_length=150, null=True)
    product_region = models.CharField(max_length=50, null=True)
    product_instancetype = models.CharField(max_length=50, null=True)
    product_productname = models.CharField(max_length=256, null=True)
    product_physicalcores = models.CharField(max_length=50, null=True)
    product_vcpu = models.CharField(max_length=50, null=True)
    product_memory = models.TextField(null=True)
    product_operatingsystem = models.TextField(null=True)
    product_servicecode = models.TextField(null=True)
    product_sku = models.TextField(null=True)

    # Pricing
    pricing_unit = models.TextField(null=True)
    pricing_publicondemandcost = models.FloatField(null=True)
    pricing_publicondemandrate = models.FloatField(null=True)
    pricing_term = models.TextField(null=True)

    # Savings plan
    savingsplan_savingsplaneffectivecost = models.FloatField(null=True)

    # Reservations
    reservation_amortizedupfrontcostforusage = models.TextField(null=True)
    reservation_amortizedupfrontfeeforbillingperiod = models.TextField(null=True)
    reservation_endtime = models.TextField(null=True)
    reservation_numberofreservations = models.TextField(null=True)
    reservation_recurringfeeforusage = models.TextField(null=True)
    reservation_starttime = models.TextField(null=True)
    reservation_unitsperreservation = models.TextField(null=True)
    reservation_unusedquantity = models.TextField(null=True)
    reservation_unusedrecurringfee = models.TextField(null=True)

    # Tags and cost categories (stored as JSON text)
    resourcetags = models.TextField(null=True)
    costcategory = models.TextField(null=True)

    # Row UUID for daily aggregation tracking
    row_uuid = models.TextField(null=True)


class AWSLineItem(AWSLineItemBase):
    """Model for aws_line_items table (raw hourly data)."""

    class Meta:
        db_table = "aws_line_items"
        indexes = [
            models.Index(fields=["source", "year", "month"], name="aws_li_src_yr_mo_idx"),
        ]


class AWSLineItemDaily(AWSLineItemBase):
    """Model for aws_line_items_daily table (aggregated daily data)."""

    class Meta:
        db_table = "aws_line_items_daily"
        indexes = [
            models.Index(fields=["source", "year", "month"], name="aws_li_daily_src_yr_mo_idx"),
        ]


# Mapping from table type to Django model (for self-hosted/on-prem PostgreSQL)
# AWS only has one "report type" unlike OCP which has pod_usage, storage_usage, etc.
SELF_HOSTED_MODEL_MAP = {
    "aws_line_items": AWSLineItem,
}

SELF_HOSTED_DAILY_MODEL_MAP = {
    "aws_line_items": AWSLineItemDaily,
}


def get_self_hosted_models():
    """Get all self-hosted models (raw and daily).

    Returns a list of all Django models used for self-hosted/on-prem data storage.
    Used for cleanup operations like source deletion and expired data removal.
    """
    models_list = list(SELF_HOSTED_MODEL_MAP.values())
    models_list.extend(SELF_HOSTED_DAILY_MODEL_MAP.values())
    return models_list


def get_self_hosted_table_names():
    """Get table names for all self-hosted models.

    Returns a list of database table names for partition cleanup operations.
    """
    return [model._meta.db_table for model in get_self_hosted_models()]
