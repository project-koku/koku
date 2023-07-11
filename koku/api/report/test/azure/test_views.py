#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Azure Report views."""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase


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
