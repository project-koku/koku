#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Django models for GCP line item tables (on-prem PostgreSQL storage)."""
from uuid import uuid4

from django.db import models


class GCPLineItemBase(models.Model):
    """Abstract base class for GCP line item tables.

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

    # Manifest tracking (GCP uses manifestid like AWS)
    manifestid = models.CharField(max_length=256, null=True)

    # GCP billing columns
    billing_account_id = models.CharField(max_length=256, null=True)
    project_id = models.CharField(max_length=256, null=True)
    project_name = models.CharField(max_length=256, null=True)
    invoice_month = models.CharField(max_length=256, null=True)

    # Service columns
    service_id = models.CharField(max_length=256, null=True)
    service_description = models.CharField(max_length=256, null=True)

    # SKU columns
    sku_id = models.CharField(max_length=256, null=True)
    sku_description = models.CharField(max_length=256, null=True)

    # Usage time columns
    usage_start_time = models.DateTimeField(null=True, db_index=True)
    usage_end_time = models.DateTimeField(null=True)
    export_time = models.DateTimeField(null=True)

    # Location columns
    location_region = models.CharField(max_length=256, null=True)
    location_country = models.CharField(max_length=256, null=True)
    location_zone = models.CharField(max_length=256, null=True)

    # Usage columns
    usage_amount = models.FloatField(null=True)
    usage_unit = models.CharField(max_length=256, null=True)
    usage_amount_in_pricing_units = models.FloatField(null=True)
    usage_pricing_unit = models.CharField(max_length=256, null=True)

    # Cost columns
    cost = models.FloatField(null=True)
    cost_type = models.CharField(max_length=256, null=True)
    currency = models.CharField(max_length=20, null=True)
    currency_conversion_rate = models.FloatField(null=True)

    # Credit columns
    credits = models.TextField(null=True)  # JSON
    credit_amount = models.FloatField(null=True)

    # Resource columns
    resource_name = models.TextField(null=True)
    resource_global_name = models.TextField(null=True)

    # Labels (stored as JSON text)
    labels = models.TextField(null=True)
    system_labels = models.TextField(null=True)
    tags = models.TextField(null=True)

    # Row UUID for deduplication
    row_uuid = models.TextField(null=True)


class GCPLineItem(GCPLineItemBase):
    """Model for gcp_line_items table (raw hourly data)."""

    class Meta:
        db_table = "gcp_line_items"
        indexes = [
            models.Index(fields=["source", "year", "month"], name="gcp_li_src_yr_mo_idx"),
        ]

    # Raw-only columns (dropped during daily aggregation)
    project_labels = models.TextField(null=True)
    project_ancestry_numbers = models.TextField(null=True)
    location_location = models.TextField(null=True)
    partition_date = models.TextField(null=True)


class GCPLineItemDaily(GCPLineItemBase):
    """Model for gcp_line_items_daily table (aggregated daily data)."""

    class Meta:
        db_table = "gcp_line_items_daily"
        indexes = [
            models.Index(fields=["source", "year", "month"], name="gcp_li_daily_src_yr_mo_idx"),
        ]

    # Daily-specific columns
    daily_credits = models.FloatField(null=True)


# Mapping from table type to Django model (for self-hosted/on-prem PostgreSQL)
SELF_HOSTED_MODEL_MAP = {
    "gcp_line_items": GCPLineItem,
}

SELF_HOSTED_DAILY_MODEL_MAP = {
    "gcp_line_items": GCPLineItemDaily,
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
