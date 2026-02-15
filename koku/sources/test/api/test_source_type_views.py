#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the SourceTypesView."""
from django.test.utils import override_settings
from django.urls import reverse

from api.iam.test.iam_test_case import IamTestCase
from sources.api.source_type_mapping import CMMO_ID_TO_SOURCE_NAME


@override_settings(ROOT_URLCONF="koku.urls")
class SourceTypesViewTest(IamTestCase):
    """Test Cases for the source_types endpoint."""

    def setUp(self):
        """Set up tests."""
        super().setUp()
        customer = self._create_customer_data()
        user_data = self._create_user_data()
        self.request_context = self._create_request_context(customer, user_data, create_customer=True, is_admin=True)

    def test_list_source_types(self):
        """Test GET returns the list of source types."""
        url = reverse("source-types")
        response = self.client.get(url, **self.request_context["request"].META)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["meta"]["count"], len(CMMO_ID_TO_SOURCE_NAME))
        self.assertEqual(len(body["data"]), len(CMMO_ID_TO_SOURCE_NAME))

        # Verify all source types are present
        returned_names = {st["name"] for st in body["data"]}
        expected_names = set(CMMO_ID_TO_SOURCE_NAME.values())
        self.assertEqual(returned_names, expected_names)

    def test_filter_by_name_match(self):
        """Test GET with filter[name] that matches."""
        url = reverse("source-types")
        response = self.client.get(
            url,
            {"filter[name]": "openshift"},
            **self.request_context["request"].META,
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["meta"]["count"], 1)
        self.assertEqual(body["data"][0]["name"], "openshift")
        self.assertEqual(body["data"][0]["id"], "1")

    def test_filter_by_name_no_match(self):
        """Test GET with filter[name] that does not match."""
        url = reverse("source-types")
        response = self.client.get(
            url,
            {"filter[name]": "nonexistent"},
            **self.request_context["request"].META,
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["meta"]["count"], 0)
        self.assertEqual(len(body["data"]), 0)

    def test_filter_by_name_amazon(self):
        """Test GET with filter[name]=amazon."""
        url = reverse("source-types")
        response = self.client.get(
            url,
            {"filter[name]": "amazon"},
            **self.request_context["request"].META,
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["meta"]["count"], 1)
        self.assertEqual(body["data"][0]["name"], "amazon")
        self.assertEqual(body["data"][0]["id"], "2")

    def test_no_auth_required(self):
        """Test that the endpoint does not require authentication."""
        url = reverse("source-types")
        # SourceTypesView has AllowAny permissions and is in no_auth_list
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
