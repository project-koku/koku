#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AWS tag view."""
import calendar
from urllib.parse import quote_plus
from urllib.parse import urlencode

from dateutil.relativedelta import relativedelta
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.utils import DateHelper


class AWSTagsViewTest(IamTestCase):
    """Tests the report view."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        cls.dh = DateHelper()
        cls.ten_days_ago = cls.dh.n_days_ago(cls.dh._now, 9)

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()

    def _calculate_expected_range(self, time_scope_value, time_scope_units):
        today = self.dh.today

        if time_scope_value == "-1" and time_scope_units == "month":
            start_range = today.replace(day=1).date()
        elif time_scope_value == "-2" and time_scope_units == "month":
            start_range = (today - relativedelta(months=1)).replace(day=1).date()
        elif time_scope_value == "-10" and time_scope_units == "day":
            start_range = (today - relativedelta(days=10)).date()
        elif time_scope_value == "-30" and time_scope_units == "day":
            start_range = (today - relativedelta(days=30)).date()

        end_range = today.replace(day=calendar.monthrange(today.year, today.month)[1]).date()

        return start_range, end_range

    def test_execute_aws_tags_queries_keys_only(self):
        """Test that tag key data is for the correct time queries."""
        test_cases = [
            {"value": "-1", "unit": "month", "resolution": "monthly"},
            {"value": "-2", "unit": "month", "resolution": "monthly"},
            {"value": "-10", "unit": "day", "resolution": "daily"},
            {"value": "-30", "unit": "day", "resolution": "daily"},
        ]

        for case in test_cases:
            url = reverse("aws-tags")
            client = APIClient()
            params = {
                "filter[resolution]": case.get("resolution"),
                "filter[time_scope_value]": case.get("value"),
                "filter[time_scope_units]": case.get("unit"),
                "key_only": True,
            }
            url = url + "?" + urlencode(params, quote_via=quote_plus)
            response = client.get(url, **self.headers)

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()
            start_range, end_range = self._calculate_expected_range(case.get("value"), case.get("unit"))

            self.assertNotEqual(data.get("data"), [])
            self.assertTrue(isinstance(data.get("data"), list))

    def test_execute_aws_tags_queries(self):
        """Test that tag data is for the correct time queries."""
        test_cases = [
            {"value": "-1", "unit": "month", "resolution": "monthly"},
            {"value": "-2", "unit": "month", "resolution": "monthly"},
            {"value": "-10", "unit": "day", "resolution": "daily"},
            {"value": "-30", "unit": "day", "resolution": "daily"},
        ]

        for case in test_cases:
            url = reverse("aws-tags")
            client = APIClient()
            params = {
                "filter[resolution]": case.get("resolution"),
                "filter[time_scope_value]": case.get("value"),
                "filter[time_scope_units]": case.get("unit"),
                "key_only": False,
            }
            url = url + "?" + urlencode(params, quote_via=quote_plus)
            response = client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()
            start_range, end_range = self._calculate_expected_range(case.get("value"), case.get("unit"))

            self.assertNotEqual(data.get("data"), [])
            self.assertTrue(isinstance(data.get("data"), list))

    def test_execute_query_with_and_filter(self):
        """Test the filter[and:] param in the view."""
        url = reverse("aws-tags")
        client = APIClient()

        params = {
            "filter[resolution]": "daily",
            "filter[time_scope_value]": "-10",
            "filter[time_scope_units]": "day",
            "filter[and:account]": ["account1", "account2"],
        }
        url = url + "?" + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response_data = response.json()
        self.assertEqual(response_data.get("data", []), [])
