from __future__ import annotations

import argparse
import logging
from typing import Any

from dateutil import parser
from dateutil.relativedelta import relativedelta
from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from api.common import log_json
from api.provider.models import Provider
from koku.database import cascade_delete
from reporting.models import AWSCostEntryBill


LOG = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Delete AWS Bills and with a NULL payer_account_id and all FK references for a given month."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--delete",
            action="store_true",
            default=False,
            help="Actually delete the cost entry bills.",
        )

    def handle(self, *args: Any, delete: bool, **kwargs: Any) -> None:
        if not delete:
            LOG.info(log_json(msg="In dry run mode (--delete not passed)"))
        else:
            LOG.info(log_json(msg="DELETING BILLS (--delete passed)"))
        cleanup_aws_bills(delete)


def cleanup_aws_bills(delete):
    """Deletes AWS Bills with a null payer account ID for January 2024 back through October 2023."""
    SUMMARY_URL_TEMPLATE = "api/cost-management/v1/report_data/?schema={}&provider_uuid={}&start_date={}&end_date={}"
    DATE_FORMAT = "%Y-%m-%d"
    initial_date = parser.parse("2024-01-01T00:00:00+00:00")
    total_cleaned_bills = 0
    total_cleaned_providers = 0
    providers = Provider.objects.filter(type__in=[Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL])
    for prov in providers:
        schema = prov.customer.schema_name
        provider_uuid = prov.uuid
        total_cleaned_providers += 1
        start_date = initial_date
        # adding a relative delta of day=31 will not cross a month boundary whereas days=31 would
        end_date = start_date + relativedelta(day=31)
        with schema_context(schema):
            while start_date >= parser.parse("2023-10-01T00:00:00+00:00"):
                bills = AWSCostEntryBill.objects.filter(
                    provider_id=provider_uuid, payer_account_id=None, billing_period_start=start_date
                )
                summary_url = SUMMARY_URL_TEMPLATE.format(
                    schema, provider_uuid, start_date.strftime(DATE_FORMAT), end_date.strftime(DATE_FORMAT)
                )
                start_date = start_date - relativedelta(months=1)
                end_date = start_date + relativedelta(day=31)
                if not bills:
                    continue
                num_bills = len(bills)
                total_cleaned_bills += num_bills
                if delete:
                    cascade_delete(bills.query.model, bills)
                    LOG.info(log_json(msg="Deletes completed and ready for summary", summary_url=summary_url))

                else:
                    bill_ids = [bill.id for bill in bills]
                    LOG.info(log_json(msg=f"bills {bill_ids} would be deleted for provider: {provider_uuid}"))

    if delete:
        LOG.info(log_json(msg=f"{total_cleaned_bills} bills deleted across {total_cleaned_providers} providers."))

    else:
        LOG.info(
            log_json(
                msg=f"DRY RUN: {total_cleaned_bills} bills would be deleted across {total_cleaned_providers} providers."
            )
        )
