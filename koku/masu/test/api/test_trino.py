#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the trino_query endpoint view."""
from unittest.mock import MagicMock
from unittest.mock import patch
from urllib.parse import urlencode

from django.test.utils import override_settings
from django.urls import reverse

from masu.test import MasuTestCase


@override_settings(ROOT_URLCONF="masu.urls")
class TrinoQueryTest(MasuTestCase):
    """Test Cases for the trino_query endpoint."""

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.trino.get_report_db_accessor")
    def test_trino_query_no_query(self, mock_trino, _):
        """Test the GET trino/query endpoint with no query."""
        data = {"schema": "org1234567"}

        expected = {"Error": "Must provide a query key to run."}
        response = self.client.post(reverse("trino_query"), data=data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), expected)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.trino.get_report_db_accessor")
    def test_trino_query_no_schema(self, mock_trino, _):
        """Test the GET trino/query endpoint with no schema."""
        data = {"query": "select 1"}

        expected = {"Error": "Must provide a schema key to run."}
        response = self.client.post(reverse("trino_query"), data=data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), expected)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.trino.get_report_db_accessor")
    def test_trino_query_dissallowed_query(self, mock_trino, _):
        """Test the GET trino/query endpoint with bad queries."""
        dissallowed_keywords = ["delete", "insert", "update", "alter", "create", "drop", "grant"]
        for keyword in dissallowed_keywords:
            data = {"query": f"{keyword}", "schema": "org1234567"}
            expected = {"Error": f"This endpoint does not allow a {keyword} operation to be performed."}
            response = self.client.post(reverse("trino_query"), data=data)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json(), expected)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.trino.get_report_db_accessor")
    def test_trino_query_allowed_queries(self, *args):
        """Test the GET trino/query endpoint with allowed queries."""
        test_queries = [
            "SELECT * FROM openshift_pod_usage_line_items",
            "SELECT DISTINCT json_extract_scalar(json_parse(persistentvolumeclaim_labels), '$.kubevirt_io_created_by')",
            "SELECT json_extract_scalar(json_parse(random_labels), '$.delete')",
            "WITH cte AS (SELECT * FROM gcp_line_items) SELECT * FROM cte",
            "SHOW TABLES",
            "DESCRIBE openshift_storage_usage_line_items",
            "SELECT 1",
        ]

        for query in test_queries:
            with self.subTest(params=query):
                data = {"query": query, "schema": "org1234567"}
                response = self.client.post(reverse("trino_query"), data=data)
                self.assertEqual(response.status_code, 200)


@override_settings(ROOT_URLCONF="masu.urls")
class TrinoUITest(MasuTestCase):
    """Test Cases for the trino_ui endpoint."""

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.trino.requests")
    def test_trino_ui_with_api_service(self, mock_requests, _):
        """Test the GET trino_ui endpoint."""
        valid_api_services = ["query", "stats", "cluster"]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_requests.get.return_value = mock_response
        for service in valid_api_services:
            params = {"api_service": service}
            url = f"{reverse('trino_ui')}?{urlencode(params)}"
            response = self.client.get(url)
            self.assertEqual(response.status_code, mock_response.status_code)
            self.assertIsInstance(response.data, dict)
            self.assertEqual(response.data.get("api_service_name"), service)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.trino.requests")
    def test_trino_ui_invalid_or_no_api_service(self, mock_requests, _):
        """Test the GET trino_ui endpoint with no api service parameter."""
        invalid_api_services = ["invalid", "", "random", "test"]
        expected = {"Error": "Must provide a valid parameter and trino-ui api service."}
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {}
        mock_requests.get.return_value = mock_response
        for service in invalid_api_services:
            params = {"api_service": service}
            url = f"{reverse('trino_ui')}?{urlencode(params)}"
            response = self.client.get(url)
            self.assertEqual(response.status_code, mock_response.status_code)
            self.assertEqual(response.json(), expected)
