#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tasks for Subscriptions Watch"""
import logging
import uuid

from dateutil import parser

from api.common import log_json
from api.utils import DateHelper
from koku import celery_app
from koku import settings
from koku.feature_flags import UNLEASH_CLIENT
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from subs.subs_data_extractor import SUBSDataExtractor
from subs.subs_data_messenger import SUBSDataMessenger

LOG = logging.getLogger(__name__)

SUBS_EXTRACTION_QUEUE = "subs_extraction"
SUBS_TRANSMISSION_QUEUE = "subs_transmission"

# any additional queues should be added to this list
QUEUE_LIST = [SUBS_EXTRACTION_QUEUE, SUBS_TRANSMISSION_QUEUE]


def enable_subs_extraction(schema_name: str, metered: str) -> bool:  # pragma: no cover
    """Helper to determine if source is enabled for SUBS extraction."""
    context = {"schema": schema_name}
    LOG.info(log_json(msg="enable_subs_extraction context", context=context))
    return bool(
        UNLEASH_CLIENT.is_enabled("cost-management.backend.subs-data-extraction", context)
        or settings.ENABLE_SUBS_DEBUG
        or metered == "rhel"
    )


def enable_subs_messaging(schema_name: str) -> bool:  # pragma: no cover
    """Helper to determine if source is enabled for SUBS messaging."""
    context = {"schema": schema_name}
    LOG.info(log_json(msg="enable_subs_messaging context", context=context))
    return bool(
        UNLEASH_CLIENT.is_enabled("cost-management.backend.subs-data-messaging", context) or settings.ENABLE_SUBS_DEBUG
    )


def get_month_start_from_report(report):
    """Gets the month start as a datetime from a report"""
    if report.get("start"):
        start_date = parser.parse(report.get("start"))
        return DateHelper().month_start_utc(start_date)
    else:
        # GCP sets report start and report end, AWS/Azure do not
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest_by_id(report.get("manifest_id"))
            return manifest.billing_period_start_datetime if manifest else None


@celery_app.task(name="subs.tasks.extract_subs_data_from_reports", queue=SUBS_EXTRACTION_QUEUE)
def extract_subs_data_from_reports(reports_to_extract, metered):
    """Extract relevant subs records from reports to S3 and trigger messaging task if reports are gathered."""
    reports = [report for report in reports_to_extract if report]
    reports_deduplicated = [dict(t) for t in {tuple(d.items()) for d in reports}]
    for report in reports_deduplicated:
        schema_name = report.get("schema_name")
        provider_type = report.get("provider_type")
        provider_uuid = report.get("provider_uuid")
        tracing_id = report.get("tracing_id", report.get("manifest_uuid", str(uuid.uuid4())))
        context = {"schema": schema_name, "provider_type": provider_type, "provider_uuid": provider_uuid}
        # SUBS provider type enablement is handled through the ENABLE_SUBS_PROVIDER_TYPES environment variable
        if provider_type.rstrip("-local") not in settings.ENABLE_SUBS_PROVIDER_TYPES:
            LOG.info(log_json(tracing_id, msg="provider type not valid for subs processing", context=context))
            continue
        if not enable_subs_extraction(schema_name, metered):
            LOG.info(log_json(tracing_id, msg="subs processing not enabled for provider", context=context))
            continue
        month_start = get_month_start_from_report(report)
        if not month_start:
            LOG.info(log_json(tracing_id, msg="skipping report, no manifest found.", context=context))
            continue
        LOG.info(log_json(tracing_id, msg="collecting subs report data", context=context))
        extractor = SUBSDataExtractor(tracing_id, context=context)
        upload_keys = extractor.extract_data_to_s3(month_start)
        if upload_keys and enable_subs_messaging(schema_name):
            process_upload_keys_to_subs_message.delay(context, schema_name, tracing_id, upload_keys)


@celery_app.task(name="subs.tasks.process_upload_keys_to_subs_message", queue=SUBS_TRANSMISSION_QUEUE)
def process_upload_keys_to_subs_message(context, schema_name, tracing_id, upload_keys):
    """Process data from a list of S3 objects to kafka messages for consumption."""
    LOG.info(log_json(tracing_id, msg="processing subs data to kafka", context=context))
    messenger = SUBSDataMessenger(context, schema_name, tracing_id)
    messenger.process_and_send_subs_message(upload_keys)
