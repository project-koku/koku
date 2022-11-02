#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCIReportDownloader class."""
import logging
import os
import shutil
import tempfile
from unittest.mock import MagicMock
from unittest.mock import patch
from uuid import uuid4

from faker import Faker
from rest_framework.exceptions import ValidationError

from api.utils import DateHelper
from masu.external import UNCOMPRESSED
from masu.external.downloader.oci.oci_report_downloader import create_monthly_archives
from masu.external.downloader.oci.oci_report_downloader import DATA_DIR
from masu.external.downloader.oci.oci_report_downloader import OCIReportDownloader
from masu.external.downloader.oci.oci_report_downloader import OCIReportDownloaderError
from masu.test import MasuTestCase

LOG = logging.getLogger(__name__)

FAKE = Faker()


class OCIReportDownloaderTest(MasuTestCase):
    """Test Cases for the OCIReportDownloader object."""

    def setUp(self):
        """Setup vars for test."""
        super().setUp()
        self.today = DateHelper().today

    def tearDown(self):
        """Remove files and directories created during the test run."""
        super().tearDown()
        shutil.rmtree(DATA_DIR, ignore_errors=True)

    def create_oci_downloader_with_mocked_values(
        self,
        customer_name=FAKE.name(),
        bucket=FAKE.slug(),
        provider_uuid=uuid4(),
        namespace=FAKE.slug(),
        region=FAKE.slug(),
        report="reports_cost-csv_0001000000603504.csv",
    ):
        """
        Create a OCIReportDownloader that skips the initial OCI checks.

        This also results in Mock objects being set to instance variables that can be patched
        inside other test functions.

        Args:
            customer_name (str): optional customer name; will be randomly generated if None
            bucket (str): optional bucket name; will be randomly generated if None
            provider_uuid (uuid): optional provider UUID; will be randomly generated if None

        Returns:
            OCIReportDownloader instance with faked argument data and Mocks.
        """
        report_file = MagicMock()
        report_file.get_objects = report
        billing_source = {"bucket": bucket, "bucket_namespace": namespace, "bucket_region": region}
        with patch("masu.external.downloader.oci.oci_report_downloader.OCIProvider"), patch(
            "masu.external.downloader.oci.oci_report_downloader.OCIReportDownloader._get_oci_client",
            return_value=report_file,
        ):
            downloader = OCIReportDownloader(
                customer_name=customer_name,
                data_source=billing_source,
                provider_uuid=provider_uuid,
            )

        return downloader

    def test_prepare_monthly_files(self):
        """
        Test _prepare_monthly_files returns a pseudo dictionary of monthly files.
        """

        provider_uuid = uuid4()
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        downloader = self.create_oci_downloader_with_mocked_values(provider_uuid=provider_uuid)
        result_monthly_files_dict = downloader._prepare_monthly_files(start_date, end_date)
        expected_monthly_files_dict = {start_date.date(): []}
        self.assertEqual(result_monthly_files_dict, expected_monthly_files_dict)

    def test_prepare_monthly_files_initial_ingest(self):
        """
        Test _prepare_monthly_files returns a pseudo dictionary of monthly files
        """

        provider_uuid = uuid4()
        dh = DateHelper()
        previous_month = dh.previous_month(dh.last_month_start)
        last_month = dh.last_month_start
        this_month = dh.this_month_start
        downloader = self.create_oci_downloader_with_mocked_values(provider_uuid=provider_uuid)
        result_monthly_files_dict = downloader._prepare_monthly_files(previous_month, this_month)
        expected_monthly_files_dict = {
            previous_month.date(): [],
            last_month.date(): [],
            this_month.date(): [],
        }
        self.assertEqual(result_monthly_files_dict, expected_monthly_files_dict)

    @patch("masu.external.downloader.oci.oci_report_downloader.OCIReportDownloader._collect_reports")
    def test_extract_names(self, mock_collect_reports):
        """Test _extract_names returns filenames for files created in a month."""

        provider_uuid = uuid4()
        dh = DateHelper()
        start_date = dh.this_month_start
        filenames = [
            "test_cost_this_month.csv",
            "test_usage_this_month.csv",
            "test_cost_last_month.csv",
            "test_usage_last_month.csv",
        ]
        cost_report = MagicMock()
        cost_report.name = filenames[0]
        cost_report.time_created = dh._now
        usage_report = MagicMock()
        usage_report.name = filenames[1]
        usage_report.time_created = dh._now
        cost_reports = MagicMock()
        cost_reports.data.objects = [cost_report]
        usage_reports = MagicMock()
        usage_reports.data.objects = [usage_report]
        mock_collect_reports.side_effect = [cost_reports, usage_reports]
        invoice_month = start_date.strftime("%Y%m")
        assembly_id = ":".join([str(provider_uuid), str(invoice_month)])
        downloader = self.create_oci_downloader_with_mocked_values(provider_uuid=provider_uuid)
        result_file_names = downloader._extract_names(assembly_id, start_date)
        mock_collect_reports.assert_called()
        expected_filenames = filenames[:2]
        self.assertEqual(result_file_names, expected_filenames)
        self.assertNotEqual(result_file_names, filenames)

    def test_generate_monthly_pseudo_manifest(self):
        """Assert _generate_monthly_pseudo_manifest returns a manifest-like dict."""
        provider_uuid = uuid4()
        dh = DateHelper()
        start_date = dh.this_month_start
        downloader = self.create_oci_downloader_with_mocked_values(provider_uuid=provider_uuid)
        result_manifest = downloader._generate_monthly_pseudo_manifest(start_date)
        expected_manifest_data = {
            "assembly_id": "",
            "compression": UNCOMPRESSED,
            "start_date": start_date,
            "file_names": [],
        }
        self.assertEqual(result_manifest, expected_manifest_data)

    @patch("masu.external.downloader.oci.oci_report_downloader.OCIReportDownloader._collect_reports")
    def test_generate_monthly_pseudo_no_manifest(self, mock_collect_reports):
        """Test get monthly psuedo manifest with no manifest."""
        dh = DateHelper()
        mock_collect_reports.side_effect = []
        downloader = self.create_oci_downloader_with_mocked_values(provider_uuid=uuid4())
        start_date = dh.last_month_start
        manifest_dict = downloader._generate_monthly_pseudo_manifest(start_date)
        self.assertIsNotNone(manifest_dict)

    @patch("masu.external.downloader.oci.oci_report_downloader.OCIReportDownloader._prepare_monthly_files")
    def test_get_manifest_context_for_date(self, mock_prepare_monthly_files):
        """Test successful return of get manifest context for date."""
        dh = DateHelper()
        start_date = dh.this_month_start
        p_uuid = uuid4()
        expected_assembly_id = f"{p_uuid}:{str(start_date.strftime('%Y%m'))}"
        mock_prepare_monthly_files.return_value = {start_date: []}
        downloader = self.create_oci_downloader_with_mocked_values(provider_uuid=p_uuid)
        with patch(
            "masu.external.downloader.oci.oci_report_downloader.OCIReportDownloader._process_manifest_db_record",
            return_value=2,
        ):
            report_manifests_list = downloader.get_manifest_context_for_date(start_date.date())
            manifest = report_manifests_list[0]
            self.assertEqual(manifest.get("compression", ""), UNCOMPRESSED)
            self.assertEqual(manifest.get("manifest_id", ""), 2)
            self.assertEqual(expected_assembly_id, manifest.get("assembly_id", ""))

    def test_get_local_file_for_report(self):
        """Assert that get_local_file_for_report is a simple pass-through."""
        downloader = self.create_oci_downloader_with_mocked_values()
        report_name = FAKE.file_path()
        expected_report_name = report_name.replace("/", "_")
        local_name = downloader.get_local_file_for_report(report_name)
        self.assertEqual(local_name, expected_report_name)

    def test_get_last_reports(self):
        """Assert collecting dict of last reports downloaded."""
        downloader = self.create_oci_downloader_with_mocked_values()
        expected_reports = {"usage": "", "cost": ""}
        result_reports = downloader.get_last_reports("assembly")
        self.assertEqual(expected_reports, result_reports)

    @patch("masu.external.downloader.oci.oci_report_downloader.OCIReportDownloader.update_last_reports")
    def test_update_last_reports(self, mock_update_last_reports):
        """Assert updating dict of last reports downloaded."""
        key = "test-report"
        manifest_id = "1"
        downloader = self.create_oci_downloader_with_mocked_values()
        expected_reports = {"usage": "new_report", "cost": "new_cost_report"}
        mock_update_last_reports.return_value = expected_reports
        result_reports = downloader.update_last_reports(key, manifest_id)
        self.assertEqual(expected_reports, result_reports)

    @patch("masu.external.downloader.oci.oci_report_downloader.OCIProvider")
    @patch("masu.external.downloader.oci.oci_report_downloader.OCIReportDownloader._get_oci_client")
    def test_download_with_unreachable_source(self, mock_get_oci_client, oci_provider):
        """Assert errors correctly when source is unreachable."""
        mock_get_oci_client.return_value = "client"
        oci_provider.return_value.cost_usage_source_is_reachable.side_effect = ValidationError
        billing_source = {"bucket": FAKE.slug(), "bucket_namespace": FAKE.slug(), "bucket_region": FAKE.slug()}
        with self.assertRaises(OCIReportDownloaderError):
            OCIReportDownloader(FAKE.name(), billing_source)

    @patch("masu.external.downloader.oci.oci_report_downloader.os.makedirs")
    def test_download_file_success(self, mock_makedirs):
        """Assert download_file successful scenario"""
        key = "reports_cost-csv_0001000000603504.csv"
        dh = DateHelper()
        start_date = dh.today
        mock_name = "mock-test-customer-success"
        expected_full_path = f"{DATA_DIR}/{mock_name}/oci/{key}"
        downloader = self.create_oci_downloader_with_mocked_values(customer_name=mock_name, report=key)
        with patch("masu.external.downloader.oci.oci_report_downloader.open"):
            with patch("masu.external.downloader.oci.oci_report_downloader.os.path.getmtime"):
                with patch(
                    "masu.external.downloader.oci.oci_report_downloader.create_monthly_archives",
                    return_value=[[key], {"start_date": start_date, "end_date": start_date}],
                ):
                    full_path, etag, date, _, __ = downloader.download_file(key)
                    mock_makedirs.assert_called()
                    self.assertEqual(full_path, expected_full_path)

    @patch("masu.external.downloader.oci.oci_report_downloader.open")
    def test_download_file_error(self, mock_open):
        """Test download error is handled correctly in download file method."""
        key = "reports_cost-csv_0001000000603504.csv"
        err_msg = "Unknown Error"
        downloader = self.create_oci_downloader_with_mocked_values()
        with patch("masu.external.downloader.oci.oci_report_downloader.object_storage"):
            with patch("masu.external.downloader.oci.oci_report_downloader.os.path.getmtime"):
                with patch("masu.external.downloader.oci.oci_report_downloader.create_monthly_archives"):
                    with self.assertRaises(Exception) as exp:
                        downloader.download_file(key)
                        self.assertEqual(exp.message, err_msg)

    @patch("masu.external.downloader.oci.oci_report_downloader.copy_local_report_file_to_s3_bucket")
    def test_create_monthly_archives(self, mock_s3):
        """Test that we load daily files to S3."""
        # Use the processor example for data:
        file_path = "./koku/masu/test/data/oci/reports_cost-csv_0001000000603747.csv"
        file_name = "reports_cost-csv_0001000000603747.csv"
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, file_name)
        shutil.copy2(file_path, temp_path)
        uuid = uuid4()

        with patch("masu.external.downloader.oci.oci_report_downloader.uuid.uuid4", return_value=uuid):
            expected_daily_files = [
                f"{temp_dir}/cost_{uuid}.2022-04.csv",
            ]

            daily_file_names, date_range = create_monthly_archives(
                "request_id", "account", self.oci_provider_uuid, file_name, temp_path, None
            )

            mock_s3.assert_called()
            self.assertEqual(sorted(daily_file_names), sorted(expected_daily_files))

            for daily_file in expected_daily_files:
                self.assertTrue(os.path.exists(daily_file))
                os.remove(daily_file)

            os.remove(temp_path)

    @patch(
        "masu.external.downloader.oci.oci_report_downloader.object_storage.ObjectStorageClient",
        return_value=MagicMock(),
    )
    def test_get_oci_client(self, _):
        """Test to verify OCI downloader is initialized."""
        downloader = self.create_oci_downloader_with_mocked_values()
        client = downloader._get_oci_client("region")
        self.assertIsNotNone(client)
