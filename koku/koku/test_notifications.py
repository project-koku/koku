#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the NOTIFICATION Service interaction."""
from unittest.mock import patch

from django.test import TestCase

from api.provider.models import Provider
from koku.notifications import NotificationService

# from django.forms.models import model_to_dict
# from django_tenants.utils import schema_context
# from cost_models.models import CostModelMap


class NotificationsTest(TestCase):
    """Test Notifications object."""

    @patch("koku.notifications.NotificationService.send_notification", return_result=True)
    def test_cost_model_notification(self, mock_send_notification):
        """Test triggering a cost model notification."""
        provider = Provider.objects.first()
        notification = NotificationService()
        notification.cost_model_notification(provider)
        mock_send_notification.assert_called()

    # @patch("koku.notifications.NotificationService.send_notification", return_result=True)
    # def test_cost_model_crud_notification(self, mock_send_notification):
    #     """Test triggering a cost model crud notification."""
    #     with schema_context("org1234567"):
    #         cmm = CostModelMap.objects.first()
    #         cost_model = model_to_dict(cmm.cost_model, fields=["uuid", "name"])
    #         provider = Provider.objects.get(uuid=cmm.provider_uuid)
    #     notification = NotificationService()
    #     cost_model_types = ["create", "update", "remove"]
    #     for cmt in cost_model_types:
    #         notification.cost_model_crud_notification(provider, cost_model, cmt)
    #         mock_send_notification.assert_called()

    @patch("koku.notifications.NotificationService.send_notification", return_result=True)
    def test_ocp_stale_cluster_notification(self, mock_send_notification):
        """Test triggering a stale cluster notification."""
        provider = Provider.objects.first()
        notification = NotificationService()
        notification.ocp_stale_source_notification(provider)
        mock_send_notification.assert_called()

    # @patch("koku.notifications.NotificationService.send_notification", return_result=True)
    # def test_ocp_data_processed_notification(self, mock_send_notification):
    #     """Test triggering a processed cluster notification."""
    #     provider = Provider.objects.first()
    #     notification = NotificationService()
    #     notification.ocp_data_processed_notification(provider)
    #     mock_send_notification.assert_called()

    # @patch("koku.notifications.NotificationService.send_notification", return_result=True)
    # def test_ocp_data_received_notification(self, mock_send_notification):
    #     """Test triggering data received cluster notification."""
    #     provider = Provider.objects.first()
    #     notification = NotificationService()
    #     notification.ocp_data_received_notification(provider)
    #     mock_send_notification.assert_called()

    @patch("koku.notifications.get_producer")
    def test_send_notification(self, mock_producer):
        """Test sending notification payload."""
        msg = "notification-test-message"
        notification = NotificationService()
        notification.send_notification(msg)
        mock_producer.assert_called()

    def test_building_notification_json(self):
        """Test sending notification payload."""
        provider = Provider.objects.first()
        event_type = "testing-event"
        host_url = "test-url"
        description = "test notification description"
        notification = NotificationService()
        msg = notification.build_notification_json(provider, event_type, host_url, description)
        assert bytes(event_type, "utf-8") in msg
        assert bytes(host_url, "utf-8") in msg
        assert bytes(description, "utf-8") in msg
