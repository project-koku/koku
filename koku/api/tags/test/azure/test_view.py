#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Azure tag view."""
from urllib.parse import quote_plus
from urllib.parse import urlencode

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.utils import DateHelper
from reporting.models import AzureCostEntryLineItemDailySummary


class AzureTagsViewTest(IamTestCase):
    """Tests the report view."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.dh = DateHelper()
        self.ten_days_ago = self.dh.n_days_ago(self.dh.today, 9)

    def test_execute_tags_queries_keys_only(self):
        """Test that tag key data is for the correct time queries."""
        test_cases = [
            {"value": "-1", "unit": "month", "resolution": "monthly"},
            {"value": "-2", "unit": "month", "resolution": "monthly"},
            {"value": "-10", "unit": "day", "resolution": "daily"},
            {"value": "-30", "unit": "day", "resolution": "daily"},
        ]

        for case in test_cases:
            url = reverse("azure-tags")
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
            data = response.json().get("data")

            self.assertTrue(data)
            self.assertTrue(isinstance(data, list))
            for tag in data:
                self.assertTrue(isinstance(tag, str))

    def test_execute_tags_queries(self):
        """Test that tag data is for the correct time queries."""
        test_cases = [
            {"value": "-1", "unit": "month", "resolution": "monthly"},
            {"value": "-2", "unit": "month", "resolution": "monthly"},
            {"value": "-10", "unit": "day", "resolution": "daily"},
            {"value": "-30", "unit": "day", "resolution": "daily"},
        ]

        for case in test_cases:
            url = reverse("azure-tags")
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
            data = response.json().get("data")

            self.assertTrue(data)
            self.assertTrue(isinstance(data, list))
            for tag in data:
                self.assertTrue(isinstance(tag, dict))
                self.assertIn("key", tag)
                self.assertIn("values", tag)
                self.assertIsNotNone(tag.get("key"))
                self.assertIn(tag.get("values").__class__, [list, str])
                self.assertTrue(tag.get("values"))

    def test_execute_tags_type_queries(self):
        """Test that tag data is for the correct type queries."""
        with tenant_context(self.tenant):
            guid = AzureCostEntryLineItemDailySummary.objects.values("subscription_guid")[0].get("subscription_guid")
        test_cases = [
            {"value": "-1", "unit": "month", "resolution": "monthly", "subscription_guid": guid},
            {"value": "-2", "unit": "month", "resolution": "monthly", "subscription_guid": guid},
            {"value": "-10", "unit": "day", "resolution": "daily", "subscription_guid": guid},
            {"value": "-30", "unit": "day", "resolution": "daily", "subscription_guid": guid},
        ]

        for case in test_cases:
            url = reverse("azure-tags")
            client = APIClient()
            params = {
                "filter[resolution]": case.get("resolution"),
                "filter[time_scope_value]": case.get("value"),
                "filter[time_scope_units]": case.get("unit"),
                "key_only": False,
                "filter[subscription_guid]": case.get("subscription_guid"),
            }
            url = url + "?" + urlencode(params, quote_via=quote_plus)
            response = client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json().get("data")
            self.assertTrue(data)
            self.assertTrue(isinstance(data, list))
            for tag in data:
                self.assertTrue(isinstance(tag, dict))
                self.assertIn("key", tag)
                self.assertIn("values", tag)
                self.assertIsNotNone(tag.get("key"))
                self.assertIn(tag.get("values").__class__, [list, str])
                self.assertTrue(tag.get("values"))

    def test_execute_query_with_and_filter(self):
        """Test the filter[and:] param in the view."""
        url = reverse("azure-tags")
        client = APIClient()

        with tenant_context(self.tenant):
            subs = (
                AzureCostEntryLineItemDailySummary.objects.filter(usage_start__gte=self.ten_days_ago)
                .values("subscription_guid")
                .distinct()
            )
            subscription_guids = [sub.get("subscription_guid") for sub in subs]
        params = {
            "filter[resolution]": "daily",
            "filter[time_scope_value]": "-10",
            "filter[time_scope_units]": "day",
            "filter[and:subscription_guid]": subscription_guids,
        }
        url = url + "?" + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json().get("data")
        self.assertEqual(data, [])
