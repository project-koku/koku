#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the trino_query endpoint view."""
from unittest.mock import patch

from django.test.utils import override_settings
from django.urls import reverse

from masu.test import MasuTestCase


@override_settings(ROOT_URLCONF="masu.urls")
class TrinoQueryTest(MasuTestCase):
    """Test Cases for the trino_query endpoint."""

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.trino.trino")
    def test_trino_query(self, mock_trino, _):
        """Test the GET trino/query endpoint."""
        data = {"query": "SELECT 1", "schema": "org1234567"}

        response = self.client.post(reverse("trino_query"), data=data)
        self.assertEqual(response.status_code, 200)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.trino.trino")
    def test_trino_query_no_query(self, mock_trino, _):
        """Test the GET trino/query endpoint with no query."""
        data = {"schema": "org1234567"}

        expected = {"Error": "Must provide a query key to run."}
        response = self.client.post(reverse("trino_query"), data=data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), expected)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.trino.trino")
    def test_trino_query_no_schema(self, mock_trino, _):
        """Test the GET trino/query endpoint with no schema."""
        data = {"query": "select 1"}

        expected = {"Error": "Must provide a schema key to run."}
        response = self.client.post(reverse("trino_query"), data=data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), expected)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.trino.trino")
    def test_trino_query_dissallowed_query(self, mock_trino, _):
        """Test the GET trino/query endpoint with bad queries."""
        dissallowed_keywords = ["delete", "insert", "update", "alter", "create", "drop", "grant"]
        for keyword in dissallowed_keywords:
            data = {"query": f"{keyword}", "schema": "org1234567"}
            expected = {"Error": f"This endpoint does not allow a {keyword} operation to be performed."}
            response = self.client.post(reverse("trino_query"), data=data)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json(), expected)
