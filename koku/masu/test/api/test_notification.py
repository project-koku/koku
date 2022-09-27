#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Notification endpoint view."""
from unittest.mock import patch

from celery.result import AsyncResult
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from api.iam.models import Tenant


@override_settings(ROOT_URLCONF="masu.urls")
class NotificationAPIViewTest(TestCase):
    """Test Cases for the Notification API."""

    def setUp(self):
        """Create test case setup."""
        super().setUp()
        self.client = APIClient()
        Tenant.objects.get_or_create(schema_name="public")

    @patch("koku.middleware.MASU", return_value=True)
    def test_notification_endpoint_no_param(self, file_list):
        """Test the Notification cost model endpoint."""
        url = reverse("notification")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)

    @patch("koku.middleware.MASU", return_value=True)
    def test_notification_endpoint_invalid_uuid(self, file_list):
        """Test the Notification cost model endpoint."""
        url_w_params = reverse("notification") + "?cost_model_check&provider_uuid=dc"
        response = self.client.get(url_w_params)
        self.assertEqual(response.status_code, 400)

    @patch("koku.middleware.MASU", return_value=True)
    @patch(
        "masu.celery.tasks.check_cost_model_status.delay",
        return_value=AsyncResult("dc350f15-ffc7-4fcb-92d7-2a9f1275568e"),
    )
    def test_notification_cost_model(self, file_list, _):
        """Test the Notification cost model endpoint."""
        url = reverse("notification")
        params = {"cost_model_check": ""}
        response = self.client.get(url, params)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn("Notification Request Task ID", body)

        url_w_params = reverse("notification") + "?cost_model_check&provider_uuid=dc350f15-ffc7-4fcb-92d7-2a9f1275568e"
        response = self.client.get(url_w_params)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn("Notification Request Task ID", body)

    @patch("koku.middleware.MASU", return_value=True)
    @patch(
        "masu.celery.tasks.check_for_stale_ocp_source.delay",
        return_value=AsyncResult("dc350f15-ffc7-4fcb-92d7-2a9f1275568e"),
    )
    def test_notification_stale_cluster(self, file_list, _):
        """Test the Notification stale cluster endpoint."""
        url = reverse("notification")
        params = {"stale_ocp_check": ""}
        response = self.client.get(url, params)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn("Notification Request Task ID", body)

        url_w_params = reverse("notification") + "?stale_ocp_check&provider_uuid=dc350f15-ffc7-4fcb-92d7-2a9f1275568e"
        response = self.client.get(url_w_params)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn("Notification Request Task ID", body)
