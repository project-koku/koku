#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Interactions with the notifications service."""
import datetime
import json
import logging
import uuid

from kafka_utils.utils import delivery_callback
from kafka_utils.utils import get_producer
from masu.config import Config
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.prometheus_stats import KAFKA_CONNECTION_ERRORS_COUNTER

LOG = logging.getLogger(__name__)


class NotificationService:
    """A class to handle interactions with the Notifications service."""

    def __init__(self):
        """Initialize Notifications class"""
        self.msg_uuid = str(uuid.uuid4())
        self.timestamp = datetime.datetime.utcnow().isoformat()
        # TODO Protecting your Kafka messages against duplicate processing
        # add header RecordHeaders().add("rh-message-id", messageId)
        # encoded_id = msg_uuid.encode()
        # message_id = bytearray(encoded_id)

    def build_notification_json(self, account, event_type, host_url, description):
        """
        Build json message for sending to notifications service
        Args:
            account (Object): account object for notifications being sent
            event_type (String): notification event type
            host_url (String): URL for notification event
            description (String): Description of event being sent
        Returns:
            notification message
        """
        provider_uuid = account.get("provider_uuid")
        with ProviderDBAccessor(provider_uuid) as provider_accessor:
            name = provider_accessor.get_provider_name()

        notification_json = {
            "id": self.msg_uuid,
            "bundle": "openshift",
            "application": "cost-management",
            "event_type": event_type,
            "timestamp": self.timestamp,
            "account_id": account.get("schema_name"),
            "context": {
                "source_id": str(provider_uuid),
                "source_name": name,
                "host_url": f"https://console.redhat.com/settings/sources/detail/{str(provider_uuid)}",
            },
            "events": [
                {
                    "metadata": {},
                    "payload": {
                        "description": description,
                        "host_url": host_url,
                    },
                }
            ],
        }
        msg = bytes(json.dumps(notification_json), "utf-8")
        LOG.info(f"Notification kafka message: {msg}")
        return msg

    @KAFKA_CONNECTION_ERRORS_COUNTER.count_exceptions()
    def send_notification(self, msg):
        """
        Send kafka notification message to Insights Notifications Service.
        Args:
            msg (string): message for kafka notification.
        Returns:
            None
        """
        producer = get_producer()
        producer.produce(Config.NOTIFICATION_TOPIC, value=msg, callback=delivery_callback)
        # Wait up to 1 second for events. Callbacks will be invoked during
        # this method call if the message is acknowledged.
        # `flush` makes this process synchronous compared to async with `poll`
        producer.flush(1)

    def cost_model_notification(self, account):
        """Send a cost-model to notification service via kafka"""
        event_type = "missing-cost-model"
        host_url = "https://console.redhat.com/openshift/cost-management/cost-models"
        description = "Openshift source has no cost model assigned, add one via the following link."
        msg = self.build_notification_json(account, event_type, host_url, description)
        self.send_notification(msg)
