#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tasks for Hybrid Committed Spend (HCS)"""
import logging

from koku import celery_app


LOG = logging.getLogger(__name__)

HCS_QUEUE = "hcs"

# any additional queues should be added to this list
QUEUE_LIST = [HCS_QUEUE]


@celery_app.task(name="hcs.tasks.collect_hcs_report_data", queue=HCS_QUEUE)
def collect_hcs_report_data(start_date, end_date=None):
    """Update Hybrid Committed Spend report.

    Args:
        start_date  (str) The date to start populating the table.
        end_date    (str) The date to end on.

    Returns
        None

    """
    # TODO: implement for HCS
    if end_date:
        LOG.info(f"OUTPUT FROM HCS TASK, Start-date: {start_date}, End-date: {end_date}")
    else:
        LOG.info(f"OUTPUT FROM HCS TASK, Start-date: {start_date}")
