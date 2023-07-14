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
from api.utils import DateHelper
from hcs.tasks import get_start_and_end_from_manifest_id
from koku import celery_app
from subs.common import enable_subs_processing
from subs.common import SUBS_ACCEPTED_PROVIDERS


LOG = logging.getLogger(__name__)

SUBS_EXTRACTION_QUEUE = "subs_extraction"

# any additional queues should be added to this list
QUEUE_LIST = [SUBS_EXTRACTION_QUEUE]


@celery_app.task(name="subs.tasks.collect_subs_report_data_from_manifest", bind=True, queue=SUBS_EXTRACTION_QUEUE)
def collect_subs_report_data_from_manifest(reports_to_subs_summarize):
    """Implement the functionality of the new task"""

    dh = DateHelper()
    date_str_fmt = "%Y-%m-%d"
    reports = [report for report in reports_to_subs_summarize if report]
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
        if not enable_subs_processing(schema_name):
            LOG.info(log_json(tracing_id, msg="subs processing not enabled for provider", context=context))
            continue
        if report.get("start") and report.get("end"):
            LOG.debug(
                log_json(
                    tracing_id, msg="using start and end dates from the manifest for subs processing", context=context
                )
            )
            start_date = parser.parse(report.get("start")).date()
            end_date = parser.parse(report.get("end")).date()
        else:
            # GCP and OCI set report start and report end, AWS/Azure do not
            date_tuple = get_start_and_end_from_manifest_id(report.get("manifest_id"))
            if not date_tuple:
                LOG.debug(log_json(tracing_id, msg="skipping report, no manifest found", context=context))
                continue
            start_date, end_date = date_tuple

        start_date = start_date or dh.today.date() - datetime.timedelta(days=2)
        end_date = end_date or dh.today.date()
        if isinstance(start_date, str):
            start_date = datetime.datetime.strptime(start_date, date_str_fmt)
            end_date = datetime.datetime.strptime(end_date, date_str_fmt)
        LOG.info(log_json(tracing_id, msg="collecting subs report data", context=context))
        # TODO: To call SUBS extractor here
