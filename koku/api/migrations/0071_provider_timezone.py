#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Migration: add timezone field to Provider model."""
from django.db import migrations, models


class Migration(migrations.Migration):
    """Add an IANA timezone field to Provider for billing-region-aware date attribution."""

    dependencies = [
        ("api", "0070_alter_exchangerates_currency_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="provider",
            name="timezone",
            field=models.CharField(
                blank=True,
                default="UTC",
                help_text=(
                    "IANA timezone for provider's billing region. "
                    "Examples: 'America/New_York', 'Europe/Paris', 'Asia/Tokyo'. "
                    "Defaults to UTC for backwards compatibility."
                ),
                max_length=64,
                null=True,
            ),
        ),
    ]
