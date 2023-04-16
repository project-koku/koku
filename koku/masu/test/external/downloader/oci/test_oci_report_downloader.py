#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCIReportDownloader class."""
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

FAKE = Faker()


class OCIReportDownloaderTest(MasuTestCase):
    """Test Cases for the OCIReportDownloader object."""

    def setUp(self):
        """Setup vars for test."""
        super().setUp()
        self.dh = DateHelper()
        self.provider_uuid = uuid4()
        self.test_cost_report_name = "reports_cost-csv_0001000000603747.csv"
        self.cost_file_path = f"./koku/masu/test/data/oci/{self.test_cost_report_name}"
        self.test_usage_report_name = "reports_usage-csv_0001000000829494.csv"
        self.usage_file_path = f"./koku/masu/test/data/oci/{self.test_usage_report_name}"

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

    def test_prepare_monthly_files_dict(self):
        """
        Test _prepare_monthly_files_dict returns a pseudo dictionary of monthly files.
        """

        start_date = self.dh.this_month_start
        end_date = self.dh.this_month_end
        downloader = self.create_oci_downloader_with_mocked_values(provider_uuid=self.provider_uuid)
        result_monthly_files_dict = downloader._prepare_monthly_files_dict(start_date, end_date)
        expected_monthly_files_dict = {start_date.date(): []}
        self.assertEqual(result_monthly_files_dict, expected_monthly_files_dict)

    def test_prepare_monthly_files_dict_initial_ingest(self):
        """
        Test _prepare_monthly_files_dict returns a pseudo dictionary of monthly files
        """

        previous_month = self.dh.previous_month(self.dh.last_month_start)
        last_month = self.dh.last_month_start
        this_month = self.dh.this_month_start
        downloader = self.create_oci_downloader_with_mocked_values(provider_uuid=self.provider_uuid)
        result_monthly_files_dict = downloader._prepare_monthly_files_dict(previous_month, this_month)
        expected_monthly_files_dict = {
            previous_month.date(): [],
            last_month.date(): [],
            this_month.date(): [],
        }
        self.assertEqual(result_monthly_files_dict, expected_monthly_files_dict)

    def test_collect_reports(self):
        """Test _collect_reports returns list of reports objects"""

        test_report = MagicMock()
        test_report.name = self.test_cost_report_name
        test_report.time_created = self.dh._now
        list_objects_res = MagicMock()
        list_objects_res.data.objects = [test_report]
        downloader = self.create_oci_downloader_with_mocked_values(provider_uuid=self.provider_uuid)
        downloader._oci_client = MagicMock()
        mock_list_objects = downloader._oci_client.list_objects
        mock_list_objects.return_value = list_objects_res

        returned_reports = downloader._collect_reports()

        mock_list_objects.assert_called()
        self.assertEqual(returned_reports, [test_report, test_report])

    def test_get_month_report_names(self):
        """Test _get_month_report_names returns list of month report names"""

        cost_test_report = MagicMock()
        cost_test_report.name = self.test_cost_report_name
        cost_test_report.time_created = self.dh.this_month_start
        usage_test_report = MagicMock()
        usage_test_report.name = self.test_usage_report_name
        usage_test_report.time_created = self.dh.last_month_start
        list_report_objects = [cost_test_report, usage_test_report]
        expected_report_names_list = [self.test_cost_report_name]

        downloader = self.create_oci_downloader_with_mocked_values(provider_uuid=self.provider_uuid)
        returned_report_names_list = downloader._get_month_report_names(self.dh.this_month_start, list_report_objects)

        self.assertEqual(returned_report_names_list, expected_report_names_list)

    def test_generate_monthly_pseudo_manifest(self):
        """Assert _generate_monthly_pseudo_manifest returns a manifest-like dict."""

        start_date = self.dh.this_month_start
        downloader = self.create_oci_downloader_with_mocked_values(provider_uuid=self.provider_uuid)
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
        mock_collect_reports.side_effect = []
        downloader = self.create_oci_downloader_with_mocked_values(provider_uuid=uuid4())
        start_date = self.dh.last_month_start
        manifest_dict = downloader._generate_monthly_pseudo_manifest(start_date)
        self.assertIsNotNone(manifest_dict)

    @patch("masu.external.downloader.oci.oci_report_downloader.OCIReportDownloader._get_month_report_names")
    @patch("masu.external.downloader.oci.oci_report_downloader.OCIReportDownloader._prepare_monthly_files_dict")
    def test_get_manifest_context_for_date(self, mock_prepare_monthly_files, mock_month_rpt_names):
        """Test successful return of get manifest context for date."""

        start_date = self.dh.this_month_start
        p_uuid = uuid4()
        file_month_year = self.start_date.strftime("%Y%m")
        cost_report = f"report_cost-{file_month_year}.csv"
        usage_report = f"report_usage-{file_month_year}.csv"
        test_file_list = [cost_report, usage_report]
        expected_assembly_id = f"{p_uuid}:{str(file_month_year)}"
        mock_prepare_monthly_files.return_value = {start_date: []}
        mock_month_rpt_names.return_value = test_file_list
        downloader = self.create_oci_downloader_with_mocked_values(provider_uuid=p_uuid)
        with patch(
            "masu.external.downloader.oci.oci_report_downloader.OCIReportDownloader._process_manifest_db_record",
            return_value=2,
        ):
            report_manifests_list = downloader.get_manifest_context_for_date(start_date.date())
            manifest = report_manifests_list[0]
            self.assertEqual(manifest.get("manifest_id", ""), 2)
            self.assertEqual(manifest.get("compression", ""), UNCOMPRESSED)
            self.assertEqual(
                manifest.get("assembly_id", ""),
                expected_assembly_id,
            )

    @patch("masu.external.downloader.oci.oci_report_downloader.OCIReportDownloader._prepare_monthly_files_dict")
    def test_get_manifest_context_for_date_no_month_reports(self, mock_prepare_monthly_files):
        """Test successful return of get manifest context for date."""

        start_date = self.dh.this_month_start
        p_uuid = uuid4()
        test_file_list = []
        mock_prepare_monthly_files.return_value = {start_date: []}
        downloader = self.create_oci_downloader_with_mocked_values(provider_uuid=p_uuid)
        with patch(
            "masu.external.downloader.oci.oci_report_downloader.OCIReportDownloader._process_manifest_db_record",
            return_value=2,
        ):
            report_manifests_list = downloader.get_manifest_context_for_date(start_date.date())
            self.assertIsInstance(report_manifests_list, list)
            self.assertEqual(len(report_manifests_list), 0)
            self.assertEqual(len(report_manifests_list), len(test_file_list))

    def test_get_local_file_for_report(self):
        """Assert that get_local_file_for_report is a simple pass-through."""
        downloader = self.create_oci_downloader_with_mocked_values()
        report_name = self.cost_file_path
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
        key = self.test_cost_report_name
        start_date = self.dh.today
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
        key = self.test_cost_report_name
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
        file_name = self.test_cost_report_name
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, file_name)
        shutil.copy2(self.cost_file_path, temp_path)
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
