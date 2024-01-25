from __future__ import annotations

import argparse
import logging
from typing import Any

from dateutil import parser
from dateutil.relativedelta import relativedelta
from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from api.provider.models import Provider
from koku.database import cascade_delete
from masu.processor import is_customer_large
from masu.processor.tasks import PRIORITY_QUEUE
from masu.processor.tasks import PRIORITY_QUEUE_XL
from masu.processor.tasks import update_summary_tables
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
            LOG.info(msg="In dry run mode (--delete not passed)")
        else:
            LOG.info(msg="DELETING BILLS (--delete passed)")
        cleanup_aws_bills(delete)


def cleanup_aws_bills(delete):
    """Deletes AWS Bills with a null payer account ID for January 2024 back through October 2023."""
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
                if bills:
                    queue_name = PRIORITY_QUEUE_XL if is_customer_large(schema) else PRIORITY_QUEUE
                    num_bills = len(bills)
                    total_cleaned_bills += num_bills
                    if delete:
                        formatted_start = start_date.strftime(DATE_FORMAT)
                        formatted_end = end_date.strftime(DATE_FORMAT)
                        cascade_delete(bills.query.model, bills)
                        async_result = update_summary_tables.s(
                            schema,
                            prov.type,
                            provider_uuid,
                            formatted_start,
                            end_date=formatted_end,
                            queue_name=queue_name,
                            ocp_on_cloud=True,
                        ).apply_async(queue=queue_name)
                        LOG.info(
                            f"Deletes completed and summary triggered for provider {provider_uuid} "
                            f"with start {formatted_start} and end {formatted_end}, task_id: {async_result.id}"
                        )

                    else:
                        bill_ids = [bill.id for bill in bills]
                        LOG.info(f"bills {bill_ids} would be deleted for provider: {provider_uuid}")
                start_date = start_date - relativedelta(months=1)
                end_date = start_date + relativedelta(day=31)

    if delete:
        LOG.info(f"{total_cleaned_bills} bills deleted across {total_cleaned_providers} providers.")

    else:
        LOG.info(f"DRY RUN: {total_cleaned_bills} bills would be deleted across {total_cleaned_providers} providers.")
