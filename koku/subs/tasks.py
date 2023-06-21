#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tasks for Subscriptions Watch"""
import datetime
import logging
import uuid

from botocore.exceptions import ClientError

from api.common import log_json
from api.provider.models import Provider
from koku import celery_app
from koku import settings
from masu.external.date_accessor import DateAccessor


LOG = logging.getLogger(__name__)

SUBS_EXTRACTION_QUEUE = "subs_extraction"

# any additional queues should be added to this list
QUEUE_LIST = [SUBS_EXTRACTION_QUEUE]

SUBS_ACCEPTED_PROVIDERS = (
    Provider.PROVIDER_AWS,
    Provider.PROVIDER_AWS_LOCAL,
    # Add additional accepted providers here
)


def check_schema_name(schema_name: str) -> str:
    # Implement the logic for checking and modifying the schema name if needed
    pass


def enable_subs_processing(schema_name: str) -> bool:
    """Determine if the source is enabled for SUBS processing."""
    schema_name = check_schema_name(schema_name)
    context = {"schema_name": schema_name}
    LOG.info(f"enable_subs_processing context: {context}")

    # TODO: check for unleash client
    # UNLEASH_CLIENT.is_enabled("cost-management.backend.subs-data-processor", context)

    return bool(context) or settings.ENABLE_SUBS_DEBUG


@celery_app.task(name="subs.tasks.collect_subs_report_data_from_manifest", queue=SUBS_EXTRACTION_QUEUE)
def collect_subs_report_data_from_manifest(reports_to_subs_summarize):
    """Implement the functionality of the new task"""

    # TODO: Implement the functionality of the new task for SUBS data extraction from manifest

    LOG.info("collect subs report data from manifest")

    collect_subs_report_data.s(
        "schema_name",
        "provider_type",
        "provider_uuid",
    ).apply_async()


@celery_app.task(
    name="subs.tasks.collect_subs_report_data",
    bind=True,
    autoretry_for=(ClientError,),
    max_retries=settings.MAX_UPDATE_RETRIES,
    queue=SUBS_EXTRACTION_QUEUE,
)
def collect_subs_report_data(
    self, schema_name, provider_type, provider_uuid, start_date=None, end_date=None, tracing_id=None, finalize=False
):
    """Implement the functionality of the new task
    Args:
        schema_name:     (str) db schema name
        provider_type:   (str) The provider type
        provider_uuid:   (str) The provider unique identification number
        start_date:      The date to start populating the table (default: (Today - 2 days))
        end_date:        The date to end on (default: Today)
        tracing_id:      (uuid) for log tracing
        finalize:        (boolean) If True run report finalization process for previous month(default: False)

    Returns:
        None
    """

    # TODO: Implement the functionality of the new task for SUBS data extraction

    start_date = start_date or DateAccessor().today() - datetime.timedelta(days=2)
    end_date = end_date or DateAccessor().today()
    tracing_id = tracing_id or str(uuid.uuid4())

    context = {
        "start_date": start_date,
        "end_date": end_date,
    }
    LOG.info(log_json(tracing_id, msg="skipping subs report generation", context=context))


def get_providers_for_subs():
    # Implement the logic to fetch and filter providers for SUBS processing
    pass
