#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("cost_models", "0015_enabledcurrency"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="EnabledCurrency",
            new_name="CurrencyConfig",
        ),
        migrations.AlterModelTable(
            name="currencyconfig",
            table="currency_config",
        ),
    ]
