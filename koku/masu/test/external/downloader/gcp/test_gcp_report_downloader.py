"""Test the GCPReportDownloader class."""
import shutil
from datetime import datetime
from unittest.mock import patch
from uuid import uuid4

from faker import Faker
from google.cloud.exceptions import GoogleCloudError
from rest_framework.exceptions import ValidationError

from api.utils import DateHelper
from masu.external import UNCOMPRESSED
from masu.external.downloader.gcp.gcp_report_downloader import DATA_DIR
from masu.external.downloader.gcp.gcp_report_downloader import GCPReportDownloader
from masu.external.downloader.gcp.gcp_report_downloader import GCPReportDownloaderError
from masu.test import MasuTestCase

FAKE = Faker()


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
        provider_uuid=uuid4(),
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
        with patch("masu.external.downloader.gcp.gcp_report_downloader.GCPProvider"), patch(
            "masu.external.downloader.gcp.gcp_report_downloader.GCPReportDownloader._generate_etag",
            return_value=self.etag,
        ):
            downloader = GCPReportDownloader(
                customer_name=customer_name,
                data_source=billing_source,
                provider_uuid=provider_uuid,
                credentials=credentials,
            )
        return downloader

    @patch("masu.external.downloader.gcp.gcp_report_downloader.GCPProvider")
    def test_generate_etag_big_query_client_error(self, gcp_provider):
        """Test BigQuery client is handled correctly in generate etag method."""
        billing_source = {"table_id": FAKE.slug(), "dataset": FAKE.slug()}
        credentials = {"project_id": FAKE.slug()}
        err_msg = "GCP Error"
        with patch("masu.external.downloader.gcp.gcp_report_downloader.bigquery") as bigquery:
            bigquery.Client.side_effect = GoogleCloudError(err_msg)
            with self.assertRaisesRegexp(GCPReportDownloaderError, err_msg):
                GCPReportDownloader(
                    customer_name=FAKE.name(),
                    data_source=billing_source,
                    provider_uuid=uuid4(),
                    credentials=credentials,
                )

    @patch("masu.external.downloader.gcp.gcp_report_downloader.GCPProvider")
    def test_generate_etag(self, gcp_provider):
        """Test BigQuery client is handled correctly in generate etag method."""
        billing_source = {"table_id": FAKE.slug(), "dataset": FAKE.slug()}
        credentials = {"project_id": FAKE.slug()}
        with patch("masu.external.downloader.gcp.gcp_report_downloader.bigquery") as bigquery:
            bigquery.Client.return_value.get_table.return_value.modified.return_value = self.today
            downloader = GCPReportDownloader(
                customer_name=FAKE.name(), data_source=billing_source, provider_uuid=uuid4(), credentials=credentials
            )
            self.assertIsNotNone(downloader.etag)

    @patch("masu.external.downloader.gcp.gcp_report_downloader.os.makedirs")
    @patch("masu.external.downloader.gcp.gcp_report_downloader.bigquery")
    def test_download_file_failure_on_file_open(self, mock_bigquery, mock_makedirs):
        """Assert download_file successful scenario"""
        mock_bigquery.client.return_value.query.return_value = ["This", "test"]
        key = "test_key.csv"
        downloader = self.create_gcp_downloader_with_mocked_values()
        with patch("masu.external.downloader.gcp.gcp_report_downloader.open") as mock_open:
            err_msg = "bad open"
            mock_open.side_effect = IOError(err_msg)
            with self.assertRaisesRegexp(GCPReportDownloaderError, err_msg):
                downloader.download_file(key)

    def test_generate_monthly_pseudo_manifest(self):
        """Assert _generate_monthly_pseudo_manifest returns a manifest-like dict."""
        provider_uuid = uuid4()
        start_date = datetime(2019, 2, 1)
        invoice_month = start_date.strftime("%Y%m")
        expected_end_date = datetime(2019, 2, 28)
        expected_assembly_id = ":".join([str(provider_uuid), self.etag, invoice_month])
        downloader = self.create_gcp_downloader_with_mocked_values(provider_uuid=provider_uuid)
        result_manifest = downloader._generate_monthly_pseudo_manifest(start_date)
        expected_manifest_data = {
            "assembly_id": expected_assembly_id,
            "compression": UNCOMPRESSED,
            "start_date": start_date,
            "end_date": expected_end_date,  # inclusive end date
            "file_names": [f"{invoice_month}_{self.etag}_{downloader.query_date}:{self.today.date()}.csv"],
        }
        self.assertEqual(result_manifest, expected_manifest_data)

    def test_generate_assembly_id(self):
        """Assert appropriate generation of assembly ID."""
        provider_uuid = uuid4()
        expected_assembly_id = ":".join([str(provider_uuid), self.etag, "1"])
        downloader = self.create_gcp_downloader_with_mocked_values(provider_uuid=provider_uuid)
        assembly_id = downloader._generate_assembly_id("1")
        self.assertEqual(assembly_id, expected_assembly_id)

    def test_relevant_file_names(self):
        """Assert relevant file name is generated correctly."""
        downloader = self.create_gcp_downloader_with_mocked_values()
        mock_invoice_month = self.today.strftime("%Y%m")
        expected_file_name = [f"{mock_invoice_month}_{self.etag}_{downloader.query_date}:{self.today.date()}.csv"]
        result_file_names = downloader._get_relevant_file_names(mock_invoice_month)
        self.assertEqual(expected_file_name, result_file_names)

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
        key = "test_key.csv"
        mock_name = "Cody"
        expected_full_path = f"{DATA_DIR}/{mock_name}/gcp/{key}"
        downloader = self.create_gcp_downloader_with_mocked_values(customer_name=mock_name)
        with patch("masu.external.downloader.gcp.gcp_report_downloader.open"):
            full_path, etag, date = downloader.download_file(key)
            mock_makedirs.assert_called()
            self.assertEqual(etag, self.etag)
            self.assertEqual(date, self.today)
            self.assertEqual(full_path, expected_full_path)

    @patch("masu.external.downloader.gcp.gcp_report_downloader.open")
    def test_download_file_query_client_error(self, mock_open):
        """Test BigQuery client is handled correctly in download file method."""
        key = "test_key.csv"
        downloader = self.create_gcp_downloader_with_mocked_values()
        err_msg = "GCP Error"
        with patch("masu.external.downloader.gcp.gcp_report_downloader.bigquery") as bigquery:
            bigquery.Client.side_effect = GoogleCloudError(err_msg)
            with self.assertRaisesRegexp(GCPReportDownloaderError, err_msg):
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
        start_date = datetime(2019, 2, 1)
        invoice_month = start_date.strftime("%Y%m")
        p_uuid = uuid4()
        expected_assembly_id = f"{p_uuid}:{self.etag}:{invoice_month}"
        downloader = self.create_gcp_downloader_with_mocked_values(provider_uuid=p_uuid)
        csv_file = f"{invoice_month}_{self.etag}_{downloader.query_date}:{self.today.date()}.csv"
        expected_files = [{"key": csv_file, "local_file": csv_file}]
        with patch(
            "masu.external.downloader.gcp.gcp_report_downloader.GCPReportDownloader._process_manifest_db_record",
            return_value=2,
        ):
            report_dict = downloader.get_manifest_context_for_date(start_date)
        self.assertEqual(report_dict.get("manifest_id"), 2)
        self.assertEqual(report_dict.get("files"), expected_files)
        self.assertEqual(report_dict.get("compression"), UNCOMPRESSED)
        self.assertEqual(report_dict.get("assembly_id"), expected_assembly_id)
