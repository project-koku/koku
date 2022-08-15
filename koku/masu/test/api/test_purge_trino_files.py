#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the purge_trino_files endpoint view."""
from unittest.mock import patch

# from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from urllib.parse import urlencode

from masu.config import Config
from masu.processor.orchestrator import Orchestrator
from masu.test import MasuTestCase


@override_settings(ROOT_URLCONF="masu.urls")
class PurgeTrinoFilesTest(MasuTestCase):
    """Test Cases for the purge_trino_files endpoint."""

    @patch("koku.middleware.MASU", return_value=True)
    def test_require_parameters(self, _):
        """Test the purge_trino_files endpoint with no parameters."""
        url = reverse("purge_trino_files")
        response_types = ["GET", "DELETE"]
        for response_type in response_types:
            with self.subTest(response_type):
                if response_type == "GET":
                    response = self.client.get(url)
                else:
                    response = self.client.delete(url)
                body = response.json()
                errmsg = body.get("Error")
                expected_errmsg = "Parameter missing. Required: provider_uuid, schema, bill date"
                self.assertEqual(response.status_code, 400)
                self.assertEqual(errmsg, expected_errmsg)

    @patch("koku.middleware.MASU", return_value=True)
    def test_provider_uuid_does_not_exist(self, _):
        """Test the purge_trino_files endpoint with no parameters."""
        fake_uuid = "12345"
        params = {"provider_uuid": fake_uuid}
        query_string = urlencode(params)
        url = reverse("purge_trino_files") + "?" + query_string
        response_types = ["GET", "DELETE"]
        for response_type in response_types:
            with self.subTest(response_type):
                if response_type == "GET":
                    response = self.client.get(url)
                else:
                    response = self.client.delete(url)
                body = response.json()
                errmsg = body.get("Error")
                expected_errmsg = f"The provider_uuid {fake_uuid} does not exist."
                self.assertEqual(response.status_code, 400)
                self.assertEqual(errmsg, expected_errmsg)

    @patch("koku.middleware.MASU", return_value=True)
    def test_require_schema(self, _):
        """Test the purge_trino_files endpoint with no parameters."""
        params = {"provider_uuid": self.aws_provider_uuid, "bill_date": "08-01-2022"}
        query_string = urlencode(params)
        url = reverse("purge_trino_files") + "?" + query_string
        response_types = ["GET", "DELETE"]
        for response_type in response_types:
            with self.subTest(response_type):
                if response_type == "GET":
                    response = self.client.get(url)
                else:
                    response = self.client.delete(url)
                body = response.json()
                errmsg = body.get("Error")
                expected_errmsg = "Parameter missing. Required: schema"
                self.assertEqual(response.status_code, 400)
                self.assertEqual(errmsg, expected_errmsg)

    @patch("koku.middleware.MASU", return_value=True)
    def test_require_bill_date(self, _):
        """Test the purge_trino_files endpoint with no parameters."""
        params = {"provider_uuid": self.aws_provider_uuid, "schema": "org1234567"}
        query_string = urlencode(params)
        url = reverse("purge_trino_files") + "?" + query_string
        response_types = ["GET", "DELETE"]
        for response_type in response_types:
            with self.subTest(response_type):
                if response_type == "GET":
                    response = self.client.get(url)
                else:
                    response = self.client.delete(url)
                body = response.json()
                errmsg = body.get("Error")
                expected_errmsg = "Parameter missing. Required: bill_date"
                self.assertEqual(response.status_code, 400)
                self.assertEqual(errmsg, expected_errmsg)

    @patch("koku.middleware.MASU", return_value=True)
    def test_successful_get_request(self, _):
        """Test the purge_trino_files endpoint with no parameters."""
        params = {
            "provider_uuid": self.aws_provider_uuid,
            "schema": "org1234567",
            "bill_date": "08-01-2022",
        }
        query_string = urlencode(params)
        url = reverse("purge_trino_files") + "?" + query_string
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    @patch("koku.middleware.MASU", return_value=True)
    def test_successful_get_request(self, _):
        """Test the purge_trino_files endpoint with no parameters."""
        params = {
            "provider_uuid": self.aws_provider_uuid,
            "schema": "org1234567",
            "bill_date": "08-01-2022",
        }
        query_string = urlencode(params)
        url = reverse("purge_trino_files") + "?" + query_string
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    @patch("koku.middleware.MASU", return_value=True)
    def test_successful_get_request(self, _):
        """Test the purge_trino_files endpoint with no parameters."""
        params = {
            "provider_uuid": self.aws_provider_uuid,
            "schema": "org1234567",
            "bill_date": "08-01-2022",
        }
        query_string = urlencode(params)
        url = reverse("purge_trino_files") + "?" + query_string
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    @patch("koku.middleware.MASU", return_value=True)
    def test_unleash_delete_request(self, _):
        """Test the purge_trino_files endpoint with no parameters."""
        params = {
            "provider_uuid": self.aws_provider_uuid,
            "schema": "org1234",
            "bill_date": "08-01-2022",
        }
        query_string = urlencode(params)
        url = reverse("purge_trino_files") + "?" + query_string
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 200)



