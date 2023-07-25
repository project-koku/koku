#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tasks for Subscriptions Watch"""
import datetime
import logging
import uuid

from dateutil import parser

from api.common import log_json
from api.provider.models import Provider
from hcs.tasks import get_start_and_end_from_manifest_id
from koku import celery_app
from koku import settings
from koku.feature_flags import fallback_development_true
from koku.feature_flags import UNLEASH_CLIENT
from masu.external.date_accessor import DateAccessor
from masu.util.common import convert_account
from subs.subs_data_extractor import SUBSDataExtractor
from subs.subs_data_messenger import SUBSDataMessenger

LOG = logging.getLogger(__name__)

SUBS_EXTRACTION_QUEUE = "subs_extraction"
SUBS_TRANSMISSION_QUEUE = "subs_transmission"

# any additional queues should be added to this list
QUEUE_LIST = [SUBS_EXTRACTION_QUEUE, SUBS_TRANSMISSION_QUEUE]

SUBS_ACCEPTED_PROVIDERS = (
    Provider.PROVIDER_AWS,
    Provider.PROVIDER_AWS_LOCAL,
    # Add additional accepted providers here
)


def check_subs_source_gate(schema_name: str) -> bool:
    """Checks if the specific source is selected for RHEL Metered processing."""
    # TODO: COST-4033 implement sources gate
    return False


def enable_subs_extraction(schema_name: str) -> bool:
    """Helper to determine if source is enabled for SUBS extraction."""
    schema_name = convert_account(schema_name)
    context = {"schema_name": schema_name}
    LOG.info(log_json(msg="enable_subs_extraction context", context=context))
    return bool(
        UNLEASH_CLIENT.is_enabled("cost-management.backend.subs-data-extraction", context, fallback_development_true)
        or settings.ENABLE_SUBS_DEBUG
        or check_subs_source_gate(schema_name)
    )


def enable_subs_messaging(schema_name: str) -> bool:
    """Helper to determine if source is enabled for SUBS messaging."""
    schema_name = convert_account(schema_name)
    context = {"schema_name": schema_name}
    LOG.info(log_json(msg="enable_subs_messaging context", context=context))
    return bool(
        UNLEASH_CLIENT.is_enabled("cost-management.backend.subs-data-messaging", context) or settings.ENABLE_SUBS_DEBUG
    )


@celery_app.task(name="subs.tasks.extract_subs_data_from_reports", queue=SUBS_EXTRACTION_QUEUE)
def extract_subs_data_from_reports(reports_to_extract):
    """Implement the functionality of the new task"""
    reports = [report for report in reports_to_extract if report]
    reports_deduplicated = [dict(t) for t in {tuple(d.items()) for d in reports}]
    for report in reports_deduplicated:
        schema_name = report.get("schema_name")
        provider_type = report.get("provider_type")
        provider_uuid = report.get("provider_uuid")
        tracing_id = report.get("tracing_id", report.get("manifest_uuid", str(uuid.uuid4())))
        context = {"schema": schema_name, "provider_type": provider_type, "provider_uuid": provider_uuid}
        if provider_type not in SUBS_ACCEPTED_PROVIDERS:
            LOG.info(log_json(tracing_id, msg="provider type not valid for subs processing", context=context))
            continue
        if not enable_subs_extraction(schema_name):
            LOG.info(log_json(tracing_id, msg="subs processing not enabled for provider", context=context))
            continue
        if report.get("start") and report.get("end"):
            LOG.debug(
                log_json(
                    tracing_id, msg="using start and end dates from the manifest for subs processing", context=context
                )
            )
            start_date = parser.parse(report.get("start"))
            end_date = parser.parse(report.get("end"))
        else:
            # GCP and OCI set report start and report end, AWS/Azure do not
            date_tuple = get_start_and_end_from_manifest_id(report.get("manifest_id"))
            if not date_tuple:
                LOG.debug(log_json(tracing_id, msg="skipping report, no manifest found.", context=context))
                continue
            start_date, end_date = date_tuple
        if start_date is None:
            start_date = DateAccessor().today() - datetime.timedelta(days=2)
        if end_date is None:
            end_date = DateAccessor().today()
        if isinstance(start_date, str):
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d")
        LOG.info(log_json(tracing_id, msg="collecting subs report data", context=context))
        extractor = SUBSDataExtractor(schema_name, provider_type, provider_uuid, tracing_id, context=context)
        upload_keys = extractor.extract_data_to_s3(start_date, end_date)
        if upload_keys and enable_subs_messaging(schema_name):
            process_upload_keys_to_subs_message.delay(context, schema_name, tracing_id, upload_keys)


@celery_app.task(name="subs.tasks.process_upload_keys_to_subs_message", queue=SUBS_TRANSMISSION_QUEUE)
def process_upload_keys_to_subs_message(context, schema_name, tracing_id, upload_keys):
    LOG.info(log_json(tracing_id, msg="processing subs data to kafka", context=context))
    messenger = SUBSDataMessenger(context, schema_name, tracing_id)
    messenger.process_and_send_subs_message(upload_keys)
