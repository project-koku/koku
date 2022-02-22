#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tasks for Hybrid Committed Spend (HCS)"""
import logging

from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from hcs import enable_HCS_processing
from koku import celery_app


LOG = logging.getLogger(__name__)

HCS_QUEUE = "hcs"

# any additional queues should be added to this list
QUEUE_LIST = [HCS_QUEUE]


@celery_app.task(name="hcs.tasks.collect_hcs_report_data", queue=HCS_QUEUE)
def collect_hcs_report_data(schema_name, provider, provider_uuid, start_date=None, end_date=None, tracing_id=None):
    """Update Hybrid Committed Spend report.
    :param provider:        (str) The provider type
    :param provider_uuid:   (str) The provider type
    :param start_date:      The date to start populating the table
    :param end_date:        The date to end on
    :param schema_name:     (String) db schema name
    :param tracing_id:      (uuid) for log tracing

    :returns None
    """

    if enable_HCS_processing(provider_uuid, provider, schema_name) and provider in (
        Provider.PROVIDER_AWS,
        Provider.PROVIDER_AWS_LOCAL,
        Provider.PROVIDER_AZURE,
        Provider.PROVIDER_AZURE_LOCAL,
    ):
        stmt = (
            f"Running HCS data collection for schema_name: {schema_name}, provider_uuid: {provider_uuid}, "
            f"provider: {provider}"
        )
        LOG.info(log_json(tracing_id, stmt))

        if start_date is None:
            start_date = DateHelper().today

        if end_date:
            LOG.info(f"OUTPUT FROM HCS TASK, Start-date: {start_date}, End-date: {end_date}")
        else:
            LOG.info(f"OUTPUT FROM HCS TASK, Start-date: {start_date}")
