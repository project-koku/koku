#
# Copyright 2020 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Test the Organization views."""
from django.test import RequestFactory
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_csv.renderers import CSVRenderer

from api.common.pagination import ReportPagination
from api.common.pagination import ReportRankedPagination
from api.iam.test.iam_test_case import IamTestCase
from api.report.view import get_paginator


class ReportViewTest(IamTestCase):
    """Tests the organizations view."""

    ENDPOINTS = ["aws-org-unit"]

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.client = APIClient()
        self.factory = RequestFactory()

    def test_endpoint_view(self):
        """Test endpoint runs with a customer owner."""
        for endpoint in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                json_result = response.json()
                self.assertIsNotNone(json_result.get("data"))
                self.assertIsInstance(json_result.get("data"), list)
                self.assertTrue(len(json_result.get("data")) > 0)

    def test_endpoints_invalid_query_param(self):
        """Test endpoint runs with an invalid query param."""
        for endpoint in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                query = "group_by[invalid]=*"
                url = reverse(endpoint) + "?" + query
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_endpoint_csv(self):
        """Test CSV output of inventory endpoint reports."""
        self.client = APIClient(HTTP_ACCEPT="text/csv")
        for endpoint in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, content_type="text/csv", **self.headers)
                response.render()

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.accepted_media_type, "text/csv")
                self.assertIsInstance(response.accepted_renderer, CSVRenderer)

    def test_get_paginator_default(self):
        """Test that the standard report paginator is returned."""
        params = {}
        paginator = get_paginator(params, 0)
        self.assertIsInstance(paginator, ReportPagination)

    def test_get_paginator_for_filter_offset(self):
        """Test that the standard report paginator is returned."""
        params = {"offset": 5}
        paginator = get_paginator(params, 0)
        self.assertIsInstance(paginator, ReportRankedPagination)
