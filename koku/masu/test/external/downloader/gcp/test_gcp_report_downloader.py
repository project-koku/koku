"""Test the GCPReportDownloader class."""
import datetime
import logging
import os
import shutil
import tempfile
from unittest.mock import patch
from unittest.mock import PropertyMock
from uuid import uuid4

from dateutil.relativedelta import relativedelta
from django.test.utils import override_settings
from faker import Faker
from google.cloud.exceptions import GoogleCloudError
from pytz import timezone
from rest_framework.exceptions import ValidationError

from api.utils import DateHelper
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external import UNCOMPRESSED
from masu.external.date_accessor import DateAccessor
from masu.external.downloader.gcp.gcp_report_downloader import create_daily_archives
from masu.external.downloader.gcp.gcp_report_downloader import DATA_DIR
from masu.external.downloader.gcp.gcp_report_downloader import GCPReportDownloader
from masu.external.downloader.gcp.gcp_report_downloader import GCPReportDownloaderError
from masu.test import MasuTestCase
from masu.util.common import date_range_pair
from reporting_common.models import CostUsageReportManifest

LOG = logging.getLogger(__name__)

FAKE = Faker()


def create_expected_csv_files(start_date, end_date, invoice_month, etag, keys=False):
    """Create the list of expected csv."""
    files = list()
    for start, end in date_range_pair(start_date, end_date):
        end = end + relativedelta(days=1)
        files.append(f"{invoice_month}_{etag}_{start}:{end}.csv")
    if keys:
        return [{"key": f"{f}", "local_file": f"{f}"} for f in files]
    return files


