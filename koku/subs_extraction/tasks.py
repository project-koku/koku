#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tasks for Subscriptions Watch Data Extraction and Transmission"""
import datetime
import logging
import uuid

from botocore.exceptions import ClientError

from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from koku import celery_app
from koku import settings
from koku.feature_flags import UNLEASH_CLIENT
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.util.common import convert_account

LOG = logging.getLogger(__name__)

SUBS_EXTRACTION_QUEUE = "subs_extraction"

# any additional queues should be added to this list
QUEUE_LIST = [SUBS_EXTRACTION_QUEUE]

SUBS_ACCEPTED_PROVIDERS = (
    Provider.PROVIDER_AWS,
    Provider.PROVIDER_AWS_LOCAL,
    # Add additional accepted providers here
)


def enable_subs_extraction(schema_name: str) -> bool:
    """Helper to determine if source is enabled for SUBS processing."""

    schema_name = convert_account(schema_name)
    context = {"schema_name": schema_name}
    LOG.info(log_json(msg="enable_subs_extraction context", context=context))

    return bool(
        UNLEASH_CLIENT.is_enabled("cost-management.backend.subs-data-extraction", context)
        or settings.ENABLE_SUBS_EXTRACTION_DEBUG
    )


def get_start_and_end_from_manifest_id(manifest_id):
    """Helper to get the start and end dates for the report."""

    start_date = None
    end_date = None

    with ReportManifestDBAccessor() as manifest_accessor:
        manifest = manifest_accessor.get_manifest_by_id(manifest_id)
        if not manifest:
            return

        bill_date = manifest.billing_period_start_datetime.date()
        if bill_date:
            provider_uuid = manifest.provider_id
            manifest_list = manifest_accessor.get_manifest_list_for_provider_and_bill_date(provider_uuid, bill_date)
            if len(manifest_list) == 1:
                start_date = bill_date
                end_date = DateHelper().month_end(bill_date)

    return start_date, end_date


@celery_app.task(
    name="subs_extraction.tasks.collect_subs_extract_report_data_from_manifest", queue=SUBS_EXTRACTION_QUEUE
)
def collect_subs_extract_report_data_from_manifest(reports_to_subs_summarize):
    """Initial functionality of the task for SUBS data extraction from manifest"""

    LOG.info(log_json(msg="collect subs report data from manifest"))

    # TODO: To uncomment if to adapt the following code block based on the assumed similarity with HCS flow.

    """
    reports = [report for report in reports_to_subs_summarize if report]
    reports_deduplicated = [dict(t) for t in {tuple(d.items()) for d in reports}]

    for report in reports_deduplicated:
        start_date = None
        end_date = None
        ...
        # Process each report to:
        # - Extract start and end dates (either directly from the report data or from the manifest ID)
        # - Retrieve schema_name, provider_type, provider_uuid, and tracing_id
        # - Initiate the collect_subs_report_data task with the collected information.
        ...
        collect_subs_report_data.s(
            schema_name, provider_type, provider_uuid, start_date, end_date, tracing_id
        ).apply_async()
    """


@celery_app.task(
    name="subs_extraction.tasks.collect_subs_extract_report_data",
    bind=True,
    autoretry_for=(ClientError,),
    max_retries=settings.MAX_UPDATE_RETRIES,
    queue=SUBS_EXTRACTION_QUEUE,
)
def collect_subs_extract_report_data(
    self, schema_name, provider_type, provider_uuid, start_date=None, end_date=None, tracing_id=None
):
    """Implement the functionality of the new task
    Args:
        schema_name:     (str) db schema name
        provider_type:   (str) The provider type
        provider_uuid:   (str) The provider unique identification number
        start_date:      The date to start populating the table (default: (Today - 2 days))
        end_date:        The date to end on (default: Today)
        tracing_id:      (uuid) for log tracing

    Returns:
        None
    """

    dh = DateHelper()
    start_date = start_date or dh.today - datetime.timedelta(days=2)
    end_date = end_date or dh.today
    schema_name = convert_account(schema_name)
    tracing_id = tracing_id or str(uuid.uuid4())

    ctx = {
        "schema_name": schema_name,
        "provider_uuid": provider_uuid,
        "provider_type": provider_type,
        "start_date": start_date,
        "end_date": end_date,
    }
    if enable_subs_extraction(schema_name) and provider_type in SUBS_ACCEPTED_PROVIDERS:
        LOG.info(log_json(tracing_id, msg="collecting subs report data", context=ctx))
        # TODO: instantiate the ReportSUBS class and call generate_report when implemented.
        # reporter = ReportSUBS(schema_name, provider_type, provider_uuid, tracing_id)
        # reporter.generate_report(start_date, end_date)

    else:
        LOG.info(log_json(tracing_id, msg="skipping subs report generation", context=ctx))
