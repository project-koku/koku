#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tasks for Subscriptions Watch"""
import datetime
import logging
import uuid

from botocore.exceptions import ClientError
from dateutil import parser

from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from koku import celery_app
from koku import settings
from koku.feature_flags import UNLEASH_CLIENT
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.date_accessor import DateAccessor
from subs.daily_report import ReportSUBS


LOG = logging.getLogger(__name__)

SUBS_EXTRACTION_QUEUE = "subs"

# any additional queues should be added to this list
QUEUE_LIST = [SUBS_EXTRACTION_QUEUE]

SUBS_ACCEPTED_PROVIDERS = (
    Provider.PROVIDER_AWS,
    Provider.PROVIDER_AWS_LOCAL,
    # Add additional accepted providers here
)


def check_schema_name(schema_name: str) -> str:
    """Helper to check for and modify the schema name if needed."""
    if schema_name and not schema_name.startswith(("acct", "org")):
        schema_name = f"acct{schema_name}"

    return schema_name


def enable_subs_processing(schema_name: str) -> bool:
    """Helper to determine if source is enabled for SUBS processing."""
    schema_name = check_schema_name(schema_name)
    context = {"schema_name": schema_name}
    LOG.info(log_json(msg="enable_subs_processing context", context=context))
    return bool(
        UNLEASH_CLIENT.is_enabled("cost-management.backend.subs-data-processor", context) or settings.ENABLE_SUBS_DEBUG
    )


def get_start_and_end_from_manifest_id(manifest_id):
    """Helper to get the start and end dates for the report"""

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


@celery_app.task(name="subs.tasks.collect_subs_report_data_from_manifest", queue=SUBS_EXTRACTION_QUEUE)
def collect_subs_report_data_from_manifest(reports_to_subs_summarize):
    """Initial functionality of the task for SUBS data extraction from manifest"""

    # TODO: update function when all pieces are added

    LOG.info(log_json(msg="collect subs report data from manifest"))

    # Assuming a similar to HCS, iterate over reports, get necessary details
    # for SUBS specific data collection
    # at the moment, the logic is assumed to be similar the HCS flow

    reports = [report for report in reports_to_subs_summarize if report]
    reports_deduplicated = [dict(t) for t in {tuple(d.items()) for d in reports}]

    for report in reports_deduplicated:
        start_date = None
        end_date = None
        if report.get("start") and report.get("end"):
            start_date = parser.parse(report.get("start")).date()
            end_date = parser.parse(report.get("end")).date()
            LOG.info(
                log_json(
                    msg="using start and end dates from the manifest for SUBS processing",
                    start_date=start_date,
                    end_date=end_date,
                )
            )
        else:
            date_tuple = get_start_and_end_from_manifest_id(report.get("manifest_id"))
            if not date_tuple:
                LOG.debug(log_json(msg="no manifest found, skipping report", report=report))
                continue
            start_date, end_date = date_tuple

        # if no latest hourly month-to-date cost and usage files of data,
        # query all data for the month
        dh = DateHelper()
        start_date = dh.this_month_start.date() if start_date is None else start_date
        end_date = dh.this_month_end.date() if end_date is None else end_date

        date_str_fmt = "%Y-%m-%d"
        start_date = start_date.strftime(date_str_fmt)
        end_date = end_date.strftime(date_str_fmt)

        schema_name = report.get("schema_name")
        provider_type = report.get("provider_type")
        provider_uuid = report.get("provider_uuid")
        tracing_id = report.get("tracing_id", report.get("manifest_uuid", str(uuid.uuid4())))

        ctx = {
            "schema_name": schema_name,
            "provider_type": provider_type,
            "provider_uuid": provider_uuid,
            "start_date": start_date,
            "end_date": end_date,
        }
        LOG.info(log_json(tracing_id, msg="collect SUBS report data from manifest", context=ctx))

        collect_subs_report_data.s(
            schema_name, provider_type, provider_uuid, start_date, end_date, tracing_id
        ).apply_async()


@celery_app.task(
    name="subs.tasks.collect_subs_report_data",
    bind=True,
    autoretry_for=(ClientError,),
    max_retries=settings.MAX_UPDATE_RETRIES,
    queue=SUBS_EXTRACTION_QUEUE,
)
def collect_subs_report_data(
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

    # TODO: update the functionality of the SUBS data extraction task when all pieces are added

    start_date = start_date or DateAccessor().today() - datetime.timedelta(days=2)
    end_date = end_date or DateAccessor().today()
    tracing_id = tracing_id or str(uuid.uuid4())

    context = {
        "start_date": start_date,
        "end_date": end_date,
    }
    LOG.info(log_json(tracing_id, msg="skipping subs report generation", context=context))

    schema_name = check_schema_name(schema_name)
    start_date = DateAccessor().today() - datetime.timedelta(days=2) if start_date is None else start_date
    end_date = DateAccessor().today() if end_date is None else end_date
    tracing_id = str(uuid.uuid4()) if tracing_id is None else tracing_id

    ctx = {
        "schema_name": schema_name,
        "provider_uuid": provider_uuid,
        "provider_type": provider_type,
        "start_date": start_date,
        "end_date": end_date,
    }
    if enable_subs_processing(schema_name) and provider_type in SUBS_ACCEPTED_PROVIDERS:
        LOG.info(log_json(tracing_id, msg="collecting subs report data", context=ctx))
        reporter = ReportSUBS(schema_name, provider_type, provider_uuid, tracing_id)
        reporter.generate_report(start_date, end_date)

    else:
        LOG.info(log_json(tracing_id, msg="skipping subs report generation", context=ctx))
