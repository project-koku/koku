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
from masu.external import UNCOMPRESSED
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
        self.dh = DateHelper()
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

    @patch("masu.util.aws.common.remove_files_not_in_set_from_s3_bucket")
    @patch("masu.util.aws.common.copy_data_to_s3_bucket")
    def test_download_file(self, *args):
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
        """
        Test download_file raise error when no file in path provided
        """

        key = "test-report.csv"
        err_msg = f"Unable to locate {key}"
        with self.assertRaises(Exception) as exp:
            self.oci_local_report_downloader.download_file(key)
        expected_exception = exp.exception
        self.assertIn(err_msg, expected_exception.args[0])

    @patch("masu.external.downloader.oci_local.oci_local_report_downloader.OCILocalReportDownloader._extract_names")
    @patch(
        "masu.external.downloader.oci_local.oci_local_report_downloader.OCILocalReportDownloader._prepare_monthly_files"
    )
    def test_get_manifest_for_date(self, mock_prepare_monthly_files, mock_extract_names):
        """Test OCI-local get manifest."""
        start_date = self.dh.this_month_start
        file_month_year = start_date.strftime("%Y-%m")
        cost_report = f"report_cost-{file_month_year}.csv"
        usage_report = f"report_usage-{file_month_year}.csv"
        test_file_list = [cost_report, usage_report]
        expected_assembly_id = ":".join([str(self.oci_provider_uuid), str(file_month_year)])
        mock_prepare_monthly_files.return_value = {start_date: []}
        mock_extract_names.return_value = test_file_list
        report_manifests_list = self.oci_local_report_downloader.get_manifest_context_for_date(start_date)
        result_report_dict = report_manifests_list[0]
        self.assertEqual(result_report_dict.get("assembly_id", ""), expected_assembly_id)
        mock_prepare_monthly_files.assert_called_once()
        mock_extract_names.assert_called_once()
        expected_file_list = result_report_dict.get("files", [])
        self.assertIsInstance(expected_file_list, list)
        for file in expected_file_list:
            self.assertIn(file["key"], test_file_list)

    @patch("masu.external.downloader.oci_local.oci_local_report_downloader.OCILocalReportDownloader._extract_names")
    @patch(
        "masu.external.downloader.oci_local.oci_local_report_downloader.OCILocalReportDownloader._prepare_monthly_files"
    )
    def test_get_manifest_for_date_no_month_reports(self, mock_prepare_monthly_files, mock_extract_names):
        """Test OCI-local don't create manifest record if no monthly reports downloaded."""
        test_file_list = []
        mock_prepare_monthly_files.return_value = {self.dh.this_month_start: []}
        mock_extract_names.return_value = []
        report_manifests_list = self.oci_local_report_downloader.get_manifest_context_for_date(
            self.dh.last_month_start
        )
        mock_prepare_monthly_files.assert_called_once()
        mock_extract_names.assert_called_once()
        self.assertIsInstance(report_manifests_list, list)
        self.assertEqual(len(report_manifests_list), 0)
        self.assertEqual(len(report_manifests_list), len(test_file_list))

    def test_empty_manifest(self):
        """Test an empty report is returned if no manifest."""
        # patch_sting is used to prevent reordered making the E501 useless
        patch_string = "masu.external.downloader.oci_local.oci_local_report_downloader.OCILocalReportDownloader._generate_monthly_pseudo_manifest"  # noqa: E501
        with patch(patch_string) as patch_manifest:
            patch_manifest.side_effect = [None]
            report = self.oci_local_report_downloader.get_manifest_context_for_date(self.dh.this_month_start)
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
        """Test _extract_names returns month filenames."""

        start_date = self.dh.this_month_start
        date_str = start_date.strftime("%Y-%m")
        cost_report_name = f"report_cost-0001_{date_str}.csv"
        usage_report_name = f"report_cost-0001_{date_str}.csv"
        expected_filenames = [cost_report_name, usage_report_name]
        with patch("os.walk") as mockwalk:
            mockwalk.return_value = [
                ("", (), expected_filenames),
            ]
            filenames = self.oci_local_report_downloader._extract_names(start_date)
        self.assertEqual(filenames, expected_filenames)

    def test_extract_names_error(self):
        """
        Test that _extract_names raises error when bucket is not provided
        """
        err_msg = "The required bucket parameter was not provided in the data_source json."
        self.oci_local_report_downloader = OCILocalReportDownloader(
            **{
                "customer_name": self.fake_customer_name,
                "data_source": {},
            }
        )
        with self.assertRaises(Exception) as exp:
            self.oci_local_report_downloader._extract_names(self.dh.this_month_start)
        expected_exception = exp.exception
        self.assertIn(err_msg, expected_exception.args[0])

    def test_generate_monthly_pseudo_manifest(self):
        """Test generating the monthly manifest."""
        result_manifest_data = self.oci_local_report_downloader._generate_monthly_pseudo_manifest(
            self.dh.this_month_start
        )
        self.assertEqual(result_manifest_data.get("compression"), UNCOMPRESSED)
        self.assertEqual(result_manifest_data.get("assembly_id"), "")
        self.assertEqual(self.dh.this_month_start, result_manifest_data.get("start_date"))

    def test_remove_manifest_file(self):
        """Test remove manifest file."""
        self.assertTrue(os.path.exists(self.csv_file_path))
        self.oci_local_report_downloader._remove_manifest_file(self.csv_file_path)
        self.assertFalse(os.path.exists(self.csv_file_path))

    def test_prepare_monthly_files(self):
        """
        Test _prepare_monthly_files returns a pseudo dictionary of monthly files.
        """

        start_date = self.dh.this_month_start
        end_date = self.dh.this_month_end
        result_monthly_files_dict = self.oci_local_report_downloader._prepare_monthly_files(start_date, end_date)
        expected_monthly_files_dict = {start_date.date(): []}
        self.assertEqual(result_monthly_files_dict, expected_monthly_files_dict)
