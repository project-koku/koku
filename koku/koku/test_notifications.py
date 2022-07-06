#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the NOTIFICATION Service interaction."""
from unittest.mock import patch

from django.test import TestCase

from koku.notifications import NotificationService
from masu.external.accounts_accessor import AccountsAccessor


class NotificationsTest(TestCase):
    """Test Notifications object."""

    @patch("koku.notifications.NotificationService.send_notification", return_result=True)
    def test_cost_model_notification(self, mock_send_notification):
        """Test triggering a cost model notification."""
        polling_accounts = AccountsAccessor().get_accounts()
        notification = NotificationService()
        notification.cost_model_notification(polling_accounts[0])
        mock_send_notification.assert_called()

    @patch("koku.notifications.get_producer")
    def test_send_notification(self, mock_producer):
        """Test sending notification payload."""
        msg = "notification-test-message"
        notification = NotificationService()
        notification.send_notification(msg)
        mock_producer.assert_called()

    def test_building_notification_json(self):
        """Test sending notification payload."""
        account = AccountsAccessor().get_accounts()[0]
        event_type = "testing-event"
        host_url = "test-url"
        description = "test notification description"
        notification = NotificationService()
        msg = notification.build_notification_json(account, event_type, host_url, description)
        assert bytes(event_type, "utf-8") in msg
        assert bytes(host_url, "utf-8") in msg
        assert bytes(description, "utf-8") in msg
