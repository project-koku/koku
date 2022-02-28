#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test GCP Report Views."""
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
from api.report.gcp.view import GCPCostView

FAKE = Faker()


class GCPReportViewTest(IamTestCase):
    """GCP report view test cases."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()

        self.report = {
            "group_by": {"account": ["*"]},
            "filter": {"time_scope_value": "-10", "time_scope_units": "day", "resolution": "daily"},
            "data": [
                {
                    "date": "2020-12-06",
                    "accounts": [
                        {
                            "account": "018984-D0AAA4-940B88",
                            "values": [
                                {
                                    "date": "2020-12-06",
                                    "account": "018984-D0AAA4-940B88",
                                    "source_uuid": ["c545d7bd-2814-4f80-a8da-4b56d2146d5b"],
                                    "infrastructure": {
                                        "raw": {"value": 10.222222222, "units": "USD"},
                                        "markup": {"value": 0.0, "units": "USD"},
                                        "usage": {"value": 0.0, "units": "USD"},
                                        "total": {"value": 10.222222222, "units": "USD"},
                                    },
                                    "supplementary": {
                                        "raw": {"value": 0.0, "units": "USD"},
                                        "markup": {"value": 0.0, "units": "USD"},
                                        "usage": {"value": 0.0, "units": "USD"},
                                        "total": {"value": 0.0, "units": "USD"},
                                    },
                                    "cost": {
                                        "raw": {"value": 10.222222222, "units": "USD"},
                                        "markup": {"value": 0.0, "units": "USD"},
                                        "usage": {"value": 0.0, "units": "USD"},
                                        "total": {"value": 10.222222222, "units": "USD"},
                                    },
                                }
                            ],
                        }
                    ],
                }
            ],
        }

    @patch("api.report.gcp.query_handler.GCPReportQueryHandler")
    def test_costview_with_units_success(self, mock_handler):
        """Test unit conversion succeeds in GCPCostView."""
        mock_handler.return_value.execute_query.return_value = self.report
        params = {
            "group_by[account]": "*",
            "filter[resolution]": "monthly",
            "filter[time_scope_value]": "-1",
            "filter[time_scope_units]": "month",
            "SERVER_NAME": "",
        }
        user = User.objects.get(username=self.user_data["username"])

        django_request = HttpRequest()
        qd = QueryDict(mutable=True)
        qd.update(params)
        django_request.GET = qd
        request = Request(django_request)
        request.user = user

        response = GCPCostView().get(request)
        self.assertIsInstance(response, Response)

    def test_execute_query_w_delta_total(self):
        """Test that delta=total returns deltas."""
        qs = "delta=cost"
        url = reverse("reports-gcp-costs") + "?" + qs
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_execute_query_w_delta_bad_choice(self):
        """Test invalid delta value."""
        bad_delta = "Invalid"
        expected = f'"{bad_delta}" is not a valid choice.'
        qs = f"group_by[subscription_guid]=*&filter[limit]=2&delta={bad_delta}"
        url = reverse("reports-gcp-costs") + "?" + qs
        client = APIClient()
        response = client.get(url, **self.headers)
        result = str(response.data.get("delta")[0])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(result, expected)
