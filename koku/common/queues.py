#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common place for queues"""
from common.enum import StrEnum
from masu.processor import is_customer_large
from masu.processor import is_customer_penalty

DEFAULT = "celery"


class DownloadQueue(StrEnum):
    DEFAULT = "download"
    XL = "download_xl"
    PENALTY_BOX = "download_penalty"


class OCPQueue(StrEnum):
    DEFAULT = "ocp"
    XL = "ocp_xl"
    PENALTY_BOX = "ocp_penalty"


class PriorityQueue(StrEnum):
    DEFAULT = "priority"
    XL = "priority_xl"
    PENALTY_BOX = "priority_penalty"


class SummaryQueue(StrEnum):
    DEFAULT = "summary"
    XL = "summary_xl"
    PENALTY_BOX = "summary_penalty"


class CostModelQueue(StrEnum):
    DEFAULT = "cost_model"
    XL = "cost_model_xl"
    PENALTY_BOX = "cost_model_penalty"


class RefreshQueue(StrEnum):
    DEFAULT = "refresh"
    XL = "refresh_xl"
    PENALTY_BOX = "refresh_penalty"


# any additional queues should be added to this list
QUEUE_LIST = [
    DEFAULT,
    DownloadQueue.DEFAULT,
    DownloadQueue.XL,
    DownloadQueue.PENALTY_BOX,
    OCPQueue.DEFAULT,
    OCPQueue.XL,
    OCPQueue.PENALTY_BOX,
    PriorityQueue.DEFAULT,
    PriorityQueue.XL,
    PriorityQueue.PENALTY_BOX,
    CostModelQueue.DEFAULT,
    CostModelQueue.XL,
    CostModelQueue.PENALTY_BOX,
    SummaryQueue.DEFAULT,
    SummaryQueue.XL,
    SummaryQueue.PENALTY_BOX,
]


def get_customer_queue(schema, queue_class=DownloadQueue, xl_provider=False):
    queue = queue_class.DEFAULT
    if is_customer_penalty(schema):
        queue = queue_class.PENALTY_BOX
    elif xl_provider or is_customer_large(schema):
        queue = queue_class.XL
    return queue
