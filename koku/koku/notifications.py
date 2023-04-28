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

    def build_notification_json(self, account, event_type, host_url, description, cost_model=None):
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
            account_id = provider_accessor.get_account_id()
            org_id = provider_accessor.get_org_id()

        account_id = account_id if account_id else ""
        org_id = org_id if org_id else ""

        if event_type in ["cost-model-create", "cost-model-update", "cost-model-remove"]:
            context = {
                "cost_model_id": str(cost_model.get("cost_model_uuid")),
                "cost_model_name": cost_model.get("cost_model_name"),
                "host_url": "https://console.redhat.com/openshift/cost-management/cost-models/",
            }
        else:
            context = {
                "source_id": str(provider_uuid),
                "source_name": name,
                "host_url": f"https://console.redhat.com/settings/sources/detail/{str(provider_uuid)}",
            }

        notification_json = {
            "id": self.msg_uuid,
            "bundle": "openshift",
            "application": "cost-management",
            "event_type": event_type,
            "timestamp": self.timestamp,
            "account_id": account_id,
            "org_id": org_id,
            "context": context,
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
        producer.poll(0)

    def cost_model_notification(self, account):
        """Send cost-model notifications via kafka"""
        event_type = "missing-cost-model"
        host_url = "https://console.redhat.com/openshift/cost-management/cost-models"
        description = "Openshift source has no cost model assigned, add one via the following link."
        msg = self.build_notification_json(account, event_type, host_url, description)
        self.send_notification(msg)

    def cost_model_crud_notification(self, account, cost_model, cost_model_type):
        """Send cost-model notifications via kafka"""
        event_type = f"cost-model-{cost_model_type}"
        host_url = "https://console.redhat.com/openshift/cost-management/cost-models"
        description = f"Cost model {cost_model_type}."
        msg = self.build_notification_json(account, event_type, host_url, description, cost_model)
        self.send_notification(msg)

    def ocp_stale_source_notification(self, account):
        """Send notifications for stale openshift clusters via kafka"""
        event_type = "cm-operator-stale"
        host_url = "https://console.redhat.com/openshift/cost-management/ocp"
        description = "Openshift source has not received data for at least 3 days."
        msg = self.build_notification_json(account, event_type, host_url, description)
        self.send_notification(msg)

    def ocp_data_processed_notification(self, account):
        """Send notifications for stale openshift clusters via kafka"""
        event_type = "cm-operator-data-processed"
        host_url = "https://console.redhat.com/openshift/cost-management/ocp"
        description = "Openshift cluster processing complete."
        msg = self.build_notification_json(account, event_type, host_url, description)
        self.send_notification(msg)

    def ocp_data_received_notification(self, account):
        """Send notifications for stale openshift clusters via kafka"""
        event_type = "cm-operator-data-received"
        host_url = "https://console.redhat.com/openshift/cost-management/ocp"
        description = "Openshift cluster data received for processing."
        msg = self.build_notification_json(account, event_type, host_url, description)
        self.send_notification(msg)
