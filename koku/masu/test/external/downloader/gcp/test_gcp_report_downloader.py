"""Test the GCPReportDownloader class."""
import datetime
import os
import shutil
import tempfile
from unittest.mock import patch
from unittest.mock import PropertyMock
from uuid import uuid4

from dateutil.relativedelta import relativedelta
from django.conf import settings
from faker import Faker
from google.cloud.exceptions import GoogleCloudError
from rest_framework.exceptions import ValidationError

from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external import UNCOMPRESSED
from masu.external.downloader.gcp.gcp_report_downloader import create_daily_archives
from masu.external.downloader.gcp.gcp_report_downloader import DATA_DIR
from masu.external.downloader.gcp.gcp_report_downloader import GCPReportDownloader
from masu.external.downloader.gcp.gcp_report_downloader import GCPReportDownloaderError
from masu.test import MasuTestCase
from masu.util.common import CreateDailyArchivesError
from masu.util.common import date_range_pair
from reporting_common.models import CostUsageReportManifest

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
        self.today = self.dh.today
        self.fake_customer_name = FAKE.word()
        self.credentials = {"project_id": "project"}
        self.data_source = {"bucket": "bucket"}
        self.billing_source = {"table_id": "table_id", "dataset": "dataset"}
        self.storage_only_data_source = {"bucket": "bucket", "storage_only": True}
        self.ingress_reports = ["test_report_file.csv"]

        with patch("masu.external.downloader.gcp.gcp_report_downloader.GCPProvider"):
            self.downloader = GCPReportDownloader(
                self.fake_customer_name,
                data_source=self.billing_source,
                provider_uuid=self.gcp_provider_uuid,
                credentials=self.credentials,
            )
            self.storage_only_downloader = GCPReportDownloader(self.fake_customer_name, self.storage_only_data_source)
            with patch("masu.external.downloader.gcp.gcp_report_downloader.storage"):
                self.gcp_ingress_report_downloader = GCPReportDownloader(
                    self.fake_customer_name,
                    self.storage_only_data_source,
                    ingress_reports=self.ingress_reports,
                    provider_uuid=self.gcp_provider_uuid,
                    credentials=self.credentials,
                )
        self.gcp_manifest = CostUsageReportManifest.objects.filter(provider_id=self.gcp_provider_uuid).first()
        self.gcp_manifest_id = self.gcp_manifest.id

    def tearDown(self):
        """Remove files and directories created during the test run."""
        super().tearDown()
        shutil.rmtree(DATA_DIR, ignore_errors=True)

    @patch("masu.external.downloader.gcp.gcp_report_downloader.os.makedirs")
    @patch("masu.external.downloader.gcp.gcp_report_downloader.bigquery")
    def test_download_file_failure_on_file_open(self, mock_bigquery, mock_makedirs):
        """Assert download_file successful scenario"""
        mock_bigquery.Client.return_value.query.return_value.result.return_value = ["a", "b", "c", "d"]
        key = "202011_1234_2020-12-05:2020-12-08.csv"
        downloader = self.downloader
        with patch("masu.external.downloader.gcp.gcp_report_downloader.open") as mock_open:
            err_msg = "bad open"
            mock_open.side_effect = IOError(err_msg)
            with self.assertRaisesRegex(GCPReportDownloaderError, err_msg):
                downloader.download_file(key)
                mock_bigquery.assert_called()
                mock_open.assert_called()

    def test_get_local_file_for_report(self):
        """Assert that get_local_file_for_report is a simple pass-through."""
        downloader = self.downloader
        report_name = FAKE.file_path()
        local_name = downloader.get_local_file_for_report(report_name)
        self.assertEqual(local_name, report_name)

    @patch("masu.external.downloader.gcp.gcp_report_downloader.os.makedirs")
    @patch("masu.external.downloader.gcp.gcp_report_downloader.bigquery")
    def test_download_file_success(self, mock_bigquery, mock_makedirs):
        """Assert download_file successful scenario"""
        mock_bigquery.client.return_value.query.return_value = ["This", "test"]
        key = "202011_1234_2020-12-05:2020-12-08.csv"
        downloader = self.downloader
        with patch("masu.external.downloader.gcp.gcp_report_downloader.open"):
            with patch(
                "masu.external.downloader.gcp.gcp_report_downloader.create_daily_archives",
                return_value=[["file_one", "file_two"], {"start": "", "end": ""}],
            ):
                full_path, _, date, __, ___ = downloader.download_file(key)
                mock_makedirs.assert_called()
                self.assertEqual(date, self.today)
                self.assertEqual(full_path, key)

    @patch("masu.external.downloader.gcp.gcp_report_downloader.os.makedirs")
    @patch("masu.external.downloader.gcp.gcp_report_downloader.bigquery")
    def test_download_file_success_end_date_today(self, mock_bigquery, mock_makedirs):
        """Assert download_file successful scenario"""
        mock_bigquery.client.return_value.query.return_value = ["This", "test"]
        partition_date = self.today.date()
        export_time = self.today
        key = f"202011_{partition_date}_{export_time}.csv"
        downloader = self.downloader
        with patch("masu.external.downloader.gcp.gcp_report_downloader.open"):
            with patch(
                "masu.external.downloader.gcp.gcp_report_downloader.create_daily_archives",
                return_value=[["file_one", "file_two"], {"start": "", "end": ""}],
            ):
                full_path, _, date, __, ___ = downloader.download_file(key)
                mock_makedirs.assert_called()
                self.assertEqual(date, self.today)
                self.assertEqual(full_path, key)

    @patch("masu.external.downloader.gcp.gcp_report_downloader.open")
    def test_download_file_query_client_error(self, mock_open):
        """Test BigQuery client is handled correctly in download file method."""
        key = "202011_1234_2020-12-05:2020-12-08.csv"
        downloader = self.downloader
        err_msg = "GCP Error"
        expected_error_msg = "Could not query table for billing information."
        with patch("masu.external.downloader.gcp.gcp_report_downloader.bigquery") as bigquery:
            bigquery.Client.side_effect = GoogleCloudError(err_msg)
            with self.assertRaisesRegex(GCPReportDownloaderError, expected_error_msg):
                downloader.download_file(key)

    @patch("masu.external.downloader.gcp.gcp_report_downloader.open")
    def test_download_file_query_unbound_error(self, mock_open):
        """Test BigQuery client is handled correctly in download file method."""
        key = "202011_1234_2020-12-05:2020-12-08.csv"
        downloader = self.downloader
        err_msg = "GCP Error"
        with patch("masu.external.downloader.gcp.gcp_report_downloader.bigquery") as bigquery:
            bigquery.Client.side_effect = UnboundLocalError(err_msg)
            with self.assertRaises(GCPReportDownloaderError):
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
            manifest.assembly_id = f"{manifest.billing_period_start_datetime.date()}|{self.today}"
            manifest.save()
        self.maxDiff = None
        start_date = self.dh.this_month_start
        invoice_month = start_date.strftime("%Y%m")
        downloader = self.downloader
        mocked_mapping = {datetime.date.today(): self.today}
        with patch(
            "masu.external.downloader.gcp.gcp_report_downloader.GCPReportDownloader._process_manifest_db_record",
            return_value=2,
        ):
            with patch(
                "masu.external.downloader.gcp.gcp_report_downloader.GCPReportDownloader"
                + ".bigquery_export_to_partition_mapping",
                return_value=mocked_mapping,
            ):
                report_list = downloader.get_manifest_context_for_date(start_date)
        expected_file = f"{invoice_month}_{self.today.date()}"
        expected_files = [{"key": expected_file, "local_file": expected_file}]
        for report_dict in report_list:
            self.assertEqual(report_dict.get("manifest_id"), 2)
            self.assertEqual(report_dict.get("files"), expected_files)
            self.assertEqual(report_dict.get("compression"), UNCOMPRESSED)

    @patch("masu.external.downloader.gcp.gcp_report_downloader.copy_local_report_file_to_s3_bucket")
    def test_create_daily_archives(self, mock_s3):
        """Test that we load daily files to S3."""
        # Use the processor example for data:
        file_name = "2022-08-01_5.csv"
        partition = "2022-08-01"
        file_path = f"./koku/masu/test/data/gcp/{file_name}"
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, file_name)
        shutil.copy2(file_path, temp_path)
        expected_daily_files = [
            f"{temp_dir}/202208_{partition}_{file_name}",
        ]
        start_date = self.dh.this_month_start
        daily_file_names, date_range = create_daily_archives(
            "request_id", "account", self.gcp_provider_uuid, [temp_path], None, start_date, None
        )
        expected_date_range = {"start": "2022-08-01", "end": "2022-08-01"}
        self.assertEqual(date_range, expected_date_range)
        self.assertIsInstance(daily_file_names, list)
        mock_s3.assert_called()
        self.assertEqual(sorted(daily_file_names), sorted(expected_daily_files))
        for daily_file in expected_daily_files:
            self.assertTrue(os.path.exists(daily_file))
            os.remove(daily_file)
        os.remove(temp_path)

    @patch("masu.external.downloader.gcp.gcp_report_downloader.copy_local_report_file_to_s3_bucket")
    def test_create_daily_archives_leading_zeros(self, mock_s3):
        """Test if create_daily_archives function is keeping the leading zeros after download."""
        # Use the processor example for data:
        file_name = "2022-08-01_5.csv"
        file_path = f"./koku/masu/test/data/gcp/{file_name}"
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, file_name)
        shutil.copy2(file_path, temp_path)
        start_date = self.dh.this_month_start
        daily_file_names, _ = create_daily_archives(
            "request_id", "account", self.gcp_provider_uuid, [temp_path], None, start_date, None
        )
        for daily_file in daily_file_names:
            with open(daily_file) as file:
                csv = file.readlines()

            self.assertIn("018984-D0AAA4-940B88", csv[1].split(","))
        os.remove(temp_path)

    @patch("masu.external.downloader.gcp.gcp_report_downloader.copy_local_report_file_to_s3_bucket")
    def test_create_daily_archives_error_opening_file(self, mock_s3):
        """
        Test that we handle error while opening csv file.
        """
        with patch("masu.external.downloader.gcp.gcp_report_downloader.pd.read_csv") as mock_open:
            err_msg = "unable to create daily archives from: fake"
            mock_open.side_effect = IOError(err_msg)
            with self.assertRaisesRegex(CreateDailyArchivesError, err_msg):
                create_daily_archives("request_id", "acccount", self.gcp_provider_uuid, "fake", None, "fake", None)

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

    @patch("masu.external.downloader.gcp.gcp_report_downloader.Provider")
    def test_scan_start_setup_complete(self, provider):
        """Test scan start when provider setup is complete"""
        provider.setup_complete = True
        expected_scan_start = self.dh.today.date() - relativedelta(days=10)
        downloader = self.downloader
        self.assertEqual(downloader.scan_start, expected_scan_start)

    def test_scan_start_setup_not_complete(self):
        """Test scan start provider setup is not complete"""
        downloader = self.downloader
        if self.gcp_provider.setup_complete:
            self.gcp_provider.setup_complete = False
        months_delta = Config.INITIAL_INGEST_NUM_MONTHS - 1
        expected_scan_start = self.dh.today.date() - relativedelta(months=months_delta)
        expected_scan_start = expected_scan_start.replace(day=1)
        self.assertEqual(downloader.scan_start, expected_scan_start)

    def test_retrieve_current_manifests_mapping(self):
        """Test retrieving existing manifests mapping given bill_date and provider"""
        manifests = CostUsageReportManifest.objects.filter(provider_id=self.gcp_provider_uuid)
        for manifest in manifests:
            manifest.assembly_id = f"{manifest.billing_period_start_datetime.date()}|{self.today}"
            manifest.save()
        downloader = self.downloader
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
        downloader = self.downloader
        err_msg = "GCP Error"
        expected_error_msg = "could not query table for partition date information"
        with patch("masu.external.downloader.gcp.gcp_report_downloader.bigquery") as bigquery:
            bigquery.Client.side_effect = GoogleCloudError(err_msg)
            with self.assertRaisesRegex(GCPReportDownloaderError, expected_error_msg):
                downloader.bigquery_export_to_partition_mapping()

    def test_bigquery_export_to_partition_mapping_success(self):
        """Test GCP error retrieving partition data."""
        key = datetime.date.today()
        now_utc = datetime.datetime.now(tz=settings.UTC)
        mocked_result = [[key, now_utc]]
        with patch(
            "masu.external.downloader.gcp.gcp_report_downloader.bigquery", new_callable=PropertyMock
        ) as mock_bigquery:
            mock_bigquery.Client.return_value.query.return_value.result.return_value = mocked_result
            downloader = self.downloader
            mapping = downloader.bigquery_export_to_partition_mapping()
            self.assertEqual(mapping, {key: now_utc})

    def test_collect_new_manifest_initial_ingest(self):
        """Test collecting new manifests on initial ingest"""
        partition_date = datetime.date.today()
        export_time = datetime.datetime.now()
        current_manifests = {}
        bigquery_mapping = {partition_date: export_time}
        expected_bill_date = partition_date.replace(day=1)
        expected_assembly_id = f"{partition_date}|{export_time}"
        expected_filename = f"{expected_bill_date.strftime('%Y%m')}_{partition_date}"
        downloader = self.downloader
        new_manifests = downloader.collect_new_manifests(current_manifests, bigquery_mapping)
        for manifest_metadata in new_manifests:
            self.assertEqual(manifest_metadata["bill_date"], expected_bill_date)
            self.assertEqual(manifest_metadata["assembly_id"], expected_assembly_id)
            self.assertEqual(manifest_metadata["files"], [expected_filename])

    def test_collect_new_manifest(self):
        """Test collecting new manifests when there is new data in BigQuery"""
        partition_date = datetime.date.today()
        export_time = datetime.datetime.now()
        new_export_time = export_time + datetime.timedelta(hours=2)
        current_manifests = {partition_date: export_time}
        bigquery_mapping = {partition_date: new_export_time}
        expected_bill_date = partition_date.replace(day=1)
        expected_assembly_id = f"{partition_date}|{new_export_time}"
        expected_filename = f"{expected_bill_date.strftime('%Y%m')}_{partition_date}"
        downloader = self.downloader
        new_manifests = downloader.collect_new_manifests(current_manifests, bigquery_mapping)
        for manifest_metadata in new_manifests:
            self.assertEqual(manifest_metadata["bill_date"], expected_bill_date)
            self.assertEqual(manifest_metadata["assembly_id"], expected_assembly_id)
            self.assertEqual(manifest_metadata["files"], [expected_filename])

    def test_collect_new_manifest_no_bigquery_update(self):
        """Test collecting new manifests when there is no new data in BigQuery"""
        partition_date = datetime.date.today()
        export_time = datetime.datetime.now()
        current_manifests = {partition_date: export_time}
        bigquery_mapping = {partition_date: export_time}
        expected_bill_date = partition_date.replace(day=1)
        expected_assembly_id = f"{partition_date}|{export_time}"
        expected_filename = f"{expected_bill_date.strftime('%Y%m')}_{partition_date}"
        downloader = self.downloader
        new_manifests = downloader.collect_new_manifests(current_manifests, bigquery_mapping)
        for manifest_metadata in new_manifests:
            self.assertEqual(manifest_metadata["bill_date"], expected_bill_date)
            self.assertEqual(manifest_metadata["assembly_id"], expected_assembly_id)
            self.assertEqual(manifest_metadata["files"], [expected_filename])

    def test_generate_pseudo_manifest(self):
        """Test Generating pseudo manifest for storage only."""
        mock_datetime = self.dh.now
        mock_date_str = mock_datetime.strftime("%Y-%m-%d")
        expected_manifest_data = {
            "bill_date": mock_date_str,
            "files": self.ingress_reports,
        }
        result_manifest = self.gcp_ingress_report_downloader.collect_pseudo_manifests(mock_datetime)
        self.assertEqual(result_manifest, result_manifest | expected_manifest_data)
        self.assertIn(mock_date_str, result_manifest["assembly_id"])

    def test_get_storage_only_manifest_file(self):
        """Test _get_manifest method w storage only."""
        mock_datetime = self.dh.now
        result = self.storage_only_downloader.get_manifest_context_for_date(mock_datetime)
        self.assertEqual(result, [])

    def test_get_ingress_report_manifest_context_for_date(self):
        """Test that the pseudo manifest is created and read."""
        mock_datetime = self.dh.now
        result = self.gcp_ingress_report_downloader.get_manifest_context_for_date(mock_datetime)[0]
        self.assertEqual(result.get("compression"), UNCOMPRESSED)
        self.assertIsNotNone(result.get("files"))

    @patch("masu.external.downloader.gcp.gcp_report_downloader.os.makedirs")
    @patch("masu.external.downloader.gcp.gcp_report_downloader.storage")
    def test_ingress_report_download_file_success(self, mock_storage, mock_makedirs):
        """Assert ingress download_file successful scenario"""
        key = "ingress_report.csv"
        with patch(
            "masu.external.downloader.gcp.gcp_report_downloader.create_daily_archives",
            return_value=[["file_one", "file_two"], {"start": "", "end": ""}],
        ):
            full_path, _, date, __, ___ = self.gcp_ingress_report_downloader.download_file(key)
            mock_makedirs.assert_called()
            self.assertEqual(date, self.today)
            self.assertEqual(full_path, key)

    @patch("masu.external.downloader.gcp.gcp_report_downloader.storage")
    def test_ingress_report_download_file_blob_client_error(self, mock_storage):
        """Test Storage client error is handled correctly in download file method."""
        mock_storage.Client.side_effect = GoogleCloudError("GCP ERROR")
        key = "ingress_report.csv"
        with self.assertRaises(GCPReportDownloaderError):
            self.gcp_ingress_report_downloader.download_file(key)

    @patch("masu.external.downloader.gcp.gcp_report_downloader.copy_local_report_file_to_s3_bucket")
    def test_create_daily_archives_ingress_reports(self, mock_s3):
        """Test that we load daily files to S3."""
        file_name = "2022-08-01_5.csv"
        partition = "2022-08-01"
        file_path = f"./koku/masu/test/data/gcp/{file_name}"
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, file_name)
        shutil.copy2(file_path, temp_path)
        expected_daily_files = [
            f"{temp_dir}/202208_{partition}_manifestid-{self.gcp_manifest_id}_0.csv",
        ]
        context = {"account": self.schema_name, "provider_type": "GCP"}
        start_date = self.dh.this_month_start
        with patch("masu.external.downloader.gcp.gcp_report_downloader.clear_s3_files"):
            daily_file_names, date_range = create_daily_archives(
                "request_id",
                "account",
                self.gcp_provider_uuid,
                [temp_path],
                self.gcp_manifest_id,
                start_date,
                context,
                "ingress_reports",
            )
            expected_date_range = {"start": "2022-08-01", "end": "2022-08-01"}
            self.assertEqual(date_range, expected_date_range)
            self.assertIsInstance(daily_file_names, list)
            mock_s3.assert_called()
            self.assertEqual(sorted(daily_file_names), sorted(expected_daily_files))
            for daily_file in expected_daily_files:
                self.assertTrue(os.path.exists(daily_file))
                os.remove(daily_file)
            os.remove(temp_path)
