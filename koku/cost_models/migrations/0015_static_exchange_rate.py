#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Add StaticExchangeRate model for admin-defined currency rates with monthly validity."""
import uuid

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("cost_models", "0014_enabled_currency"),
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
                "ordering": ["-start_date"],
                "unique_together": {("base_currency", "target_currency", "start_date", "end_date")},
            },
        ),
        migrations.AddConstraint(
            model_name="staticexchangerate",
            constraint=models.CheckConstraint(
                check=models.Q(end_date__gte=models.F("start_date")),
                name="static_rate_end_gte_start",
            ),
        ),
        migrations.AddIndex(
            model_name="staticexchangerate",
            index=models.Index(
                fields=["base_currency", "target_currency"],
                name="static_rate_pair_idx",
            ),
        ),
    ]
