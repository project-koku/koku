#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from unittest.mock import patch

from django.test.utils import override_settings
from django.urls import reverse

from masu.test import MasuTestCase


@override_settings(ROOT_URLCONF="masu.urls")
class AWSBillCleanupTest(MasuTestCase):
    ENDPOINT = "aws_bill_cleanup"

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.aws_bill_cleanup.cleanup_aws_bills_task")
    def test_aws_bill_cleanup_no_params(self, mock_cleanup, _):
        """Test that no bill_date results in a 400."""
        params = {}
        expected_key = "Error"
        expected_message = "bill_date is a required parameter."
        response = self.client.get(reverse(self.ENDPOINT), params)
        body = response.json()
        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)
        mock_cleanup.s.assert_not_called()

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.aws_bill_cleanup.cleanup_aws_bills_task")
    def test_aws_bill_cleanup_bill_date(self, mock_cleanup, _):
        """Test that the appropriate task is triggered when passing a bill_date."""
        params = {
            "bill_date": "2023-12-01",
        }
        expected_bill_key = "bill_date"
        expected_bill_message = "2023-12-01"
        expected_task_key = "cleanup_aws_bills Task IDs"
        expected_task_schema = "org1234567"
        response = self.client.get(reverse(self.ENDPOINT), params)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_bill_key, body)
        self.assertEqual(expected_bill_message, body[expected_bill_key])
        self.assertIn(expected_task_key, body)
        self.assertIn(expected_task_schema, body[expected_task_key].keys())
        mock_cleanup.s.assert_called_once()

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.aws_bill_cleanup.cleanup_aws_bills_task")
    def test_aws_bill_cleanup_bill_date_and_schema(self, mock_cleanup, _):
        """Test that the appropriate task is triggered when passing a schema and bill_date."""
        params = {"bill_date": "2023-12-01", "schema": "org1234567"}
        expected_bill_key = "bill_date"
        expected_bill_message = "2023-12-01"
        expected_task_key = "cleanup_aws_bills Task IDs"
        expected_task_schema = "org1234567"
        response = self.client.get(reverse(self.ENDPOINT), params)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_bill_key, body)
        self.assertEqual(expected_bill_message, body[expected_bill_key])
        self.assertIn(expected_task_key, body)
        self.assertIn(expected_task_schema, body[expected_task_key].keys())
        mock_cleanup.s.assert_called_once()

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.aws_bill_cleanup.cleanup_aws_bills_task")
    def test_aws_bill_cleanup_fake_schema(self, mock_cleanup, _):
        """Test that a fake schema does not trigger the task."""
        params = {"bill_date": "2023-12-01", "schema": "org5678"}
        expected_bill_key = "bill_date"
        expected_bill_message = "2023-12-01"
        expected_task_key = "cleanup_aws_bills Task IDs"
        response = self.client.get(reverse(self.ENDPOINT), params)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_bill_key, body)
        self.assertEqual(expected_bill_message, body[expected_bill_key])
        self.assertIn(expected_task_key, body)
        self.assertEqual(body[expected_task_key], {})
        mock_cleanup.s.assert_not_called()

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.aws_bill_cleanup.cleanup_aws_bills_task")
    def test_aws_bill_cleanup_bad_queue(self, mock_cleanup, _):
        """Test that a bad queue results in a 400."""
        params = {"bill_date": "2023-12-01", "queue": "sandwich"}
        expected_key = "Error"
        expected_message = "'queue' must be one of"
        response = self.client.get(reverse(self.ENDPOINT), params)
        body = response.json()
        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertTrue(body[expected_key].startswith(expected_message))
        mock_cleanup.s.assert_not_called()

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.aws_bill_cleanup.cleanup_aws_bills_task")
    def test_aws_bill_cleanup_good_queue(self, mock_cleanup, _):
        """Test that a good queue results in a 200."""
        params = {"bill_date": "2023-12-01", "queue": "download"}
        expected_bill_key = "bill_date"
        expected_bill_message = "2023-12-01"
        expected_task_key = "cleanup_aws_bills Task IDs"
        expected_task_schema = "org1234567"
        response = self.client.get(reverse(self.ENDPOINT), params)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_bill_key, body)
        self.assertEqual(expected_bill_message, body[expected_bill_key])
        self.assertIn(expected_task_key, body)
        self.assertIn(expected_task_schema, body[expected_task_key].keys())
        mock_cleanup.s.assert_called_once()
