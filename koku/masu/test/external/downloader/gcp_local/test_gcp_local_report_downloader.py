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
from datetime import date
from unittest.mock import patch
from api.utils import DateHelper

from faker import Faker

from api.models import Provider
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
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

    def test_download_file(self):
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

    # TODO: Figure out the mock to make this empty
    # def test_empty_manifest(self):
    #     """Test an empty report is returned if no manifest."""
    #     report = self.gcp_local_report_downloader.get_manifest_context_for_date(self.start_date)
    #     self.assertEqual(report, {})

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
