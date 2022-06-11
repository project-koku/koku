#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Local Report Downloader."""
import logging
import os
import shutil
import tempfile
from unittest.mock import patch

from faker import Faker

from api.models import Provider
from api.utils import DateHelper
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.downloader.oci_local.oci_local_report_downloader import OCILocalReportDownloader
from masu.external.report_downloader import ReportDownloader
from masu.test import MasuTestCase

DATA_DIR = Config.TMP_DIR
FAKE = Faker()
CUSTOMER_NAME = FAKE.word()
REPORT = FAKE.word()
REGION = "uk-london-1"


class OCILocalReportDownloaderTest(MasuTestCase):
    """Test Cases for the Local Report Downloader."""

    fake = Faker()

    @classmethod
    def setUpClass(cls):
        """Set up class variables."""
        super().setUpClass()
        cls.fake_customer_name = CUSTOMER_NAME
        cls.fake_report_name = "koku-local"
        cls.selected_region = REGION
        cls.manifest_accessor = ReportManifestDBAccessor()

    def setUp(self):
        """Set up each test."""
        super().setUp()
        dh = DateHelper()
        self.start_date = dh.today
        self.etag = "reports_cost-csv_0001000000603747.csv"
        test_report = "./koku/masu/test/data/oci/reports_cost-csv_0001000000603747.csv"
        self.local_storage = tempfile.mkdtemp()
        local_dir = f"{self.local_storage}"
        self.csv_file_name = test_report.split("/")[-1]
        self.csv_file_path = f"{local_dir}/{self.csv_file_name}"
        self.testing_dir = f"{DATA_DIR}/{CUSTOMER_NAME}/oci-local{self.local_storage}/{self.etag}"
        shutil.copy2(test_report, self.csv_file_path)

        self.credentials = {"tenant": "test-tenant"}
        self.data_source = {"bucket": local_dir, "bucket_namespace": "test-namespace", "region": "my-region"}

        self.report_downloader = ReportDownloader(
            customer_name=self.fake_customer_name,
            credentials=self.credentials,
            data_source=self.data_source,
            provider_type=Provider.PROVIDER_OCI_LOCAL,
            provider_uuid=self.oci_provider_uuid,
        )

        self.oci_local_report_downloader = OCILocalReportDownloader(
            **{
                "customer_name": self.fake_customer_name,
                "credentials": self.credentials,
                "data_source": self.data_source,
                "provider_uuid": self.oci_provider_uuid,
            }
        )

    def tearDown(self):
        """Remove test generated data."""
        shutil.rmtree(self.local_storage)

    def test_initializer(self):
        """Test the OCI-Local initializer."""
        self.assertIsNotNone(self.report_downloader)

    def test_download_file(self):
        """Test OCI-Local report download."""

        full_file_path, etag, _, __, ___ = self.oci_local_report_downloader.download_file(self.csv_file_name)
        self.assertEqual(full_file_path, self.testing_dir)
        self.assertIsNotNone(etag)
        self.assertEqual(etag, self.etag)

        # Download a second time, verify etag is returned
        full_file_path, second_run_etag, _, __, ___ = self.oci_local_report_downloader.download_file(
            self.csv_file_name
        )
        self.assertEqual(etag, second_run_etag)
        self.assertEqual(full_file_path, self.testing_dir)

    def test_download_file_error(self):
        """Test OCI-Local report download."""
        key = "reports_cost-csv_0001000000603504.csv"
        err_msg = "Unknown Error"
        with patch(
            "masu.external.downloader.oci_local.oci_local_report_downloader.OCILocalReportDownloader.download_file"
        ) as downloader:
            with patch("masu.external.downloader.oci_local.oci_local_report_downloader.os.path.isfile"):
                with self.assertRaises(Exception) as exp:
                    downloader.download_file(key)
                    self.assertEqual(exp.message, err_msg)

    def test_get_manifest_for_date(self):
        """Test OCI-local get manifest."""
        expected_assembly_id = ":".join([str(self.oci_provider_uuid), str(self.start_date)])
        result_report_dict = self.oci_local_report_downloader.get_manifest_context_for_date(self.start_date)
        self.assertEqual(result_report_dict.get("assembly_id"), expected_assembly_id)
        result_files = result_report_dict.get("files")
        self.assertTrue(result_files)
        for file in result_files:
            self.assertEqual(file["key"], self.csv_file_name)

    def test_empty_manifest(self):
        """Test an empty report is returned if no manifest."""
        # patch_sting is used to prevent reordered making the E501 useless
        patch_string = "masu.external.downloader.oci_local.oci_local_report_downloader.OCILocalReportDownloader._generate_monthly_pseudo_manifest"  # noqa: E501
        with patch(patch_string) as patch_manifest:
            patch_manifest.side_effect = [None]
            report = self.oci_local_report_downloader.get_manifest_context_for_date(self.start_date)
            self.assertEqual(report, {})

    def test_delete_manifest_file_warning(self):
        """Test attempting a file that doesn't exist handles correctly."""
        with self.assertLogs(
            logger="masu.external.downloader.oci_local.oci_local_report_downloader", level="INFO"
        ) as captured_logs:
            # Disable log suppression
            logging.disable(logging.NOTSET)
            self.oci_local_report_downloader._remove_manifest_file("None")
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
        filenames = self.oci_local_report_downloader._extract_names()
        self.assertIsNotNone(filenames)

    def test_generate_monthly_pseudo_manifest(self):
        """Test generating the monthly manifest."""
        expected_assembly_id = ":".join([str(self.oci_provider_uuid), str(self.start_date)])
        result_manifest_data = self.oci_local_report_downloader._generate_monthly_pseudo_manifest(self.start_date)
        self.assertTrue(result_manifest_data)
        self.assertEqual(result_manifest_data.get("assembly_id"), expected_assembly_id)

    def test_remove_manifest_file(self):
        """Test remove manifest file."""
        self.assertTrue(os.path.exists(self.csv_file_path))
        self.oci_local_report_downloader._remove_manifest_file(self.csv_file_path)
        self.assertFalse(os.path.exists(self.csv_file_path))
