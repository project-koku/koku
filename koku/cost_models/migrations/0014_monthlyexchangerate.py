#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from datetime import date

from django.db import migrations
from django.db import models


def seed_current_month(apps, schema_editor):
    """Seed MonthlyExchangeRate with current-month rates from ExchangeRateDictionary."""
    ExchangeRateDictionary = apps.get_model("api", "ExchangeRateDictionary")
    MonthlyExchangeRate = apps.get_model("cost_models", "MonthlyExchangeRate")

    erd = ExchangeRateDictionary.objects.first()
    if not erd or not erd.currency_exchange_dictionary:
        return

    current_month = date.today().replace(day=1)

    rows = []
    for base_cur, targets in erd.currency_exchange_dictionary.items():
        for target_cur, rate in targets.items():
            if base_cur == target_cur:
                continue
            rows.append(
                MonthlyExchangeRate(
                    effective_date=current_month,
                    base_currency=base_cur,
                    target_currency=target_cur,
                    exchange_rate=rate,
                    rate_type="dynamic",
                )
            )
    MonthlyExchangeRate.objects.bulk_create(rows, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ("cost_models", "0013_staticexchangerate"),
        ("api", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MonthlyExchangeRate",
            fields=[
                (
                    "id",
                    models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                ("effective_date", models.DateField()),
                ("base_currency", models.CharField(max_length=5)),
                ("target_currency", models.CharField(max_length=5)),
                ("exchange_rate", models.DecimalField(decimal_places=15, max_digits=33)),
                ("rate_type", models.CharField(choices=[("static", "Static"), ("dynamic", "Dynamic")], max_length=10)),
                ("created_timestamp", models.DateTimeField(auto_now_add=True)),
                ("updated_timestamp", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "monthly_exchange_rate",
                "unique_together": {("effective_date", "base_currency", "target_currency")},
            },
        ),
        migrations.RunPython(seed_current_month, migrations.RunPython.noop),
    ]
