from __future__ import annotations

import argparse
from typing import Any

from dateutil import parser
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import DEFAULT_DB_ALIAS
from django_tenants.utils import schema_context

from api.provider.models import Provider
from koku.database import cascade_delete
from reporting.models import AWSCostEntryBill


class Command(BaseCommand):
    help = "Delete AWS Bills and with a NULL payer_account_id and all FK references for a given month."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--database",
            default=DEFAULT_DB_ALIAS,
            help='Which database to update. Defaults to the "default" database.',
        )
        parser.add_argument(
            "--delete",
            action="store_true",
            default=False,
            help="Actually delete the cost entry bills.",
        )
        parser.add_argument(
            "--bill-date",
            required=True,
            help="The date to cleanup bills for.",
        )

    def handle(self, *args: Any, database: str, delete: bool, bill_date: str, **kwargs: Any) -> None:
        def output(text: str) -> None:
            self.stdout.write(text)
            self.stdout.flush()

        if not delete:
            output("In dry run mode (--delete not passed)")

        cleanup_aws_bills(delete, bill_date)


def cleanup_aws_bills(delete, bill_date):
    formatted_date = parser.parse(bill_date).replace(tzinfo=settings.UTC)
    print(f"attempting to cleanup bills for a billing_period_start of {formatted_date}")
    total_cleaned_bills = 0
    total_cleaned_providers = 0
    providers = Provider.objects.filter(type__in=[Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL])
    for prov in providers:
        schema = prov.customer.schema_name
        provider_uuid = prov.uuid
        with schema_context(schema):
            bills = AWSCostEntryBill.objects.filter(
                provider_id=provider_uuid, payer_account_id=None, billing_period_start=formatted_date
            )
            if not bills:
                print(f"no bills found with empty payer account for provider: {provider_uuid} on schema: {schema}")
                continue
            num_bills = len(bills)
            total_cleaned_providers += 1
            total_cleaned_bills += num_bills
            print(
                f"found {num_bills} bills with empty payer account for provider: {provider_uuid} on schema: {schema}"
            )
            if delete:
                print("beginning cascade deletes")
                cascade_delete(bills.query.model, bills)
                print("cascade delete finished")
            else:
                bill_ids = [bill.id for bill in bills]
                print(f"bills {bill_ids} would be deleted for provider: {provider_uuid}")
    if delete:
        print(f"{total_cleaned_bills} bills deleted across {total_cleaned_providers} providers.")

    else:
        print(
            f"{total_cleaned_bills} bills would be deleted across {total_cleaned_providers} providers on a real run."
        )
