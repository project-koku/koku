#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Asynchronous tasks."""
import logging

from koku import celery_app


LOG = logging.getLogger(__name__)

HCS_QUEUE = "hcs"

# any additional queues should be added to this list
QUEUE_LIST = [HCS_QUEUE]


@celery_app.task(name="masu.hcs.tasks.update_hcs_data", queue=HCS_QUEUE)
def update_hcs_report(start_date, end_date=None):
    """Update Hybrid Committed Spend report.

    Args:
        start_date  (str) The date to start populating the table.
        end_date    (str) The date to end on.

    Returns
        None

    """
    # TODO: implement for HCS
    LOG.info(f"OUTPUT FROM HCS TASK, Start-date: {start_date}, End-date: {end_date}")
