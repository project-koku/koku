#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tasks for Hybrid Committed Spend (HCS)"""
import logging
import uuid

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
    """Helper to determine if source is enabled for HCS

    :param schema_name:  (Str) db schema name

    :returns None
    """
    if schema_name and not schema_name.startswith("acct"):
        schema_name = f"acct{schema_name}"

    context = {"schema": schema_name}
    LOG.info(f"enable_hcs_processing context: {context}")
    return bool(UNLEASH_CLIENT.is_enabled("hcs-data-processor", context))


@celery_app.task(name="hcs.tasks.collect_hcs_report_data", queue=HCS_QUEUE)
def collect_hcs_report_data(
    schema_name,
    provider,
    provider_uuid,
    start_date=DateHelper().today,
    end_date=DateHelper().today,
    tracing_id=str(uuid.uuid4()),
):
    """Update Hybrid Committed Spend report.
    :param schema_name:     (Str) db schema name
    :param provider:        (str) The provider type
    :param provider_uuid:   (str) The provider type
    :param start_date:      (date)The date to start populating the table (default: today)
    :param end_date:        (date)The date to end populating the table (default: today)
    :param tracing_id:      (uuid) for log tracing (default: a generated uuid)

    :returns None
    """

    if schema_name and not schema_name.startswith("acct"):
        schema_name = f"acct{schema_name}"

    if enable_hcs_processing(schema_name) and provider in (Provider.PROVIDER_AWS, Provider.PROVIDER_AZURE):
        reporter = ReportHCS(schema_name, provider, provider_uuid, tracing_id)

        stmt = (
            f"start HCS data collection for schema_name: {schema_name}, provider_uuid: {provider_uuid}, "
            f"provider: {provider}, "
            f"date(s): {start_date} - {end_date}"
        )

        reporter.generate_report(start_date, end_date)

    else:
        stmt = (
            f"[SKIPPED] customer not registered with HCS: "
            f"Schema-name: {schema_name}, provider: {provider}, provider_uuid: {provider_uuid}"
        )
        LOG.info(log_json(tracing_id, stmt))
