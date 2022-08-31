#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the purge_trino_files endpoint view."""
from unittest.mock import ANY
from unittest.mock import patch
from urllib.parse import urlencode

from celery.result import AsyncResult
from django.test.utils import override_settings
from django.urls import reverse

from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.test import MasuTestCase


class FakeManifest:
    def get_manifest_list_for_provider_and_bill_date(self, provider_uuid, bill_date):
        manifest_dict = {
            "assembly_id": "1234",
            "billing_period_start_datetime": "2020-02-01",
            "num_total_files": 2,
            "provider_uuid": provider_uuid,
        }
        manifest_accessor = ReportManifestDBAccessor()
        manifest = manifest_accessor.add(**manifest_dict)
        return [manifest]

    def get_manifest_list_for_provider_and_date_range(self, provider_uuid, start_date, end_date):
        manifest_dict = {
            "assembly_id": "1234",
            "billing_period_start_datetime": "2020-02-01",
            "num_total_files": 2,
            "provider_uuid": provider_uuid,
        }
        manifest_accessor = ReportManifestDBAccessor()
        manifest = manifest_accessor.add(**manifest_dict)
        return [manifest]

    def bulk_delete_manifests(self, provider_uuid, manifest_id_list):
        return True


@override_settings(ROOT_URLCONF="masu.urls")
class PurgeTrinoFilesTest(MasuTestCase):
    """Test Cases for the purge_trino_files endpoint."""

    def setUp(self):
        """Create test case setup."""
        super().setUp()
        self.schema = "org1234"
        self.bill_date = "2022-08-01"

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
            "schema": self.schema,
            "bill_date": self.bill_date,
        }
        query_string = urlencode(params)
        url = reverse("purge_trino_files") + "?" + query_string
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    @patch("koku.middleware.MASU", return_value=True)
    @patch(
        "masu.api.purge_trino_files.purge_s3_files",
        return_value=AsyncResult("dc350f15-ffc7-4fcb-92d7-2a9f1275568e"),
    )
    def test_unleash_get_request(self, mock_purge, _):
        """Test the purge_trino_files endpoint with no parameters."""
        params = {
            "provider_uuid": self.aws_provider_uuid,
            "schema": self.schema,
            "bill_date": self.bill_date,
        }
        query_string = urlencode(params)
        url = reverse("purge_trino_files") + "?" + query_string
        response = self.client.get(url)
        # body = response.json()
        self.assertEqual(response.status_code, 200)
        mock_purge.assert_not_called()

    @patch("koku.middleware.MASU", return_value=True)
    @patch(
        "masu.api.purge_trino_files.purge_s3_files.delay",
        return_value=AsyncResult("dc350f15-ffc7-4fcb-92d7-2a9f1275568e"),
    )
    def test_unleash_delete_request(self, mock_purge, _):
        """Test the purge_trino_files endpoint with no parameters."""
        params = {
            "provider_uuid": self.aws_provider_uuid,
            "schema": self.schema,
            "bill_date": self.bill_date,
        }
        query_string = urlencode(params)
        url = reverse("purge_trino_files") + "?" + query_string
        with patch("masu.api.purge_trino_files.ReportManifestDBAccessor") as mock_accessor:
            mock_accessor.return_value.__enter__.return_value = FakeManifest()
            response = self.client.delete(url)
            body = response.json()
            self.assertEqual(response.status_code, 200)
            mock_purge.assert_called_with(
                provider_uuid=self.aws_provider_uuid, provider_type="AWS-local", schema_name=self.schema, prefix=ANY
            )
            for key in body.keys():
                self.assertEqual(key, "dc350f15-ffc7-4fcb-92d7-2a9f1275568e")

    @patch("koku.middleware.MASU", return_value=True)
    @patch(
        "masu.api.purge_trino_files.purge_s3_files.delay",
        return_value=AsyncResult("dc350f15-ffc7-4fcb-92d7-2a9f1275568e"),
    )
    def test_unleash_delete_request_with_date_range(self, mock_purge, _):
        """Test the purge_trino_files endpoint with no parameters."""
        params = {
            "provider_uuid": self.gcp_provider_uuid,
            "schema": self.schema,
            "bill_date": self.bill_date,
            "start_date": self.bill_date,
            "end_date": "2022-08-03",
        }
        query_string = urlencode(params)
        url = reverse("purge_trino_files") + "?" + query_string
        with patch("masu.api.purge_trino_files.ReportManifestDBAccessor") as mock_accessor:
            mock_accessor.return_value.__enter__.return_value = FakeManifest()
            response = self.client.delete(url)
            body = response.json()
            self.assertEqual(response.status_code, 200)
            mock_purge.assert_called_with(
                provider_uuid=self.gcp_provider_uuid, provider_type="GCP-local", schema_name=self.schema, prefix=ANY
            )
            for key in body.keys():
                self.assertEqual(key, "dc350f15-ffc7-4fcb-92d7-2a9f1275568e")

    @patch("koku.middleware.MASU", return_value=True)
    @patch(
        "masu.api.purge_trino_files.purge_s3_files.delay",
        return_value=AsyncResult("dc350f15-ffc7-4fcb-92d7-2a9f1275568e"),
    )
    def test_unleash_delete_request_with_ignore_manifest(self, mock_purge, _):
        """Test the purge_trino_files endpoint with no parameters."""
        params = {
            "provider_uuid": self.gcp_provider_uuid,
            "schema": self.schema,
            "bill_date": self.bill_date,
            "start_date": self.bill_date,
            "ignore_manifest": "True",
        }
        query_string = urlencode(params)
        url = reverse("purge_trino_files") + "?" + query_string
        with patch("masu.api.purge_trino_files.ReportManifestDBAccessor") as mock_accessor:
            mock_accessor.return_value.__enter__.return_value = FakeManifest()
            response = self.client.delete(url)
            body = response.json()
            self.assertEqual(response.status_code, 200)
            mock_purge.assert_called_with(
                provider_uuid=self.gcp_provider_uuid, provider_type="GCP-local", schema_name=self.schema, prefix=ANY
            )
            for key in body.keys():
                self.assertEqual(key, "dc350f15-ffc7-4fcb-92d7-2a9f1275568e")
