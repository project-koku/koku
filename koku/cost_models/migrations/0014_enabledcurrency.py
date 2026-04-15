#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("cost_models", "0013_monthlyexchangerate"),
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
                ("enabled", models.BooleanField(default=False)),
                ("created_timestamp", models.DateTimeField(auto_now_add=True)),
                ("updated_timestamp", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "enabled_currency",
                "ordering": ["currency_code"],
            },
        ),
    ]
