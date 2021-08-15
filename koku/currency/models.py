from django.db import models

from api.iam.models import Customer
from koku.settings import KOKU_DEFAULT_CURRENCY


class CurrencyOptions(models.Model):
    """A collection of supported currencies for OCP cost models."""

    class Meta:
        """Meta for Currency."""

        db_table = "currency_options"
        ordering = ["code"]

    code = models.CharField(max_length=5)
    name = models.CharField(max_length=150)
    symbol = models.CharField(max_length=150)
    description = models.TextField()


class CurrencySettings(models.Model):
    """A table that maps between account and currency: currency has many accounts."""

    class Meta:
        db_table = "currency_settings"
        ordering = ["currency_code"]

    currency_code = models.ForeignKey(CurrencyOptions, on_delete=models.SET(KOKU_DEFAULT_CURRENCY))
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, primary_key=True)
