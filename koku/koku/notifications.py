#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Interactions with the notifications service."""
import json
import logging

from kafka_utils.utils import get_producer
from masu.config import Config
from masu.prometheus_stats import KAFKA_CONNECTION_ERRORS_COUNTER

# import uuid

# from masu.external.date_accessor import DateAccessor

LOG = logging.getLogger(__name__)


def cost_model_notification(account):
    """Send a notification to notifications service via kafka"""
    event_type = "missing-cost-model"
    send_notification(account, event_type)


@KAFKA_CONNECTION_ERRORS_COUNTER.count_exceptions()
def send_notification(account, event_type):
    """
    Send kafka notification message to Insights Notifications Service.
    Args:
        account (Object): account for notifications being sent.
        notification (String): Notification string
        uuid (UUID): uuid of object in question
    Returns:
        None
    """
    # encoded_id = str(uuid.uuid4()).encode()
    # message_id = bytearray(encoded_id)
    producer = get_producer()
    # notification_json = {
    #     "id": message_id,
    #     "bundle": "openshift",
    #     "application": "cost-management",
    #     "event_type": event_type,
    #     "timestamp": DateAccessor().today(),
    #     "account_id": account.get("schema_name"),
    #     "org_id": account.get("org_id"),
    #     "context": {
    #         "source_id": account.get("provider_uuid"),
    #         "source_name": account.get("name"),
    #         "host_url": f"https://console.redhat.com/settings/sources/detail/{account.get('provider_uuid')}",
    #     },
    #     "events": [
    #         {
    #             "metadata": {},
    #             "payload": {
    #                 "description": "Openshift source has no cost model assigned, add one via the following link.",
    #                 "host_url": "https://console.redhat.com/openshift/cost-management/cost-models",
    #             },
    #         }
    #     ],
    # }
    data = {
        "id": "message_id",
        "bundle": "openshift",
        "application": "cost-management",
        "event_type": "event_type",
        "timestamp": "DateAccessor().today()",
        "account_id": "account.get(",
        "org_id": "org_id",
        "context": {
            "source_id": "provider_uuid",
            "source_name": "name",
            "host_url": "https://console.redhat.com/settings/sources/detail/",
        },
        "events": [
            {
                "metadata": {},
                "payload": {
                    "description": "Openshift source has no cost model assigned, add one via the following link.",
                    "host_url": "https://console.redhat.com/openshift/cost-management/cost-models",
                },
            }
        ],
    }
    msg = bytes(json.dumps(data), "utf-8")
    producer.produce(Config.NOTIFICATION_TOPIC, value=msg)
    # Wait up to 1 second for events. Callbacks will be invoked during
    # this method call if the message is acknowledged.
    # `flush` makes this process synchronous compared to async with `poll`
    producer.flush(1)
