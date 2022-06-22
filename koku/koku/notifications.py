#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Interactions with the notifications service."""
import logging

from prometheus_client import Counter
from requests.exceptions import ConnectionError

from koku.configurator import CONFIGURATOR
from koku.env import ENVIRONMENT
from masu.external.kafka_msg_handler import send_notification


LOG = logging.getLogger(__name__)
NOTIFICATIONS_CONNECTION_ERROR_COUNTER = Counter(
    "notifications_connection_errors", "Number of NOTIFICATIONS ConnectionErros."
)
PROTOCOL = "protocol"
HOST = "host"
PORT = "port"
PATH = "path"


class NotificationsConnectionError(ConnectionError):
    """Exception for Notifications ConnectionErrors."""


class NotificationsService:
    """A class to handle interactions with the Notifications service."""

    def __init__(self):
        """Establish Notifications connection information."""
        notifications_conn_info = self._get_notifications_service()
        self.protocol = notifications_conn_info.get(PROTOCOL)
        self.host = notifications_conn_info.get(HOST)
        self.port = notifications_conn_info.get(PORT)
        self.path = notifications_conn_info.get(PATH)

    def _get_notifications_service(self):
        """Get NOTIFICATIONS service host and port info from environment."""
        return {
            PROTOCOL: ENVIRONMENT.get_value("NOTIFICATIONS_SERVICE_PROTOCOL", default="http"),
            HOST: CONFIGURATOR.get_endpoint_host("notifications", "service", "localhost"),
            PORT: CONFIGURATOR.get_endpoint_port("notifications", "service", "8111"),
            PATH: ENVIRONMENT.get_value("NOTIFICATIONS_SERVICE_PATH", default="/api/notifications-gw/notifications"),
        }

    def cost_model_notification(self, account):
        """Send a notification to notifications service via kafka"""
        event_type = "missing-cost-model"
        send_notification(account, event_type)
