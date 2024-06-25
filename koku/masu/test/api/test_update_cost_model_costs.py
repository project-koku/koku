#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the update_cost_model_costs endpoint view."""
import datetime
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.test.utils import override_settings
from django.urls import reverse

from common.queues import QUEUE_LIST
from masu.test import MasuTestCase


@override_settings(ROOT_URLCONF="masu.urls")
class UpdateCostModelCostTest(MasuTestCase):
    """Test Cases for the update_cost_model_costs endpoint."""

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.update_cost_model_costs.cost_task")
    def test_get_update_cost_model_costs(self, mock_update, _):
        """Test the GET report_data endpoint."""
        params = {"schema": self.schema, "provider_uuid": self.ocp_provider_uuid}
        expected_key = "Update Cost Model Cost Task ID"
        response = self.client.get(reverse("update_cost_model_costs"), params)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_update.s.return_value.set.return_value.apply_async.assert_called()

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.update_cost_model_costs.cost_task")
    def test_get_update_cost_model_costs_with_dates(self, mock_update, _):
        """Test the GET report_data endpoint."""

        start_date = datetime.datetime(2023, 3, 3, tzinfo=settings.UTC)
        end_date = datetime.datetime(2023, 4, 4, tzinfo=settings.UTC)
        params = {
            "schema": self.schema,
            "provider_uuid": self.ocp_provider_uuid,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
        }
        expected_key = "Update Cost Model Cost Task ID"

        response = self.client.get(reverse("update_cost_model_costs"), params)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_update.s.return_value.set.return_value.apply_async.assert_called()

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.update_cost_model_costs.cost_task")
    def test_get_update_cost_model_costs_schema_missing(self, mock_update, _):
        """Test GET report_data endpoint returns a 400 for missing schema."""
        params = {"provider_uuid": self.ocp_provider_uuid}
        expected_key = "Error"
        expected_message = "provider_uuid and schema are required parameters."

        response = self.client.get(reverse("update_cost_model_costs"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.update_cost_model_costs.cost_task")
    def test_get_update_cost_model_costs_invalid_queue(self, mock_update, _):
        """Test GET report_data endpoint returns a 400 for invalid queue."""
        params = {
            "schema": self.schema,
            "provider_uuid": self.ocp_provider_uuid,
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
        params = {"schema": self.schema}
        expected_key = "Error"
        expected_message = "provider_uuid and schema are required parameters."

        response = self.client.get(reverse("update_cost_model_costs"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.update_cost_model_costs.cost_task")
    def test_get_update_cost_model_costs_with_non_existant_provider(self, mock_update, _):
        """Test the GET report_data endpoint."""
        params = {"schema": self.schema, "provider_uuid": uuid4()}
        expected_key = "Error"
        expected_message = "Provider does not exist."

        response = self.client.get(reverse("update_cost_model_costs"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)
        mock_update.delay.assert_not_called()
