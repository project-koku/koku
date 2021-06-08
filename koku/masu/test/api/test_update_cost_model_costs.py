#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the update_cost_model_costs endpoint view."""
from unittest.mock import patch

from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from masu.processor.tasks import QUEUE_LIST


@override_settings(ROOT_URLCONF="masu.urls")
class UpdateCostModelCostTest(TestCase):
    """Test Cases for the update_cost_model_costs endpoint."""

    @patch("masu.api.update_cost_model_costs.Provider")
    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.update_cost_model_costs.chain")
    def test_get_update_cost_model_costs(self, mock_update, _, __):
        """Test the GET report_data endpoint."""
        params = {"schema": "acct10001", "provider_uuid": "3c6e687e-1a09-4a05-970c-2ccf44b0952e"}
        expected_key = "Update Cost Model Cost Task ID"

        response = self.client.get(reverse("update_cost_model_costs"), params)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_update.assert_called()

    @patch("masu.api.update_cost_model_costs.Provider")
    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.update_cost_model_costs.chain")
    def test_get_update_cost_model_costs_with_dates(self, mock_update, _, __):
        """Test the GET report_data endpoint."""
        params = {
            "schema": "acct10001",
            "provider_uuid": "3c6e687e-1a09-4a05-970c-2ccf44b0952e",
            "start_date": "01-03-2010",
            "end_date": "31-03-2010",
        }
        expected_key = "Update Cost Model Cost Task ID"

        response = self.client.get(reverse("update_cost_model_costs"), params)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_update.assert_called()

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.update_cost_model_costs.cost_task")
    def test_get_update_cost_model_costs_schema_missing(self, mock_update, _):
        """Test GET report_data endpoint returns a 400 for missing schema."""
        params = {"provider_uuid": "3c6e687e-1a09-4a05-970c-2ccf44b0952e"}
        expected_key = "Error"
        expected_message = "provider_uuid and schema_name are required parameters."

        response = self.client.get(reverse("update_cost_model_costs"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)

    @patch("masu.api.update_cost_model_costs.Provider")
    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.update_cost_model_costs.cost_task")
    def test_get_update_cost_model_costs_invalid_queue(self, mock_update, _, __):
        """Test GET report_data endpoint returns a 400 for invalid queue."""
        params = {
            "schema": "acct10001",
            "provider_uuid": "3c6e687e-1a09-4a05-970c-2ccf44b0952e",
            "start_date": "01-03-2010",
            "queue": "This-aint-a-real-queue",
        }
        expected_key = "Error"
        expected_message = f"'queue' must be one of {QUEUE_LIST}."

        response = self.client.get(reverse("update_cost_model_costs"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.update_cost_model_costs.cost_task")
    def test_get_update_cost_model_costs_provider_missing(self, mock_update, _):
        """Test GET report_data endpoint returns a 400 for missing schema."""
        params = {"schema": "acct10001"}
        expected_key = "Error"
        expected_message = "provider_uuid and schema_name are required parameters."

        response = self.client.get(reverse("update_cost_model_costs"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.update_cost_model_costs.chain")
    def test_get_update_cost_model_costs_with_non_existant_provider(self, mock_update, _):
        """Test the GET report_data endpoint."""
        params = {"schema": "acct10001", "provider_uuid": "3c6e687e-1a09-4a05-970c-2ccf44b0952e"}
        expected_key = "Error"
        expected_message = "Provider does not exist."

        response = self.client.get(reverse("update_cost_model_costs"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)
        mock_update.delay.assert_not_called()
