#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the hcs_report_data endpoint view."""
from unittest.mock import patch

from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from api.utils import DateHelper


@override_settings(ROOT_URLCONF="masu.urls")
class HCSDataTests(TestCase):
    """Test Cases for the hcs_report_data endpoint."""

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_hcs_report_data_schema_missing(self, _):
        """Test GET hcs_report_data endpoint returns a 400 for missing schema."""
        start_date = DateHelper().today.date().strftime("%Y-%m-%d")
        params = {"start_date": start_date, "provider_uuid": "6e212746-484a-40cd-bba0-09a19d132d64"}
        expected_key = "Error"
        expected_message = "schema is a required parameter"

        response = self.client.get(reverse("hcs_report_data"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_hcs_report_data_provider_uuid_missing(self, _):
        """Test GET hcs_report_data endpoint returns a 400 for missing provider_uuid & provider_type."""
        start_date = DateHelper().today.date().strftime("%Y-%m-%d")
        params = {"start_date": start_date, "schema": "acct10001"}

        expected_key = "Error"
        expected_message = "provider_uuid or provider_type must be supplied as a parameter"

        response = self.client.get(reverse("hcs_report_data"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_hcs_report_data_start_date_missing(self, _):
        """Test GET hcs_report_data endpoint returns a 400 for missing start date."""
        params = {"schema": "acct10001", "provider_uuid": "6e212746-484a-40cd-bba0-09a19d132d64"}
        expected_key = "Error"
        expected_message = "start_date is a required parameter"

        response = self.client.get(reverse("hcs_report_data"), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)
