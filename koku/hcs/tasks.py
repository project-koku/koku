#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tasks for Hybrid Committed Spend (HCS)"""
import logging
import uuid
from datetime import timedelta

from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from hcs.daily_report import ReportHCS
from koku import celery_app
from koku.feature_flags import UNLEASH_CLIENT

LOG = logging.getLogger(__name__)

HCS_QUEUE = "hcs"

# any additional queues should be added to this list
QUEUE_LIST = [HCS_QUEUE]


def enable_hcs_processing(schema_name):  # pragma: no cover #noqa
    """Helper to determine if source is enabled for HCS."""
    if schema_name and not schema_name.startswith("acct"):
        schema_name = f"acct{schema_name}"

    context = {"schema": schema_name}
    LOG.info(f"enable_hcs_processing context: {context}")
    return bool(UNLEASH_CLIENT.is_enabled("hcs-data-processor", context))


@celery_app.task(name="hcs.tasks.collect_hcs_report_data", queue=HCS_QUEUE)
def collect_hcs_report_data(schema_name, provider, provider_uuid, start_date=None, end_date=None, tracing_id=None):
    """Update Hybrid Committed Spend report.
    :param provider:        (str) The provider type
    :param provider_uuid:   (str) The provider type
    :param start_date:      The date to start populating the table (default: (Today - 2 days))
    :param end_date:        The date to end on (default: Today)
    :param schema_name:     (Str) db schema name
    :param tracing_id:      (uuid) for log tracing

    :returns None
    """

    if enable_hcs_processing(schema_name) and provider in (
        Provider.PROVIDER_AWS,
        Provider.PROVIDER_AZURE,
        Provider.OCI,
    ):
        if schema_name and not schema_name.startswith("acct"):
            schema_name = f"acct{schema_name}"

        if start_date is None:
            start_date = DateHelper().today - timedelta(days=2)

        if end_date is None:
            end_date = DateHelper().today

        if tracing_id is None:
            tracing_id = str(uuid.uuid4())

        stmt = (
            f"Running HCS data collection: "
            f"schema_name: {schema_name}, "
            f"provider_uuid: {provider_uuid}, "
            f"provider: {provider}, "
            f"dates {start_date} - {end_date}"
        )
        LOG.info(log_json(tracing_id, stmt))
        reporter = ReportHCS(schema_name, provider, provider_uuid, tracing_id)
        reporter.generate_report(start_date, end_date)

    else:
        stmt = (
            f"[SKIPPED] Customer not registered with HCS: "
            f"Schema-name: {schema_name}, "
            f"provider: {provider}, "
            f"provider_uuid: {provider_uuid}, "
            f"dates {start_date} - {end_date}"
        )
        LOG.info(log_json(tracing_id, stmt))
