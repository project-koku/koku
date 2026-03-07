#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Management command to back-fill timezone on existing Provider records.

Usage
-----
::

    python manage.py populate_provider_timezones [--dry-run]

The command inspects every Provider whose ``timezone`` field is empty or
``None`` and sets it to ``'UTC'``.

AWS CUR, GCP BigQuery billing export, and Azure Cost Details all publish
timestamps in UTC.  There is no region-specific local-time offset to apply,
so all cloud providers default to UTC.

All changes are wrapped in a single database transaction so a failure rolls
back every partial update.
"""
import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from api.common import log_json
from api.provider.models import Provider

LOG = logging.getLogger(__name__)


class Command(BaseCommand):
    """Back-fill timezone on Provider records that are missing it."""

    help = "Back-fill the timezone field on Provider records that are missing it."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Print what would be changed without writing to the database.",
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        mode = "DRY-RUN" if dry_run else "LIVE"
        self.stdout.write(f"[{mode}] Scanning providers for missing timezone …")

        # Only touch providers that have no timezone set yet.
        candidates = Provider.objects.filter(timezone__isnull=True) | Provider.objects.filter(timezone="")

        if not candidates.exists():
            self.stdout.write("All providers already have a timezone set — nothing to do.")
            return

        updates: list[Provider] = []
        for provider in candidates.iterator():
            # All major cloud providers (AWS, GCP, Azure) report billing data in UTC.
            # Default every provider to "UTC".
            tz = "UTC"
            msg = "would set" if dry_run else "setting"
            context = {
                "provider_uuid": str(provider.uuid),
                "provider_type": provider.type,
                "inferred_timezone": tz,
            }
            LOG.info(log_json(msg=f"{msg} provider timezone", context=context))
            self.stdout.write(f"  {msg} {provider.uuid} ({provider.type}) → {tz}")
            provider.timezone = tz
            updates.append(provider)

        if dry_run:
            self.stdout.write(f"[DRY-RUN] Would update {len(updates)} provider(s) — no changes written.")
            return

        # Commit all updates in one transaction for atomicity.
        with transaction.atomic():
            Provider.objects.bulk_update(updates, ["timezone"])

        self.stdout.write(self.style.SUCCESS(f"Successfully updated {len(updates)} provider(s)."))
