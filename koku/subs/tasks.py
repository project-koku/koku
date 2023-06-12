#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tasks for Subscriptions Watch"""
import logging

from koku import celery_app

LOG = logging.getLogger(__name__)

SUBS_QUEUE = "subs"

# any additional queues should be added to this list
QUEUE_LIST = [SUBS_QUEUE]


@celery_app.task(name="subs.tasks.collect_subs_cur_data", queue=SUBS_QUEUE)  # noqa: C901
def collect_subs_cur_data(start_date, end_date=""):
    """Collect Subscription Watch cost-usage report data
    Args:
        start_date:         (str) The date to start populating the table
        end_date:           (str) The date to stop populating the table

    Returns:
        None
    """

    LOG.info(f"Running SUBS task. Start-date: {start_date}. End-date: {end_date}")

    # TODO: implement for SUBS
