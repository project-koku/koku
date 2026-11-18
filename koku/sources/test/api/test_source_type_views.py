#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the SourceTypesView."""
from django.test.utils import override_settings
from rest_framework.test import APIRequestFactory

from api.iam.test.iam_test_case import IamTestCase
from sources.api.source_type_mapping import CMMO_ID_TO_SOURCE_NAME
from sources.api.source_type_views import SourceTypesView


@override_settings(ONPREM=True)
class SourceTypesViewTest(IamTestCase):
    """Test Cases for the source_types endpoint (on-prem OpenShift-only catalog)."""

    def setUp(self):
        """Set up tests."""
        super().setUp()
        self.factory = APIRequestFactory()

    def _get(self, query_params=None):
        """Invoke SourceTypesView.get with optional query params."""
        request = self.factory.get("/source_types", data=query_params or {})
        return SourceTypesView.as_view()(request)

    def test_list_source_types(self):
        """Test GET returns OpenShift only on-prem (cloud CMMO types are hidden)."""
        response = self._get()

        self.assertEqual(response.status_code, 200)
        body = response.data
        self.assertEqual(body["meta"]["count"], 1)
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["name"], "openshift")
        self.assertEqual(body["data"][0]["id"], "1")
        # Mapping still documents cloud types for SaaS/CMMO, but on-prem list is OCP-only
        self.assertGreater(len(CMMO_ID_TO_SOURCE_NAME), 1)

    def test_filter_by_name_match(self):
        """Test GET with filter[name] that matches."""
        response = self._get({"filter[name]": "openshift"})

        self.assertEqual(response.status_code, 200)
        body = response.data
        self.assertEqual(body["meta"]["count"], 1)
        self.assertEqual(body["data"][0]["name"], "openshift")
        self.assertEqual(body["data"][0]["id"], "1")

    def test_filter_by_name_no_match(self):
        """Test GET with filter[name] that does not match."""
        response = self._get({"filter[name]": "nonexistent"})

        self.assertEqual(response.status_code, 200)
        body = response.data
        self.assertEqual(body["meta"]["count"], 0)
        self.assertEqual(len(body["data"]), 0)

    def test_filter_by_name_amazon(self):
        """Test GET with filter[name]=amazon returns empty on-prem (cloud types hidden)."""
        response = self._get({"filter[name]": "amazon"})

        self.assertEqual(response.status_code, 200)
        body = response.data
        self.assertEqual(body["meta"]["count"], 0)
        self.assertEqual(len(body["data"]), 0)

    def test_no_auth_required(self):
        """Test that the endpoint does not require authentication."""
        # SourceTypesView has AllowAny permissions
        response = self._get()
        self.assertEqual(response.status_code, 200)


@override_settings(ONPREM=False)
class SourceTypesViewSaasCatalogTest(IamTestCase):
    """When ONPREM is false, SourceTypesView still lists all CMMO types if invoked."""

    def test_list_includes_cloud_types_when_not_onprem(self):
        """SaaS catalog includes amazon/azure/google (view unused on SaaS URLs, but unfiltered)."""
        factory = APIRequestFactory()
        request = factory.get("/source_types")
        response = SourceTypesView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        body = response.data
        self.assertEqual(body["meta"]["count"], len(CMMO_ID_TO_SOURCE_NAME))
        returned_names = {st["name"] for st in body["data"]}
        self.assertEqual(returned_names, set(CMMO_ID_TO_SOURCE_NAME.values()))
