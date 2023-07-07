#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tasks for Subscription Watch Data Extraction."""
import datetime
import logging
import uuid

from api.common import log_json
from api.utils import DateHelper
from koku import celery_app
from masu.util.common import convert_account

LOG = logging.getLogger(__name__)

SUBS_EXTRACTION_QUEUE = "subs_extraction"

# any additional queues should be added to this list
QUEUE_LIST = [SUBS_EXTRACTION_QUEUE]


@celery_app.task(
    name="subs.extraction.tasks.collect_subs_extraction_report_data",
    bind=True,
    queue=SUBS_EXTRACTION_QUEUE,
)
def collect_subs_extraction_report_data(
    self, schema_name, provider_type, provider_uuid, start_date=None, end_date=None, tracing_id=None
):
    """Implement the functionality of the new task
    Args:
        schema_name:    (str) db schema name
        provider_type:  (str) The provider type
        provider_uuid:  (str) The provider unique identification number
        start_date:     The date to start populating the table (default: (Today - 2 days))
        end_date:       The date to end on (default: Today)
        tracing_id:     (uuid) for log tracing

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

    # TODO: uncomment after COST-3893 is merged
    # if not (enable_subs_processing(schema_name) and provider_type in SUBS_ACCEPTED_PROVIDERS):
    #     LOG.info(log_json(tracing_id, msg="skipping subs data extraction", context=ctx))
    #     return

    # TODO: instantiate the ReportSUBS class and call generate_report when implemented.
    LOG.info(log_json(tracing_id, msg="collecting subs report data for extraction", context=ctx))
