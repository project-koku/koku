#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Add MonthlyExchangeRate model — single source of truth for per-month exchange rates."""
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("cost_models", "0015_static_exchange_rate"),
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
    ]
