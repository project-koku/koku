#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the purge_trino_files endpoint view."""
from unittest.mock import ANY
from unittest.mock import patch
from urllib.parse import urlencode
from uuid import uuid4

from celery.result import AsyncResult
from django.test.utils import override_settings
from django.urls import reverse

from masu.api.purge_trino_files import OCP_REPORT_TYPES
from masu.test import MasuTestCase


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
        fake_uuid = uuid4()
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
    def test_ocp_get_request_date_range_builds_day_specific_csv_prefixes(self, _):
        """Test OCP date-range purge builds day-specific and manifest-based CSV prefixes."""
        params = {
            "provider_uuid": self.ocp_provider_uuid,
            "schema": self.schema,
            "bill_date": self.bill_date,
            "start_date": self.bill_date,
            "end_date": "2022-08-02",
        }
        query_string = urlencode(params)
        url = reverse("purge_trino_files") + "?" + query_string
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        csv_paths = body.get("s3_csv_path", [])

        day_specific = [p for p in csv_paths if any(f"/{rt}." in p for rt in OCP_REPORT_TYPES)]
        self.assertEqual(len(day_specific), len(OCP_REPORT_TYPES) * 2)
        for report_type in OCP_REPORT_TYPES:
            self.assertIn(f"/{report_type}.2022-08-01", " ".join(day_specific))
            self.assertIn(f"/{report_type}.2022-08-02", " ".join(day_specific))

    @patch("koku.middleware.MASU", return_value=True)
    def test_purge_path_generation_by_provider_and_date_range(self, _):
        """Test purge path generation for OCP validation, cross-month partitioning, and non-OCP independence."""
        test_cases = [
            {
                "label": "OCP without dates returns 400",
                "params": {
                    "provider_uuid": self.ocp_provider_uuid,
                    "schema": self.schema,
                    "bill_date": self.bill_date,
                },
                "expected_status": 400,
                "check": lambda body: self.assertIn("OCP purge requires start_date and end_date", body["Error"]),
            },
            {
                "label": "OCP cross-month uses correct partition per date",
                "params": {
                    "provider_uuid": self.ocp_provider_uuid,
                    "schema": self.schema,
                    "bill_date": self.bill_date,
                    "start_date": "2022-08-31",
                    "end_date": "2022-09-01",
                },
                "expected_status": 200,
                "check": lambda body: (
                    self.assertTrue(
                        any("2022-08-31" in p for p in body["s3_csv_path"]),
                        "Expected Aug 31 day-specific paths",
                    ),
                    self.assertTrue(
                        any("2022-09-01" in p for p in body["s3_csv_path"]),
                        "Expected Sep 01 day-specific paths",
                    ),
                    self.assertTrue(
                        any("month=08" in p for p in body["s3_csv_path"]),
                        "Expected month=08 partition",
                    ),
                    self.assertTrue(
                        any("month=09" in p for p in body["s3_csv_path"]),
                        "Expected month=09 partition",
                    ),
                ),
            },
            {
                "label": "Non-OCP date range produces independent path per date",
                "params": {
                    "provider_uuid": self.aws_provider_uuid,
                    "schema": self.schema,
                    "bill_date": self.bill_date,
                    "start_date": self.bill_date,
                    "end_date": "2022-08-03",
                },
                "expected_status": 200,
                "check": lambda body: (
                    self.assertEqual(len(body["s3_csv_path"]), 3),
                    self.assertTrue(body["s3_csv_path"][0].endswith("/2022-08-01")),
                    self.assertTrue(body["s3_csv_path"][1].endswith("/2022-08-02")),
                    self.assertTrue(body["s3_csv_path"][2].endswith("/2022-08-03")),
                ),
            },
        ]
        for case in test_cases:
            with self.subTest(case["label"]):
                url = reverse("purge_trino_files") + "?" + urlencode(case["params"])
                response = self.client.get(url)
                self.assertEqual(response.status_code, case["expected_status"])
                case["check"](response.json())

    @patch("koku.middleware.MASU", return_value=True)
    @patch(
        "masu.api.purge_trino_files.purge_manifest_records.delay",
        return_value=AsyncResult("dc350f15-ffc7-4fcb-92d7-2a9f1275568e"),
    )
    @patch(
        "masu.api.purge_trino_files.purge_s3_files",
        return_value=AsyncResult("dc350f15-ffc7-4fcb-92d7-2a9f1275568e"),
    )
    def test_unleash_get_request(self, mock_purge, mock_manifest, _):
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
        mock_manifest.assert_not_called()

    @patch("koku.middleware.MASU", return_value=True)
    @patch(
        "masu.api.purge_trino_files.purge_manifest_records.delay",
        return_value=AsyncResult("dc350f15-ffc7-4fcb-92d7-2a9f1275568e"),
    )
    @patch(
        "masu.api.purge_trino_files.purge_s3_files.delay",
        return_value=AsyncResult("dc350f15-ffc7-4fcb-92d7-2a9f1275568e"),
    )
    def test_unleash_delete_request(self, mock_purge, mock_manifest, _):
        """Test the purge_trino_files endpoint with no parameters."""
        params = {
            "provider_uuid": self.aws_provider_uuid,
            "schema": self.schema,
            "bill_date": self.bill_date,
        }
        query_string = urlencode(params)
        url = reverse("purge_trino_files") + "?" + query_string
        response = self.client.delete(url)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        mock_purge.assert_called_with(
            provider_uuid=self.aws_provider_uuid, provider_type="AWS-local", schema_name=self.schema, prefix=ANY
        )
        mock_manifest.assert_called()
        self.assertIn("dc350f15-ffc7-4fcb-92d7-2a9f1275568e", body.keys())

    @patch("koku.middleware.MASU", return_value=True)
    @patch(
        "masu.api.purge_trino_files.purge_manifest_records.delay",
        return_value=AsyncResult("dc350f15-ffc7-4fcb-92d7-2a9f1275568e"),
    )
    @patch(
        "masu.api.purge_trino_files.purge_s3_files.delay",
        return_value=AsyncResult("dc350f15-ffc7-4fcb-92d7-2a9f1275568e"),
    )
    def test_unleash_delete_request_with_date_range(self, mock_purge, mock_manifest, _):
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
        response = self.client.delete(url)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        mock_purge.assert_called_with(
            provider_uuid=self.gcp_provider_uuid, provider_type="GCP-local", schema_name=self.schema, prefix=ANY
        )
        mock_manifest.assert_called()
        self.assertIn("dc350f15-ffc7-4fcb-92d7-2a9f1275568e", body.keys())

    @patch("koku.middleware.MASU", return_value=True)
    @patch(
        "masu.api.purge_trino_files.purge_manifest_records.delay",
        return_value=AsyncResult("dc350f15-ffc7-4fcb-92d7-2a9f1275568e"),
    )
    @patch(
        "masu.api.purge_trino_files.purge_s3_files.delay",
        return_value=AsyncResult("dc350f15-ffc7-4fcb-92d7-2a9f1275568e"),
    )
    def test_unleash_delete_request_with_ignore_manifest(self, mock_purge, mock_manfiest, _):
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
        response = self.client.delete(url)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        mock_purge.assert_called_with(
            provider_uuid=self.gcp_provider_uuid, provider_type="GCP-local", schema_name=self.schema, prefix=ANY
        )
        mock_manfiest.assert_not_called()
        self.assertIn("dc350f15-ffc7-4fcb-92d7-2a9f1275568e", body.keys())
