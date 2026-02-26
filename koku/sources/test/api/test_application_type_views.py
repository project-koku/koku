#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ApplicationTypesView."""
import unittest

from django.conf import settings
from django.test.utils import override_settings
from django.urls import reverse

from api.iam.test.iam_test_case import IamTestCase
from sources.api.source_type_mapping import COST_MGMT_APP_TYPE_ID


@unittest.skipUnless(settings.ONPREM, "ONPREM-only: application_types endpoint requires ONPREM=True")
@override_settings(ROOT_URLCONF="koku.urls")
class ApplicationTypesViewTest(IamTestCase):
    """Test Cases for the application_types endpoint."""

    def setUp(self):
        """Set up tests."""
        super().setUp()
        customer = self._create_customer_data()
        user_data = self._create_user_data()
        self.request_context = self._create_request_context(customer, user_data, create_customer=True, is_admin=True)

    def test_list_application_types(self):
        """Test GET returns the list of application types."""
        url = reverse("application-types")
        response = self.client.get(url, **self.request_context["request"].META)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["meta"]["count"], 1)
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["id"], COST_MGMT_APP_TYPE_ID)
        self.assertEqual(body["data"][0]["name"], "/insights/platform/cost-management")

    def test_filter_by_name_match(self):
        """Test GET with filter[name] that matches."""
        url = reverse("application-types")
        response = self.client.get(
            url,
            {"filter[name]": "/insights/platform/cost-management"},
            **self.request_context["request"].META,
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["meta"]["count"], 1)
        self.assertEqual(body["data"][0]["name"], "/insights/platform/cost-management")

    def test_filter_by_name_no_match(self):
        """Test GET with filter[name] that does not match."""
        url = reverse("application-types")
        response = self.client.get(
            url,
            {"filter[name]": "/insights/platform/nonexistent"},
            **self.request_context["request"].META,
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["meta"]["count"], 0)
        self.assertEqual(len(body["data"]), 0)

    def test_filter_by_name_eq_match(self):
        """Test GET with filter[name][eq] that matches."""
        url = reverse("application-types")
        response = self.client.get(
            url,
            {"filter[name][eq]": "/insights/platform/cost-management"},
            **self.request_context["request"].META,
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["meta"]["count"], 1)

    def test_filter_by_name_eq_no_match(self):
        """Test GET with filter[name][eq] that does not match."""
        url = reverse("application-types")
        response = self.client.get(
            url,
            {"filter[name][eq]": "nonexistent"},
            **self.request_context["request"].META,
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["meta"]["count"], 0)

    def test_no_auth_required(self):
        """Test that the endpoint does not require authentication."""
        url = reverse("application-types")
        # ApplicationTypesView has AllowAny permissions and is in no_auth_list
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
