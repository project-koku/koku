#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("cost_models", "0015_enabledcurrency"),
    ]

    operations = [
        migrations.AddField(
            model_name="enabledcurrency",
            name="currency_name",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="enabledcurrency",
            name="currency_symbol",
            field=models.CharField(blank=True, default="", max_length=10),
        ),
    ]
