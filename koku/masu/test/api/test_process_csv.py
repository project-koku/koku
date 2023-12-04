#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the reprocess_csv_reports endpoint view."""
from unittest.mock import patch

from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from api.models import Provider


@override_settings(ROOT_URLCONF="masu.urls")
class ReprocessCSVAPIViewTest(TestCase):
    """Test Cases for the Reprocess CSV's API."""

    def setUp(self):
        """Create test case setup."""
        super().setUp()
        self.provider_type = Provider.PROVIDER_AWS_LOCAL
        p = Provider.objects.filter(type=self.provider_type).first()
        self.provider_uuid = str(p.uuid)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.processor.orchestrator.Orchestrator.start_manifest_processing", return_value=([], True))
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.orchestrator.record_report_status", return_value=True)
    @patch("masu.processor.orchestrator.chord")
    @patch("masu.processor.orchestrator.ReportDownloader.download_manifest")
    def test_reprocess_csv_reports(self, mock_download_manifest, mock_chord, mock_record, mock_inspect, mock_task, _):
        """Test the reprocess csv reports endpoint."""
        url = reverse("reprocess_csv_reports")
        url_w_params = url + "?provider_uuid=1"
        response = self.client.get(url_w_params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn("start_date must be supplied as a parameter.", body.get("Error"))

        url_w_params = url + "?start_date=2021-04-01"
        response = self.client.get(url_w_params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn("provider_uuid must be supplied as a parameter.", body.get("Error"))

        url_w_params = url + "?provider_uuid=1&start_date=2021-04-01&queue=test"
        response = self.client.get(url_w_params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn("'queue' must be one of", body.get("Error"))

        url_w_params = url + f"?provider_uuid={self.provider_uuid}&start_date=2021-04-01"
        response = self.client.get(url_w_params)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Triggering provider reprocessing", body)
