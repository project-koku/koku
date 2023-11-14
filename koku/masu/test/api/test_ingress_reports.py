#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ingress reports endpoint view."""
import logging
import uuid
from unittest.mock import patch

from celery.result import AsyncResult
from django.test.utils import override_settings
from django.urls import reverse

from masu.test import MasuTestCase

LOG = logging.getLogger(__name__)


@override_settings(ROOT_URLCONF="masu.urls")
class IngressReportsAPIViewTest(MasuTestCase):
    """Test Cases for the Ingress Reports API."""

    def setUp(self):
        """Create test case setup."""
        super().setUp()
        self.ingress_uuid = str(uuid.uuid4())

    @patch("koku.middleware.MASU", return_value=True)
    @patch(
        "masu.celery.tasks.check_report_updates.delay",
        return_value=AsyncResult("dc350f15-ffc7-4fcb-92d7-2a9f1275568e"),
    )
    def test_ingress_download(self, mock_task, _):
        """Test the ingress report download endpoint."""
        url = reverse("ingress_reports")
        response = self.client.get(url)
        body = response.json()
        self.assertEqual(response.status_code, 400)
        self.assertIn("schema_name must be supplied as a parameter.", body.get("Error"))

        url_w_params = url + "?schema_name=1&download"
        response = self.client.get(url_w_params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn("ingress_uuid must be supplied as a parameter for downloads.", body.get("Error"))

        url_w_params = url + "?schema_name=1"
        response = self.client.get(url_w_params)
        body = response.json()
        self.assertEqual(response.status_code, 400)
        self.assertIn("provider_uuid must be supplied as a parameter for fetching reports.", body.get("Error"))
