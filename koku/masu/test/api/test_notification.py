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

from api.iam.models import Tenant


@override_settings(ROOT_URLCONF="masu.urls")
class NotificationAPIViewTest(TestCase):
    """Test Cases for the Notification API."""

    def setUp(self):
        """Create test case setup."""
        super().setUp()
        Tenant.objects.get_or_create(schema_name="public")

    @patch("koku.middleware.MASU", return_value=True)
    @patch(
        "masu.celery.tasks.check_cost_model_status.delay",
        return_value=AsyncResult("dc350f15-ffc7-4fcb-92d7-2a9f1275568e"),
    )
    def test_notification(self, file_list, _):
        """Test the Notification endpoint."""
        url = reverse("notification")
        response = self.client.get(url)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Notification Request Task ID", body)

        url_w_params = url + "?provider_uuid=1&bill_date=2021-04-01"
        response = self.client.get(url_w_params)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Notification Request Task ID", body)
