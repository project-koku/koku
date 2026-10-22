#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Inventory and safely delete orphaned partitioned_tables tracking rows (COST-8415).

Only deletes rows whose physical table does not exist in PostgreSQL. DELETE on
partitioned_tables would otherwise DETACH/TRUNCATE/DROP a same-named relation via
trfn_partition_manager — those rows are reported only.

Default is dry-run. Pass --delete after reviewing counts and samples.
"""
from __future__ import annotations

import argparse
import logging
from typing import Any

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from api.iam.models import Tenant
from koku.pg_partition import reconcile_stale_partition_tracking
from koku.pg_partition import TRACKING_PHYSICAL_PRESENT
from koku.pg_partition import TRACKING_SAFE_ORPHAN

LOG = logging.getLogger(__name__)


def _tenant_schema_names(*, schema: str | None = None) -> list[str]:
    excluded = {"public", Tenant._TEMPLATE_SCHEMA}
    if schema:
        if schema in excluded:
            raise CommandError(f"Schema {schema} is not a customer tenant schema.")
        if not Tenant.objects.filter(schema_name=schema).exists():
            raise CommandError(f"Tenant schema {schema} not found.")
        return [schema]
    return [name for name in Tenant.objects.values_list("schema_name", flat=True) if name and name not in excluded]


class Command(BaseCommand):
    help = (
        "Inventory (and optionally delete) partitioned_tables rows whose physical "
        "tables no longer exist. Dry-run by default; pass --delete to mutate."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--delete",
            action="store_true",
            default=False,
            help="Delete verified safe_orphan tracking rows. Without this flag, only report.",
        )
        parser.add_argument(
            "--schema",
            type=str,
            default=None,
            help="Limit to one tenant schema (default: all customer schemas).",
        )
        parser.add_argument(
            "--sample",
            type=int,
            default=5,
            help="Max sample rows to log per classification per schema (default: 5).",
        )

    def handle(self, *args: Any, delete: bool, schema: str | None, sample: int, **kwargs: Any) -> None:
        if sample < 0:
            raise CommandError("--sample must be >= 0")

        schemas = _tenant_schema_names(schema=schema)
        mode = "DELETE" if delete else "DRY RUN"
        self.stdout.write(f"partition tracking reconcile ({mode}) schemas={len(schemas)}")

        totals = {TRACKING_SAFE_ORPHAN: 0, TRACKING_PHYSICAL_PRESENT: 0, "deleted": 0}
        for schema_name in schemas:
            result = reconcile_stale_partition_tracking(schema_name, delete=delete, sample=sample)
            totals[TRACKING_SAFE_ORPHAN] += result["counts"].get(TRACKING_SAFE_ORPHAN, 0)
            totals[TRACKING_PHYSICAL_PRESENT] += result["counts"].get(TRACKING_PHYSICAL_PRESENT, 0)
            totals["deleted"] += result["deleted"]

        self.stdout.write(
            f"Done ({mode}): safe_orphan={totals[TRACKING_SAFE_ORPHAN]} "
            f"physical_present={totals[TRACKING_PHYSICAL_PRESENT]} deleted={totals['deleted']}"
        )
        if not delete and totals[TRACKING_SAFE_ORPHAN]:
            self.stdout.write("Review samples in logs, then re-run with --delete to remove safe_orphan rows only.")
