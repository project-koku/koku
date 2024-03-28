#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Local Report Downloader."""
import logging
import os
import shutil
import tempfile
from datetime import datetime
from unittest.mock import patch

from faker import Faker

from api.models import Provider
from api.utils import DateHelper
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.downloader.gcp_local.gcp_local_report_downloader import create_daily_archives
from masu.external.downloader.gcp_local.gcp_local_report_downloader import GCPLocalReportDownloader
from masu.external.report_downloader import ReportDownloader
from masu.test import MasuTestCase

DATA_DIR = Config.TMP_DIR
FAKE = Faker()
CUSTOMER_NAME = FAKE.word()
REPORT = FAKE.word()
PREFIX = FAKE.word()
REGION = "us-central1"


class GCPLocalReportDownloaderTest(MasuTestCase):
    """Test Cases for the Local Report Downloader."""

    fake = Faker()

    @classmethod
    def setUpClass(cls):
        """Set up class variables."""
        super().setUpClass()
        cls.fake_customer_name = CUSTOMER_NAME
        cls.fake_report_name = "koku-local"

        cls.fake_bucket_prefix = PREFIX
        cls.selected_region = REGION

        cls.manifest_accessor = ReportManifestDBAccessor()

    def setUp(self):
        """Set up each test."""
        super().setUp()
        self.start_date = datetime(year=2020, month=11, day=8).date()
        self.end_date = datetime(year=2020, month=11, day=11).date()
        self.etag = "30c31bca571d9b7f3b2c8459dd8bc34a"
        self.invoice = "202011"
        test_report = f"./koku/masu/test/data/gcp/{self.invoice}_{self.etag}_2020-11-08:2020-11-11.csv"
        self.local_storage = tempfile.mkdtemp()
        local_dir = f"{self.local_storage}/{self.etag}"
        os.makedirs(local_dir)
        self.csv_file_name = test_report.split("/")[-1]
        self.csv_file_path = f"{local_dir}/{self.csv_file_name}"
        shutil.copy2(test_report, self.csv_file_path)

        self.credentials = {"project_id": "test-project"}
        self.data_source = {"table_id": "test-id", "dataset": "test-database", "local_dir": local_dir}

        self.report_downloader = ReportDownloader(
            customer_name=self.fake_customer_name,
            credentials=self.credentials,
            data_source=self.data_source,
            provider_type=Provider.PROVIDER_GCP_LOCAL,
            provider_uuid=self.gcp_provider_uuid,
        )

        self.gcp_local_report_downloader = GCPLocalReportDownloader(
            **{
                "customer_name": self.fake_customer_name,
                "credentials": self.credentials,
                "data_source": self.data_source,
                "provider_uuid": self.gcp_provider_uuid,
            }
        )

    def tearDown(self):
        """Remove test generated data."""
        shutil.rmtree(self.local_storage)

    def test_initializer(self):
        """Test the GCP-Local initializer."""
        self.assertIsNotNone(self.report_downloader)

    @patch("masu.util.aws.common.remove_files_not_in_set_from_s3_bucket")
    @patch("masu.util.aws.common.copy_data_to_s3_bucket")
    def test_download_file(self, *args):
        """Test GCP-Local report download."""

        full_file_path, etag, _, __, ___ = self.gcp_local_report_downloader.download_file(self.csv_file_name)
        self.assertEqual(full_file_path, self.csv_file_path)
        self.assertIsNotNone(etag)
        self.assertEqual(etag, self.etag)

        # Download a second time, verify etag is returned
        full_file_path, second_run_etag, _, __, ___ = self.gcp_local_report_downloader.download_file(
            self.csv_file_name
        )
        self.assertEqual(etag, second_run_etag)
        self.assertEqual(full_file_path, self.csv_file_path)

    def test_get_manifest_for_date(self):
        """Test GCP-local get manifest."""
        expected_assembly_id = f"{self.start_date}|{self.end_date}"
        result_report_list = self.gcp_local_report_downloader.get_manifest_context_for_date(self.start_date)
        for result_report in result_report_list:
            self.assertIn(expected_assembly_id, result_report.get("assembly_id"))
            result_files = result_report.get("files")
            self.assertTrue(result_files)
            for file_info in result_files:
                self.assertEqual(file_info.get("key"), self.csv_file_name)
                self.assertEqual(file_info.get("local_file"), self.csv_file_name)

    def test_empty_manifest(self):
        """Test an empty report is returned if no manifest."""
        with patch(
            "masu.external.downloader.gcp_local.gcp_local_report_downloader.GCPLocalReportDownloader"
            + ".collect_new_manifests",
            return_value=[],
        ):
            report = self.gcp_local_report_downloader.get_manifest_context_for_date(self.start_date)
            self.assertEqual(report, [])

    def test_delete_manifest_file_warning(self):
        """Test attempting a file that doesn't exist handles correctly."""
        with self.assertLogs(
            logger="masu.external.downloader.gcp_local.gcp_local_report_downloader", level="INFO"
        ) as captured_logs:
            # Disable log suppression
            logging.disable(logging.NOTSET)
            self.gcp_local_report_downloader._remove_manifest_file("None")
            self.assertTrue(
                captured_logs.output[0].startswith("INFO:"),
                msg="The log is expected to start with 'INFO:' but instead was: " + captured_logs.output[0],
            )
            self.assertTrue(
                "Could not delete manifest file at" in captured_logs.output[0],
                msg="""The log message is expected to contain
                                    'Could not delete manifest file at' but instead was: """
                + captured_logs.output[0],
            )
            # Re-enable log suppression
            logging.disable(logging.CRITICAL)

    def test_extract_names(self):
        """Test extract names creates mapping."""
        result_mapping = self.gcp_local_report_downloader._extract_names()
        file_data = result_mapping.get(self.invoice, {}).get(self.etag)
        self.assertIsNotNone(file_data)

    def test_remove_manifest_file(self):
        """Test remove manifest file."""
        self.assertTrue(os.path.exists(self.csv_file_path))
        self.gcp_local_report_downloader._remove_manifest_file(self.csv_file_path)
        self.assertFalse(os.path.exists(self.csv_file_path))

    def test_collect_new_manifest(self):
        """Test collecting new manifests when there is new data in BigQuery"""
        expected_bill_date = datetime.combine(self.start_date.replace(day=1), datetime.min.time())
        expected_assembly_id = f"{self.start_date}|{self.end_date}|{self.gcp_provider_uuid}"

        new_manifests = self.gcp_local_report_downloader.collect_new_manifests()

        for manifest_metadata in new_manifests:
            self.assertEqual(manifest_metadata["bill_date"], expected_bill_date)
            self.assertEqual(manifest_metadata["assembly_id"], expected_assembly_id)
            self.assertEqual(manifest_metadata["files"], [self.csv_file_name])

    @patch("masu.external.downloader.gcp_local.gcp_local_report_downloader.copy_local_report_file_to_s3_bucket")
    def test_create_daily_archives(self, mock_s3):
        """Test that we load daily files to S3."""
        # Use the processor example for data:
        file_path = "./koku/masu/test/data/gcp/202011_30c31bca571d9b7f3b2c8459dd8bc34a_2020-11-08:2020-11-11.csv"
        file_name = "202011_30c31bca571d9b7f3b2c8459dd8bc34a_2020-11-08:2020-11-11.csv"
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, file_name)
        shutil.copy2(file_path, temp_path)

        expected_daily_files = [
            f"{temp_dir}/202011_2020-11-08 00:00:00+00:00.csv",
            f"{temp_dir}/202011_2020-11-09 00:00:00+00:00.csv",
            f"{temp_dir}/202011_2020-11-10 00:00:00+00:00.csv",
            f"{temp_dir}/202011_2020-11-11 00:00:00+00:00.csv",
        ]

        start_date = DateHelper().this_month_start
        daily_file_names, date_range = create_daily_archives(
            "request_id", "account", self.gcp_provider_uuid, file_name, temp_path, None, start_date, None
        )
        expected_date_range = {"start": "2020-11-08", "end": "2020-11-11"}
        self.assertEqual(date_range, expected_date_range)
        self.assertIsInstance(daily_file_names, list)

        mock_s3.assert_called()
        self.assertEqual(sorted(daily_file_names), sorted(expected_daily_files))

        for daily_file in expected_daily_files:
            self.assertTrue(os.path.exists(daily_file))
            os.remove(daily_file)

        os.remove(temp_path)
