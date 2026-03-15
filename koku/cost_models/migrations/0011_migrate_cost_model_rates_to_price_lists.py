#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Data migration: copy CostModel rates into PriceList entities."""
from datetime import date
from uuid import uuid4

from django.db import migrations
from django.db import transaction


def migrate_rates_to_price_lists(apps, schema_editor):
    """For each CostModel with rates, create a PriceList and link it.

    Uses SELECT ... FOR UPDATE to lock each CostModel row individually,
    ensuring no concurrent CostModel API write can modify rates between
    the read and the PriceList creation.
    """
    CostModel = apps.get_model("cost_models", "CostModel")
    PriceList = apps.get_model("cost_models", "PriceList")
    PriceListCostModelMap = apps.get_model("cost_models", "PriceListCostModelMap")

    cm_ids = list(CostModel.objects.filter(rates__isnull=False).exclude(rates=[]).values_list("uuid", flat=True))

    for cm_id in cm_ids:
        with transaction.atomic():
            cm = CostModel.objects.select_for_update().get(uuid=cm_id)

            if PriceListCostModelMap.objects.filter(cost_model=cm).exists():
                continue

            pl = PriceList.objects.create(
                uuid=uuid4(),
                name=f"{cm.name} prices",
                description=f"Auto-migrated from cost model '{cm.name}'",
                currency=cm.currency,
                effective_start_date=date(2026, 3, 1),
                effective_end_date=date(2099, 12, 31),
                enabled=True,
                version=1,
                rates=cm.rates,
            )

            PriceListCostModelMap.objects.create(
                price_list=pl,
                cost_model=cm,
                priority=1,
            )


def reverse_migration(apps, schema_editor):
    """Remove auto-migrated price lists."""
    PriceList = apps.get_model("cost_models", "PriceList")
    PriceList.objects.filter(description__startswith="Auto-migrated from cost model").delete()


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ("cost_models", "0010_add_price_list_models"),
    ]

    operations = [
        migrations.RunPython(migrate_rates_to_price_lists, reverse_migration),
    ]
