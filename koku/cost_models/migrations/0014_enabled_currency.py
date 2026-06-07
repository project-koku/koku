#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Add EnabledCurrency model for per-tenant currency enablement."""
from django.db import migrations
from django.db import models


DEFAULT_ENABLED_CURRENCIES = (
    "AED",
    "AUD",
    "BRL",
    "CAD",
    "CHF",
    "CNY",
    "CZK",
    "DKK",
    "EUR",
    "GBP",
    "GHS",
    "HKD",
    "INR",
    "JPY",
    "NGN",
    "NOK",
    "NZD",
    "SAR",
    "SEK",
    "SGD",
    "TWD",
    "USD",
    "ZAR",
)


def seed_enabled_currencies(apps, schema_editor):
    """Seed EnabledCurrency with the previously hardcoded currency set."""
    EnabledCurrency = apps.get_model("cost_models", "EnabledCurrency")
    EnabledCurrency.objects.bulk_create(
        [EnabledCurrency(currency_code=code) for code in DEFAULT_ENABLED_CURRENCIES],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("cost_models", "0013_normalize_rates_to_rate_table"),
    ]

    operations = [
        migrations.CreateModel(
            name="EnabledCurrency",
            fields=[
                (
                    "id",
                    models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                ("currency_code", models.CharField(max_length=5, unique=True)),
                ("created_timestamp", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "enabled_currency",
                "ordering": ["currency_code"],
            },
        ),
    ]

    operations.append(
        migrations.RunPython(code=seed_enabled_currencies, reverse_code=migrations.RunPython.noop),
    )