class GCPReportDownloaderTest(MasuTestCase):
    """Test Cases for the GCPReportDownloader object."""

    def setUp(self):
        """Setup vars for test."""
        super().setUp()
        self.etag = "1234"
        self.today = DateHelper().today

    def tearDown(self):
        """Remove files and directories created during the test run."""
        super().tearDown()
        shutil.rmtree(DATA_DIR, ignore_errors=True)

    def create_gcp_downloader_with_mocked_values(
        self,
        customer_name=FAKE.name(),
        dataset=FAKE.slug(),
        project_id=FAKE.slug(),
        table_id=FAKE.slug(),
    ):
        """
        Create a GCPReportDownloader that skips the initial GCP bigquery check creates etag.

        This also results in Mock objects being set to instance variables that can be patched
        inside other test functions.

        Args:
            customer_name (str): optional customer name; will be randomly generated if None
            bucket_name (str): optional bucket name; will be randomly generated if None
            provider_uuid (uuid): optional provider UUID; will be randomly generated if None

        Returns:
            GCPReportDownloader instance with faked argument data and Mocks in
            self.etag.

        """
        billing_source = {"table_id": table_id, "dataset": dataset}
        credentials = {"project_id": project_id}
        with patch("masu.external.downloader.gcp.gcp_report_downloader.GCPProvider"):
            downloader = GCPReportDownloader(
                customer_name=customer_name,
                data_source=billing_source,
                provider_uuid=self.gcp_provider_uuid,
                credentials=credentials,
            )
        return downloader

    @patch("masu.external.downloader.gcp.gcp_report_downloader.os.makedirs")
    @patch("masu.external.downloader.gcp.gcp_report_downloader.bigquery")
    def test_download_file_failure_on_file_open(self, mock_bigquery, mock_makedirs):
        """Assert download_file successful scenario"""
        mock_bigquery.client.return_value.query.return_value = ["This", "test"]
        key = "202011_1234_2020-12-05:2020-12-08.csv"
        downloader = self.create_gcp_downloader_with_mocked_values()
        with patch("masu.external.downloader.gcp.gcp_report_downloader.open") as mock_open:
            err_msg = "bad open"
            mock_open.side_effect = IOError(err_msg)
            with self.assertRaisesRegex(GCPReportDownloaderError, err_msg):
                downloader.download_file(key)

    def test_get_local_file_for_report(self):
        """Assert that get_local_file_for_report is a simple pass-through."""
        downloader = self.create_gcp_downloader_with_mocked_values()
        report_name = FAKE.file_path()
        local_name = downloader.get_local_file_for_report(report_name)
        self.assertEqual(local_name, report_name)

    @patch("masu.external.downloader.gcp.gcp_report_downloader.os.makedirs")
    @patch("masu.external.downloader.gcp.gcp_report_downloader.bigquery")
    def test_download_file_success(self, mock_bigquery, mock_makedirs):
        """Assert download_file successful scenario"""
        mock_bigquery.client.return_value.query.return_value = ["This", "test"]
        key = "202011_1234_2020-12-05:2020-12-08.csv"
        mock_name = "mock-test-customer-success"
        expected_full_path = f"{DATA_DIR}/{mock_name}/gcp/{key}"
        downloader = self.create_gcp_downloader_with_mocked_values(customer_name=mock_name)
        with patch("masu.external.downloader.gcp.gcp_report_downloader.open"):
            with patch(
                "masu.external.downloader.gcp.gcp_report_downloader.create_daily_archives",
                return_value=[["file_one", "file_two"], {"start": "", "end": ""}],
            ):
                full_path, _, date, _, __ = downloader.download_file(key)
                mock_makedirs.assert_called()
                self.assertEqual(date, self.today)
                self.assertEqual(full_path, expected_full_path)

    @patch("masu.external.downloader.gcp.gcp_report_downloader.os.makedirs")
    @patch("masu.external.downloader.gcp.gcp_report_downloader.bigquery")
    def test_download_file_success_end_date_today(self, mock_bigquery, mock_makedirs):
        """Assert download_file successful scenario"""
        mock_bigquery.client.return_value.query.return_value = ["This", "test"]
        end_date = DateAccessor().today().date()
        key = f"202011_1234_2020-12-05:{end_date}.csv"
        mock_name = "mock-test-customer-end-date"
        expected_full_path = f"{DATA_DIR}/{mock_name}/gcp/{key}"
        downloader = self.create_gcp_downloader_with_mocked_values(customer_name=mock_name)
        with patch("masu.external.downloader.gcp.gcp_report_downloader.open"):
            with patch(
                "masu.external.downloader.gcp.gcp_report_downloader.create_daily_archives",
                return_value=[["file_one", "file_two"], {"start": "", "end": ""}],
            ):
                full_path, _, date, _, __ = downloader.download_file(key)
                mock_makedirs.assert_called()
                self.assertEqual(date, self.today)
                self.assertEqual(full_path, expected_full_path)

    @patch("masu.external.downloader.gcp.gcp_report_downloader.open")
    def test_download_file_query_client_error(self, mock_open):
        """Test BigQuery client is handled correctly in download file method."""
        key = "202011_1234_2020-12-05:2020-12-08.csv"
        downloader = self.create_gcp_downloader_with_mocked_values()
        err_msg = "GCP Error"
        with patch("masu.external.downloader.gcp.gcp_report_downloader.bigquery") as bigquery:
            bigquery.Client.side_effect = GoogleCloudError(err_msg)
            with self.assertRaisesRegex(GCPReportDownloaderError, err_msg):
                downloader.download_file(key)

    @patch("masu.external.downloader.gcp.gcp_report_downloader.GCPProvider")
    def test_download_with_unreachable_source(self, gcp_provider):
        """Assert errors correctly when source is unreachable."""
        gcp_provider.return_value.cost_usage_source_is_reachable.side_effect = ValidationError
        billing_source = {"table_id": FAKE.slug(), "dataset": FAKE.slug()}
        credentials = {"project_id": FAKE.slug()}
        with self.assertRaises(GCPReportDownloaderError):
            GCPReportDownloader(FAKE.name(), billing_source, credentials=credentials)

    def test_get_manifest_context_for_date(self):
        """Test successful return of get manifest context for date."""
        manifests = CostUsageReportManifest.objects.filter(provider_id=self.gcp_provider_uuid)
        for manifest in manifests:
            manifest.assembly_id = f"{manifest.billing_period_start_datetime.date()}|{DateHelper().today}"
            manifest.save()
        self.maxDiff = None
        dh = DateHelper()
        start_date = dh.this_month_start
        invoice_month = start_date.strftime("%Y%m")
        downloader = self.create_gcp_downloader_with_mocked_values()
        mocked_mapping = {datetime.date.today(): DateHelper().today}
        with patch(
            "masu.external.downloader.gcp.gcp_report_downloader.GCPReportDownloader._process_manifest_db_record",
            return_value=2,
        ):
            with patch(
                "masu.external.downloader.gcp.gcp_report_downloader.GCPReportDownloader"
                + ".bigquery_export_to_partition_mapping",
                return_value=mocked_mapping,
            ):
                report_list = downloader.get_manifest_context_for_date(start_date.date())
        expected_file = f"{invoice_month}_{DateHelper().today.date()}.csv"
        expected_files = [{"key": expected_file, "local_file": expected_file}]
        for report_dict in report_list:
            self.assertEqual(report_dict.get("manifest_id"), 2)
            self.assertEqual(report_dict.get("files"), expected_files)
            self.assertEqual(report_dict.get("compression"), UNCOMPRESSED)

    @override_settings(ENABLE_PARQUET_PROCESSING=True)
    @patch("masu.external.downloader.gcp.gcp_report_downloader.copy_local_report_file_to_s3_bucket")
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

    @override_settings(ENABLE_PARQUET_PROCESSING=True)
    @patch("masu.external.downloader.gcp.gcp_report_downloader.copy_local_report_file_to_s3_bucket")
    def test_create_daily_archives_error_opening_file(self, mock_s3):
        """
        Test that we handle effor while opening csv file.
        """
        with patch("masu.external.downloader.gcp.gcp_report_downloader.pd.read_csv") as mock_open:
            err_msg = "bad_open"
            mock_open.side_effect = IOError(err_msg)
            with self.assertRaisesRegex(GCPReportDownloaderError, err_msg):
                create_daily_archives(
                    "request_id", "acccount", self.gcp_provider_uuid, "fake", "fake", None, "fake", None
                )

    def test_get_dataset_name(self):
        """Test _get_dataset_name helper."""
        project_id = FAKE.slug()
        dataset_name = FAKE.slug()

        datasets = [f"{project_id}:{dataset_name}", dataset_name]

        for dataset in datasets:
            billing_source = {"table_id": FAKE.slug(), "dataset": dataset}
            credentials = {"project_id": project_id}

            with patch("masu.external.downloader.gcp.gcp_report_downloader.GCPProvider"):
                downloader = GCPReportDownloader(
                    customer_name=FAKE.name(),
                    data_source=billing_source,
                    provider_uuid=uuid4(),
                    credentials=credentials,
                )

            self.assertEqual(downloader._get_dataset_name(), dataset_name)

    def test_scan_start_setup_complete(self):
        """Test scan start when provider setup is complete"""
        dh = DateHelper()
        downloader = self.create_gcp_downloader_with_mocked_values()
        if self.gcp_provider.setup_complete:
            expected_scan_start = dh.today.date() - relativedelta(days=10)
            self.assertEqual(downloader.scan_start, expected_scan_start)

    def test_scan_start_setup_not_complete(self):
        """Test scan start provider setup is not complete"""
        dh = DateHelper()
        downloader = self.create_gcp_downloader_with_mocked_values()
        if self.gcp_provider.setup_complete:
            self.gcp_provider.setup_complete = False

        months_delta = Config.INITIAL_INGEST_NUM_MONTHS - 1
        expected_scan_start = dh.today.date() - relativedelta(months=months_delta)
        expected_scan_start = expected_scan_start.replace(day=1)
        self.assertEqual(downloader.scan_start, expected_scan_start)

    def test_retrieve_current_manifests_mapping(self):
        """Test retrieving existing manifests mapping given bill_date and provider"""
        manifests = CostUsageReportManifest.objects.filter(provider_id=self.gcp_provider_uuid)
        for manifest in manifests:
            manifest.assembly_id = f"{manifest.billing_period_start_datetime.date()}|{DateHelper().today}"
            manifest.save()
        downloader = self.create_gcp_downloader_with_mocked_values()
        expected_manifest_mapping = {}
        expected_manifests = []
        with ReportManifestDBAccessor() as manifest_accessor:
            expected_manifests = manifest_accessor.get_manifest_list_for_provider_and_date_range(
                self.gcp_provider_uuid, downloader.scan_start, downloader.scan_end
            )
        for manifest in expected_manifests:
            last_export_time = expected_manifest_mapping.get(manifest.partition_date)
            if not last_export_time or manifest.previous_export_time > last_export_time:
                expected_manifest_mapping[manifest.partition_date] = manifest.previous_export_time

        current_manifests_mapping = downloader.retrieve_current_manifests_mapping()

        self.assertEqual(current_manifests_mapping, expected_manifest_mapping)

    def test_bigquery_export_to_partition_mapping_error(self):
        """Test GCP error retrieving partition data."""
        downloader = self.create_gcp_downloader_with_mocked_values()
        err_msg = "GCP Error"
        with patch("masu.external.downloader.gcp.gcp_report_downloader.bigquery") as bigquery:
            bigquery.Client.side_effect = GoogleCloudError(err_msg)
            with self.assertRaisesRegex(GCPReportDownloaderError, err_msg):
                downloader.bigquery_export_to_partition_mapping()

    def test_bigquery_export_to_partition_mapping_success(self):
        """Test GCP error retrieving partition data."""
        key = datetime.date.today()
        now_utc = datetime.datetime.now(timezone("UTC"))
        mocked_result = [[key, now_utc]]
        with patch(
            "masu.external.downloader.gcp.gcp_report_downloader.bigquery", new_callable=PropertyMock
        ) as mock_bigquery:
            mock_bigquery.Client.return_value.query.return_value.result.return_value = mocked_result
            downloader = self.create_gcp_downloader_with_mocked_values()
            mapping = downloader.bigquery_export_to_partition_mapping()
            self.assertEqual(mapping, {key: now_utc})
