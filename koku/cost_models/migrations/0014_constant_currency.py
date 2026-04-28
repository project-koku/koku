#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Add StaticExchangeRate, EnabledCurrency, and MonthlyExchangeRate models for constant currency."""
import uuid

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("cost_models", "0013_normalize_rates_to_rate_table"),
    ]

    operations = [
        migrations.CreateModel(
            name="StaticExchangeRate",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("base_currency", models.CharField(max_length=5)),
                ("target_currency", models.CharField(max_length=5)),
                ("exchange_rate", models.DecimalField(decimal_places=15, max_digits=33)),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("created_timestamp", models.DateTimeField(auto_now_add=True)),
                ("updated_timestamp", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "static_exchange_rate",
                "ordering": ["-updated_timestamp"],
                "unique_together": {("base_currency", "target_currency", "start_date", "end_date")},
            },
        ),
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
