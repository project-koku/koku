#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the expired_endpoint endpoint view."""
from unittest.mock import patch
from urllib.parse import urlencode

from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from masu.config import Config
from masu.processor.orchestrator import Orchestrator


@override_settings(ROOT_URLCONF="masu.urls")
class ExpiredDataTest(TestCase):
    """Test Cases for the expired_data endpoint."""

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("koku.middleware.MASU", return_value=True)
    @patch.object(Orchestrator, "remove_expired_report_data")
    def test_get_expired_data(self, mock_orchestrator, _, mock_service):
        """Test the GET expired_data endpoint."""
        mock_response = [{"customer": "acct10001", "async_id": "f9eb2ce7-4564-4509-aecc-1200958c07cf"}]
        expected_key = "Async jobs for expired data removal (simulated)"
        mock_orchestrator.return_value = mock_response
        response = self.client.get(reverse("expired_data"))
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        self.assertIn(str(mock_response), body.get(expected_key))

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("koku.middleware.MASU", return_value=True)
    @patch.object(Config, "DEBUG", return_value=False)
    @patch.object(Orchestrator, "remove_expired_report_data")
    def test_del_expired_data(self, mock_orchestrator, mock_debug, _, mock_service):
        """Test the DELETE expired_data endpoint."""
        mock_response = [{"customer": "acct10001", "async_id": "f9eb2ce7-4564-4509-aecc-1200958c07cf"}]
        expected_key = "Async jobs for expired data removal"
        mock_orchestrator.return_value = mock_response

        response = self.client.delete(reverse("expired_data"))
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        self.assertIn(str(mock_response), body.get(expected_key))

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("koku.middleware.MASU", return_value=True)
    @patch.object(Orchestrator, "remove_expired_report_data")
    def test_get_expired_data_line_items_only(self, mock_orchestrator, _, mock_service):
        """Test the GET expired_data endpoint."""
        mock_response = [{"customer": "acct10001", "async_id": "f9eb2ce7-4564-4509-aecc-1200958c07cf"}]
        expected_key = "Async jobs for expired data removal (simulated)"
        mock_orchestrator.return_value = mock_response
        params = {"line_items_only": "True"}
        query_string = urlencode(params)
        url = reverse("expired_data") + "?" + query_string
        response = self.client.delete(url)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        self.assertIn(str(mock_response), body.get(expected_key))

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("koku.middleware.MASU", return_value=True)
    @patch.object(Config, "DEBUG", return_value=False)
    @patch.object(Orchestrator, "remove_expired_report_data")
    def test_del_expired_data_line_items_only(self, mock_orchestrator, mock_debug, _, mock_service):
        """Test the DELETE expired_data endpoint."""
        mock_response = [{"customer": "acct10001", "async_id": "f9eb2ce7-4564-4509-aecc-1200958c07cf"}]
        expected_key = "Async jobs for expired data removal"
        mock_orchestrator.return_value = mock_response
        params = {"line_items_only": "True"}
        query_string = urlencode(params)
        url = reverse("expired_data") + "?" + query_string
        response = self.client.delete(url)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        self.assertIn(str(mock_response), body.get(expected_key))

    @patch("koku.middleware.MASU", return_value=True)
    def test_bad_line_items_only_param(self, _):
        """Test the DELETE expired_data endpoint with bad param."""
        expected_key = "Error"
        error_message_substring = "The param line_items_only must be"
        params = {"line_items_only": "bad"}
        query_string = urlencode(params)
        url = reverse("expired_data") + "?" + query_string
        response = self.client.delete(url)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertIn(error_message_substring, body[expected_key])
