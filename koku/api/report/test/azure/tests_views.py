#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Azure Report views."""
from unittest.mock import patch

from django.http import HttpRequest
from django.http import QueryDict
from django.urls import reverse
from faker import Faker
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.models import User
from api.report.azure.view import AzureCostView
from api.report.view import _convert_units
from api.utils import UnitConverter

FAKE = Faker()


class AzureReportViewTest(IamTestCase):
    """Azure report view test cases."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()

        self.report = {
            "group_by": {"subscription_guid": ["*"]},
            "filter": {
                "resolution": "monthly",
                "time_scope_value": -1,
                "time_scope_units": "month",
                "resource_scope": [],
            },
            "data": [
                {
                    "date": "2018-07",
                    "subscription_guids": [
                        {
                            "subscription_guid": "00000000-0000-0000-0000-000000000000",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "subscription_guid": "00000000-0000-0000-0000-000000000000",
                                    "total": 1826.74238146924,
                                }
                            ],
                        },
                        {
                            "subscription_guid": "11111111-1111-1111-1111-111111111111",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "subscription_guid": "11111111-1111-1111-1111-111111111111",
                                    "total": 1137.74036198065,
                                }
                            ],
                        },
                        {
                            "subscription_guid": "22222222-2222-2222-2222-222222222222",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "subscription_guid": "22222222-2222-2222-2222-222222222222",
                                    "total": 1045.80659412797,
                                }
                            ],
                        },
                        {
                            "subscription_guid": "33333333-3333-3333-3333-333333333333",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "subscription_guid": "33333333-3333-3333-3333-333333333333",
                                    "total": 807.326470618818,
                                }
                            ],
                        },
                        {
                            "subscription_guid": "44444444-4444-4444-4444-444444444444",
                            "values": [
                                {
                                    "date": "2018-07",
                                    "units": "GB-Mo",
                                    "subscription_guid": "44444444-4444-4444-4444-444444444444",
                                    "total": 658.306642830709,
                                }
                            ],
                        },
                    ],
                }
            ],
            "total": {"value": 5475.922451027388, "units": "GB-Mo"},
        }

    def test_convert_units_success(self):
        """Test unit conversion succeeds."""
        converter = UnitConverter()
        to_unit = "byte"
        expected_unit = f"{to_unit}-Mo"
        report_total = self.report.get("total", {}).get("value")

        result = _convert_units(converter, self.report, to_unit)
        result_unit = result.get("total", {}).get("units")
        result_total = result.get("total", {}).get("value")

        self.assertEqual(expected_unit, result_unit)
        self.assertEqual(report_total * 1e9, result_total)

    def test_convert_units_list(self):
        """Test that the list check is hit."""
        converter = UnitConverter()
        to_unit = "byte"
        expected_unit = f"{to_unit}-Mo"
        report_total = self.report.get("total", {}).get("value")

        report = [self.report]
        result = _convert_units(converter, report, to_unit)
        result_unit = result[0].get("total", {}).get("units")
        result_total = result[0].get("total", {}).get("value")

        self.assertEqual(expected_unit, result_unit)
        self.assertEqual(report_total * 1e9, result_total)

    def test_convert_units_total_not_dict(self):
        """Test that the total not dict block is hit."""
        converter = UnitConverter()
        to_unit = "byte"
        expected_unit = f"{to_unit}-Mo"

        report = self.report["data"][0]["subscription_guids"][0]["values"][0]
        report_total = report.get("total")
        result = _convert_units(converter, report, to_unit)
        result_unit = result.get("units")
        result_total = result.get("total")

        self.assertEqual(expected_unit, result_unit)
        self.assertEqual(report_total * 1e9, result_total)

    @patch("api.report.azure.query_handler.AzureReportQueryHandler")
    def test_costview_with_units_success(self, mock_handler):
        """Test unit conversion succeeds in AzureCostView."""
        mock_handler.return_value.execute_query.return_value = self.report
        params = {
            "group_by[subscription_guid]": "*",
            "filter[resolution]": "monthly",
            "filter[time_scope_value]": "-1",
            "filter[time_scope_units]": "month",
            "units": "byte",
            "SERVER_NAME": "",
        }
        user = User.objects.get(username=self.user_data["username"])

        django_request = HttpRequest()
        qd = QueryDict(mutable=True)
        qd.update(params)
        django_request.GET = qd
        request = Request(django_request)
        request.user = user

        response = AzureCostView().get(request)
        self.assertIsInstance(response, Response)

    def test_execute_query_w_delta_total(self):
        """Test that delta=total returns deltas."""
        qs = "delta=cost"
        url = reverse("reports-azure-costs") + "?" + qs
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_execute_query_w_delta_bad_choice(self):
        """Test invalid delta value."""
        bad_delta = "Invalid"
        expected = f'"{bad_delta}" is not a valid choice.'
        qs = f"group_by[subscription_guid]=*&filter[limit]=2&delta={bad_delta}"
        url = reverse("reports-azure-costs") + "?" + qs
        client = APIClient()
        response = client.get(url, **self.headers)
        result = str(response.data.get("delta")[0])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(result, expected)
