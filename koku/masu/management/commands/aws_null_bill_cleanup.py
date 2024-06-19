from __future__ import annotations

import argparse
import logging
from datetime import datetime
from typing import Any

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from api.provider.models import Provider
from common.queues import get_customer_queue
from common.queues import PriorityQueue
from koku.database import cascade_delete
from koku.feature_flags import UNLEASH_CLIENT
from masu.processor.tasks import update_summary_tables
from reporting.models import AWSCostEntryBill

LOG = logging.getLogger(__name__)
DATE_FORMAT = "%Y-%m-%d"
DATETIMES = (
    datetime(2024, 1, 1, tzinfo=settings.UTC),
    datetime(2023, 12, 1, tzinfo=settings.UTC),
    datetime(2023, 11, 1, tzinfo=settings.UTC),
    datetime(2023, 10, 1, tzinfo=settings.UTC),
    datetime(2023, 9, 1, tzinfo=settings.UTC),
)


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
        LOG.info("Initializing UNLEASH_CLIENT for bill cleanup.")
        UNLEASH_CLIENT.initialize_client()
        if delete:
            LOG.info(msg="DELETING BILLS (--delete passed)")
        else:
            LOG.info(msg="In dry run mode (--delete not passed)")

        total_cleaned_bills = cleanup_aws_bills(delete)

        if delete:
            LOG.info(f"{total_cleaned_bills} bills deleted.")
        else:
            LOG.info(f"DRY RUN: {total_cleaned_bills} bills would be deleted.")


def cleanup_aws_bills(delete: bool) -> int:
    """Deletes AWS Bills with a null payer account ID."""
    total_cleaned_bills = 0
    providers = Provider.objects.filter(type__in=[Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL])
    for start_date in DATETIMES:
        end_date = start_date + relativedelta(day=31)

        for prov in providers:
            schema = prov.customer.schema_name
            provider_uuid = prov.uuid

            with schema_context(schema):
                if bills := AWSCostEntryBill.objects.filter(
                    provider_id=provider_uuid,
                    payer_account_id=None,
                    billing_period_start=start_date,
                ):
                    queue_name = get_customer_queue(schema, PriorityQueue)
                    total_cleaned_bills += len(bills)
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

    return total_cleaned_bills
