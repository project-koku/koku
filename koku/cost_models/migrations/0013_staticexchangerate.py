#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import uuid

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("cost_models", "0012_add_rate_model"),
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
                ("version", models.IntegerField(default=1)),
                ("created_timestamp", models.DateTimeField(auto_now_add=True)),
                ("updated_timestamp", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "static_exchange_rate",
                "ordering": ["-updated_timestamp"],
            },
        ),
    ]
