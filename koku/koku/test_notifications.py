#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the NOTIFICATION Service interaction."""
from unittest.mock import patch

from django.test import TestCase

from api.provider.models import Provider
from koku.notifications import NotificationService


class NotificationsTest(TestCase):
    """Test Notifications object."""

    @patch("koku.notifications.NotificationService.send_notification", return_result=True)
    def test_cost_model_notification(self, mock_send_notification):
        """Test triggering a cost model notification."""
        polling_accounts = Provider.objects.get_accounts()
        notification = NotificationService()
        notification.cost_model_notification(polling_accounts[0])
        mock_send_notification.assert_called()

    @patch("koku.notifications.NotificationService.send_notification", return_result=True)
    def test_cost_model_crud_notification(self, mock_send_notification):
        """Test triggering a cost model crud notification."""
        polling_accounts = Provider.objects.get_accounts()
        notification = NotificationService()
        cost_model = {"cost_model_uuid": "1234", "cost_model_name": "My cost model"}
        cost_model_types = ["create", "update", "remove"]
        for cmt in cost_model_types:
            notification.cost_model_crud_notification(polling_accounts[0], cost_model, cmt)
            mock_send_notification.assert_called()

    @patch("koku.notifications.NotificationService.send_notification", return_result=True)
    def test_ocp_stale_cluster_notification(self, mock_send_notification):
        """Test triggering a stale cluster notification."""
        polling_accounts = Provider.objects.get_accounts()
        notification = NotificationService()
        notification.ocp_stale_source_notification(polling_accounts[0])
        mock_send_notification.assert_called()

    @patch("koku.notifications.NotificationService.send_notification", return_result=True)
    def test_ocp_data_processed_notification(self, mock_send_notification):
        """Test triggering a processed cluster notification."""
        polling_accounts = Provider.objects.get_accounts()
        notification = NotificationService()
        notification.ocp_data_processed_notification(polling_accounts[0])
        mock_send_notification.assert_called()

    @patch("koku.notifications.NotificationService.send_notification", return_result=True)
    def test_ocp_data_received_notification(self, mock_send_notification):
        """Test triggering data received cluster notification."""
        polling_accounts = Provider.objects.get_accounts()
        notification = NotificationService()
        notification.ocp_data_received_notification(polling_accounts[0])
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
        account = Provider.objects.get_accounts()[0]
        event_type = "testing-event"
        host_url = "test-url"
        description = "test notification description"
        notification = NotificationService()
        msg = notification.build_notification_json(account, event_type, host_url, description)
        assert bytes(event_type, "utf-8") in msg
        assert bytes(host_url, "utf-8") in msg
        assert bytes(description, "utf-8") in msg
