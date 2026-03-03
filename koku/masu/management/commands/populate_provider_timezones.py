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
``None`` and attempts to infer the correct IANA timezone from:

1. The provider's ``region`` (if present) — AWS/Azure region codes are mapped
   via :func:`masu.util.timezone_utils.aws_region_to_tz`.
2. A hard-coded UTC fallback for any provider whose region is unknown.

All changes are wrapped in a single database transaction so a failure rolls
back every partial update.
"""
import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from api.common import log_json
from api.provider.models import Provider
from masu.util.timezone_utils import aws_region_to_tz

LOG = logging.getLogger(__name__)

# Provider types that carry a billing region we can map to a timezone.
_REGION_PROVIDER_TYPES = {
    Provider.PROVIDER_AWS,
    Provider.PROVIDER_AWS_LOCAL,
    Provider.PROVIDER_AZURE,
    Provider.PROVIDER_AZURE_LOCAL,
    Provider.PROVIDER_GCP,
    Provider.PROVIDER_GCP_LOCAL,
}


def _infer_timezone(provider) -> str:
    """Infer likely IANA timezone for *provider*.

    Strategy:
    - Cloud providers: map ``provider.region`` via :func:`aws_region_to_tz`
      (the same mapping works as a best-effort guess for Azure/GCP regions too).
    - All other cases: return ``'UTC'`` to preserve existing behaviour.
    """
    if provider.type in _REGION_PROVIDER_TYPES:
        region = getattr(provider, "region", None) or ""
        tz = aws_region_to_tz(region)
        if tz != "UTC" or region.upper() == "UTC":
            return tz
    return "UTC"


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
            tz = _infer_timezone(provider)
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
