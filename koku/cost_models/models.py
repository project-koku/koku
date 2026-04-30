#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for cost models."""
from uuid import uuid4

from django.contrib.postgres.fields import ArrayField
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import JSONField

from api.provider.models import Provider
from koku.settings import KOKU_DEFAULT_CURRENCY

DISTRIBUTION_CHOICES = (("memory", "memory"), ("cpu", "cpu"))
DEFAULT_DISTRIBUTION = "cpu"
COST_TYPE_CHOICES = (
    ("Infrastructure", "Infrastructure"),
    ("Supplementary", "Supplementary"),
)


class CostModel(models.Model):
    """A collection of rates used to calculate cost against resource usage data."""

    class Meta:
        """Meta for CostModel."""

        db_table = "cost_model"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"], name="name_idx"),
            models.Index(fields=["source_type"], name="source_type_idx"),
            models.Index(fields=["updated_timestamp"], name="updated_timestamp_idx"),
        ]

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    name = models.TextField()

    description = models.TextField()

    source_type = models.CharField(max_length=50, null=False, choices=Provider.PROVIDER_CHOICES)

    created_timestamp = models.DateTimeField(auto_now_add=True)

    updated_timestamp = models.DateTimeField(auto_now=True)

    rates = JSONField(default=dict)

    markup = JSONField(encoder=DjangoJSONEncoder, default=dict)

    distribution = models.TextField(choices=DISTRIBUTION_CHOICES, default=DEFAULT_DISTRIBUTION)

    distribution_info = JSONField(default=dict)

    currency = models.TextField(default=KOKU_DEFAULT_CURRENCY)


class CostModelAudit(models.Model):
    """A collection of rates used to calculate cost against resource usage data."""

    class Meta:
        """Meta for CostModel."""

        db_table = "cost_model_audit"

    operation = models.CharField(max_length=16)

    audit_timestamp = models.DateTimeField()

    provider_uuids = ArrayField(models.UUIDField(), null=True)

    uuid = models.UUIDField()

    name = models.TextField()

    description = models.TextField()

    source_type = models.CharField(max_length=50, null=False, choices=Provider.PROVIDER_CHOICES)

    created_timestamp = models.DateTimeField()

    updated_timestamp = models.DateTimeField()

    rates = JSONField(default=dict)

    markup = JSONField(encoder=DjangoJSONEncoder, default=dict)

    distribution = models.TextField(choices=DISTRIBUTION_CHOICES, default=DEFAULT_DISTRIBUTION)

    distribution_info = JSONField(default=dict)

    currency = models.TextField(default=KOKU_DEFAULT_CURRENCY)


class CostModelMap(models.Model):
    """Map for provider and rate objects."""

    provider_uuid = models.UUIDField(editable=False, unique=False, null=False)

    cost_model = models.ForeignKey("CostModel", null=True, blank=True, on_delete=models.CASCADE)

    class Meta:
        """Meta for CostModelMap."""

        ordering = ["-id"]
        unique_together = ("provider_uuid", "cost_model")
        db_table = "cost_model_map"


class PriceList(models.Model):
    """A standalone rate collection with validity period, versioning, and enabled/disabled status."""

    class Meta:
        db_table = "price_list"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"], name="price_list_name_idx"),
            models.Index(
                fields=["effective_start_date", "effective_end_date"],
                name="price_list_validity_idx",
            ),
        ]

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    name = models.TextField()

    description = models.TextField()

    currency = models.TextField()

    effective_start_date = models.DateField()

    effective_end_date = models.DateField()

    enabled = models.BooleanField(default=True)

    version = models.PositiveIntegerField(default=1)

    rates = JSONField()

    created_timestamp = models.DateTimeField(auto_now_add=True)

    updated_timestamp = models.DateTimeField(auto_now=True)


class Rate(models.Model):
    """A normalized rate row linked to a PriceList."""

    class Meta:
        db_table = "cost_model_rate"
        unique_together = ("price_list", "custom_name")
        indexes = [
            models.Index(fields=["price_list"], name="rate_price_list_idx"),
            models.Index(fields=["custom_name"], name="rate_custom_name_idx"),
            models.Index(fields=["metric"], name="rate_metric_idx"),
        ]

    uuid = models.UUIDField(primary_key=True, default=uuid4)

    price_list = models.ForeignKey("PriceList", on_delete=models.CASCADE, related_name="rate_rows")

    custom_name = models.CharField(max_length=50)

    description = models.TextField(blank=True, default="")

    metric = models.CharField(max_length=100)

    metric_type = models.CharField(max_length=20)

    cost_type = models.CharField(max_length=20, choices=COST_TYPE_CHOICES)

    default_rate = models.DecimalField(max_digits=33, decimal_places=15, null=True)

    tag_key = models.CharField(max_length=253, blank=True, default="")

    tag_values = JSONField(default=list)

    created_timestamp = models.DateTimeField(auto_now_add=True)

    updated_timestamp = models.DateTimeField(auto_now=True)


class PriceListCostModelMap(models.Model):
    """Links price lists to cost models with priority ordering."""

    class Meta:
        db_table = "price_list_cost_model_map"
        ordering = ["priority"]
        unique_together = ("price_list", "cost_model")

    price_list = models.ForeignKey("PriceList", on_delete=models.CASCADE, related_name="cost_model_maps")

    cost_model = models.ForeignKey("CostModel", on_delete=models.CASCADE, related_name="price_list_maps")

    priority = models.PositiveIntegerField()


class RateType(models.TextChoices):
    STATIC = "static", "Static"
    DYNAMIC = "dynamic", "Dynamic"


class StaticExchangeRate(models.Model):
    """User-defined exchange rates with validity periods."""

    class Meta:
        db_table = "static_exchange_rate"
        ordering = ["-updated_timestamp"]
        unique_together = [("base_currency", "target_currency", "start_date", "end_date")]

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    base_currency = models.CharField(max_length=5)
    target_currency = models.CharField(max_length=5)
    exchange_rate = models.DecimalField(max_digits=33, decimal_places=15)
    start_date = models.DateField()
    end_date = models.DateField()
    created_timestamp = models.DateTimeField(auto_now_add=True)
    updated_timestamp = models.DateTimeField(auto_now=True)

    @property
    def name(self):
        return f"{self.base_currency}-{self.target_currency}"


class EnabledCurrency(models.Model):
    """Per-tenant enabled currencies: presence in this table means the currency is enabled."""

    class Meta:
        db_table = "enabled_currency"
        ordering = ["currency_code"]

    currency_code = models.CharField(max_length=5, unique=True)
    created_timestamp = models.DateTimeField(auto_now_add=True)


class MonthlyExchangeRate(models.Model):
    """Single source of truth for exchange rates used in reports.

    Stores both static and dynamic rates as per-pair rows, one row per month.
    The query handler reads from this table for all months.
    """

    class Meta:
        db_table = "monthly_exchange_rate"
        unique_together = ("effective_date", "base_currency", "target_currency")

    effective_date = models.DateField()
    base_currency = models.CharField(max_length=5)
    target_currency = models.CharField(max_length=5)
    exchange_rate = models.DecimalField(max_digits=33, decimal_places=15)
    rate_type = models.CharField(max_length=10, choices=RateType.choices)
    created_timestamp = models.DateTimeField(auto_now_add=True)
    updated_timestamp = models.DateTimeField(auto_now=True)
