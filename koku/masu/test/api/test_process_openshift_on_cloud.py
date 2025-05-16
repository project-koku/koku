#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the process_openshift_on_cloud endpoint view."""
from unittest.mock import patch
from uuid import uuid4

from django.test.utils import override_settings
from django.urls import reverse

from api.utils import DateHelper
from common.queues import QUEUE_LIST
from masu.test import MasuTestCase


@override_settings(ROOT_URLCONF="masu.urls")
class ProcessOpenShiftOnCloudTest(MasuTestCase):
    """Test Cases for the process_openshift_on_cloud endpoint."""

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.process_openshift_on_cloud.process_openshift_on_cloud_task")
    def test_get_process_openshift_on_cloud(self, mock_process, _):
        """Test the GET report_data endpoint."""
        dh = DateHelper()
        start_date = str(dh.this_month_start.date())
        end_date = str(dh.this_month_end.date())
        params = {
            "schema": self.schema,
            "provider_uuid": self.aws_provider_uuid,
            "start_date": start_date,
            "end_date": end_date,
        }
        expected_key = "process_openshift_on_cloud Task IDs"
        response = self.client.get(reverse("process_openshift_on_cloud"), params)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_process.s.return_value.apply_async.assert_called()

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.process_openshift_on_cloud.process_openshift_on_cloud_task")
    def test_get_process_openshift_on_cloud_schema_missing(self, mock_process, _):
        """Test GET report_data endpoint returns a 400 for missing schema."""
        params = {
            "provider_uuid": self.ocpaws_provider_uuid,
            "start_date": "2022-01-01",
            "end_date": "2022-01-30",
        }
        expected_key = "Error"
        expected_message = "schema is a required parameter."

        response = self.client.get(reverse("process_openshift_on_cloud"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.process_openshift_on_cloud.process_openshift_on_cloud_task")
    def test_get_process_openshift_on_cloud_invalid_queue(self, mock_process, _):
        """Test GET report_data endpoint returns a 400 for invalid queue."""
        params = {
            "schema": self.schema,
            "provider_uuid": self.ocpaws_provider_uuid,
            "start_date": "2022-01-01",
            "queue": "This-aint-a-real-queue",
        }
        expected_key = "Error"
        expected_message = f"'queue' must be one of {QUEUE_LIST}."

        response = self.client.get(reverse("process_openshift_on_cloud"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.process_openshift_on_cloud.process_openshift_on_cloud_task")
    def test_get_process_openshift_on_cloud_provider_missing(self, mock_process, _):
        """Test GET report_data endpoint returns a 400 for missing schema."""
        params = {
            "schema": self.schema,
            "start_date": "2022-01-01",
            "end_date": "2022-01-30",
        }
        expected_key = "Error"
        expected_message = "provider_uuid is a required parameter."

        response = self.client.get(reverse("process_openshift_on_cloud"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.process_openshift_on_cloud.process_openshift_on_cloud_task")
    def test_get_process_openshift_on_cloud_with_non_existant_provider(self, mock_process, _):
        """Test the GET report_data endpoint."""
        bad_uuid = uuid4()
        params = {
            "schema": self.schema,
            "provider_uuid": bad_uuid,
            "start_date": "2022-01-01",
            "end_date": "2022-01-30",
        }
        expected_key = "Error"
        expected_message = f"provider_uuid: {bad_uuid} does not exist."

        response = self.client.get(reverse("process_openshift_on_cloud"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)
        mock_process.delay.assert_not_called()

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.process_openshift_on_cloud.process_daily_openshift_on_cloud_task")
    def test_get_process_daily_openshift_on_cloud(self, mock_process, _):
        """Test the GET report_data endpoint for a provider that is daily partitioned."""
        dh = DateHelper()
        start_date = str(dh.this_month_start.date())
        end_date = str(dh.this_month_end.date())
        params = {
            "schema": self.schema,
            "provider_uuid": self.gcp_provider_uuid,
            "start_date": start_date,
            "end_date": end_date,
        }
        expected_key = "process_openshift_on_cloud Task IDs"
        response = self.client.get(reverse("process_openshift_on_cloud"), params)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_process.s.return_value.apply_async.assert_called()
