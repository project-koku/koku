#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the hcs_report_data endpoint view."""
from unittest.mock import patch

from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from api.models import Provider
from api.utils import DateHelper


@override_settings(ROOT_URLCONF="masu.urls")
@patch("koku.middleware.MASU", return_value=True)
@patch("masu.api.hcs_report_finalization.collect_hcs_report_finalization")
class HCSFinalizationTests(TestCase):
    """Test Cases for the hcs_report_finalization endpoint."""

    ENDPOINT = "hcs_report_finalization"
    dh = DateHelper()

    def test_get_report_finalization_data(self, mock_celery, _):
        """Test the hcs_report_finalization endpoint."""

        expected_key = "HCS Report Finalization"

        response = self.client.get(reverse(self.ENDPOINT))
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_celery.s.assert_called()

    def test_get_report_finalization_month_negative(self, mock_celery, _):
        """Test the GET hcs_report_finalization endpoint with specified month but no year fails."""
        params = {
            "month": 1,
        }
        expected_errmsg = "month and year must be provided together."
        response = self.client.get(reverse(self.ENDPOINT), params)
        body = response.json()
        errmsg = body.get("Error")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(errmsg, expected_errmsg)

    def test_get_report_finalization_month_year(self, mock_celery, _):
        """Test the GET hcs_report_finalization endpoint with specified month & year"""

        expected_key = "2001-10"

        params = {
            "month": 10,
            "year": 2001,
        }

        response = self.client.get(reverse(self.ENDPOINT), params)
        body = response.json()
        result = body.get("HCS Report Finalization")[0].get("month")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(expected_key, result)
        mock_celery.s.assert_called()

    def test_get_report_finalization_neg_param(self, mock_celery, _):
        """Test GET hcs_report_finalization endpoint by providing bad parameter"""
        params = {
            "bogus": "bad_param",
        }
        response = self.client.get(reverse(self.ENDPOINT), params)

        self.assertEqual(response.status_code, 400)

    def test_get_report_finalization_year_negative(self, mock_celery, _):
        """Test the GET hcs_report_finalization endpoint for you must provide 'month' when providing 'year'"""
        params = {
            "year": 2001,
        }
        expected_errmsg = "month and year must be provided together."
        response = self.client.get(reverse(self.ENDPOINT), params)
        body = response.json()
        errmsg = body.get("Error")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(errmsg, expected_errmsg)

    def test_get_report_finalization_provider_type_provider_uuid_negative(self, mock_celery, _):
        """Test the GET hcs_report_finalization endpoint for
        'provider_type' and 'provider_uuid' are not supported in the same request"""
        params = {
            "provider_type": Provider.PROVIDER_AWS,
            "provider_uuid": 11111111 - 0000 - 1111 - 0000 - 111111111111,
        }
        expected_errmsg = "'provider_type' and 'provider_uuid' are not supported in the same request"
        response = self.client.get(reverse(self.ENDPOINT), params)
        body = response.json()
        errmsg = body.get("Error")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(errmsg, expected_errmsg)

    def test_get_report_finalization_schema_name_provider_uuid_negative(self, mock_celery, _):
        """Test the GET hcs_report_finalization endpoint for
        'schema_name' and 'provider_uuid' are not supported in the same request"""
        params = {
            "provider_uuid": 11111111 - 0000 - 1111 - 0000 - 111111111111,
            "schema_name": "acct10005",
        }
        expected_errmsg = "'schema_name' and 'provider_uuid' are not supported in the same request"
        response = self.client.get(reverse(self.ENDPOINT), params)
        body = response.json()
        errmsg = body.get("Error")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(errmsg, expected_errmsg)

    def test_get_report_finalization_future_month(self, mock_celery, _):
        """Test the GET hcs_report_finalization endpoint with a month in the future returns a 404"""
        params = {
            "month": self.dh.next_month_start.month,
            "year": self.dh.next_month_start.year,
        }

        expected_errmsg = "finalization can only be run on past months"

        response = self.client.get(reverse(self.ENDPOINT), params)
        body = response.json()
        errmsg = body.get("Error")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(errmsg, expected_errmsg)
