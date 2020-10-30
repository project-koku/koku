"""Test the GCPReportDownloader class."""
# import hashlib
import shutil
from datetime import datetime
from unittest.mock import patch
from uuid import uuid4

from faker import Faker
from rest_framework.exceptions import ValidationError

from api.utils import DateHelper
from masu.external import UNCOMPRESSED
from masu.external.downloader.gcp.gcp_report_downloader import DATA_DIR
from masu.external.downloader.gcp.gcp_report_downloader import GCPReportDownloader
from masu.external.downloader.gcp.gcp_report_downloader import GCPReportDownloaderError
from masu.test import MasuTestCase

# from unittest.mock import Mock
# from masu.external.downloader.gcp.gcp_report_downloader import GCPReportDownloaderNoFileError

FAKE = Faker()


def raise_vaildation_error(msg):
    raise ValidationError(msg=msg)


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

    def test_generate_monthly_pseudo_manifest(self):
        """Assert _generate_monthly_pseudo_manifest returns a manifest-like dict."""
        provider_uuid = uuid4()
        start_date = datetime(2019, 2, 1)
        expected_end_date = datetime(2019, 2, 28)
        expected_assembly_id = ":".join([str(provider_uuid), self.etag, "1"])
        downloader = self.create_gcp_downloader_with_mocked_values(provider_uuid=provider_uuid)
        result_manifest = downloader._generate_monthly_pseudo_manifest(start_date)
        expected_manifest_data = {
            "assembly_id": expected_assembly_id,
            "compression": UNCOMPRESSED,
            "start_date": start_date,
            "end_date": expected_end_date,  # inclusive end date
            "file_names": [f"{self.etag}_{self.today.date()}.csv"],
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
        expected_file_name = [f"{self.etag}_{self.today.date()}.csv"]
        downloader = self.create_gcp_downloader_with_mocked_values()
        result_file_names = downloader._get_relevant_file_names()
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

    @patch("masu.external.downloader.gcp.gcp_report_downloader.GCPProvider")
    def test_download_with_unreachable_source(self, gcp_provider):
        gcp_provider.return_value.cost_usage_source_is_reachable.side_effect = ValidationError
        billing_source = {"table_id": FAKE.slug(), "dataset": FAKE.slug()}
        credentials = {"project_id": FAKE.slug()}
        with self.assertRaises(GCPReportDownloaderError):
            GCPReportDownloader(FAKE.name(), billing_source, credentials=credentials)

    # @patch("masu.external.downloader.gcp.gcp_report_downloader.bigquery")
    # def test_generate_etag(self, mock_bigquery):
    #     expected_etag = hashlib.md5(str(self.today.date()).encode()).hexdigest()
    #     mock_bigquery.client.return_value.get_table.return_vlaue.modified.return_value = self.today
    #     downloader = self.create_gcp_downloader_with_mocked_values()
    #     result_etag = downloader._generate_etag()
    #     self.assertEqual(expected_etag, result_etag)

    # Coverage left to do:
    # 102-107, 124-151, 271, 270->271

    # @patch("masu.external.downloader.gcp.gcp_report_downloader.os.makedirs")
    # def test_download_file_without_etag(self, mock_makedirs):
    #     """Assert download_file downloads and returns local path with GCP's etag."""
    #     key = FAKE.file_path()
    #     expected_etag = FAKE.slug()
    #     mock_blob = MockBlob(etag=expected_etag)
    #     expected_full_local_path = FAKE.file_path()
    #     downloader = self.create_gcp_downloader_with_mocked_values()
    #     with patch.object(downloader, "_bucket_info") as mock_bucket_info, patch.object(
    #         downloader, "_get_local_file_path"
    #     ) as mock_get_local_path:
    #         mock_bucket_info.get_blob.return_value = mock_blob
    #         mock_get_local_path.return_value = expected_full_local_path
    #         results = downloader.download_file(key)
    #         mock_bucket_info.get_blob.assert_called_with(key)
    #     mock_blob.download_to_filename.assert_called_with(expected_full_local_path)
    #     mock_makedirs.assert_called()
    #     self.assertEqual(results, (expected_full_local_path, expected_etag))

    # @patch("masu.external.downloader.gcp.gcp_report_downloader.os.makedirs")
    # def test_download_file_with_mismatched_etag(self, mock_makedirs):
    #     """
    #     Assert download_file downloads and returns local path with GCP's etag.

    #     This is basically identical to test_download_file_without_etag's behavior,
    #     but this behavior may change in the future if we decide to introduce some
    #     kind of alternate flow or error handling when the remote blog's etag does
    #     not match our stored etag.
    #     """
    #     key = FAKE.file_path()
    #     stored_etag = FAKE.slug()
    #     expected_etag = FAKE.slug()
    #     self.assertNotEqual(stored_etag, expected_etag)
    #     mock_blob = MockBlob(etag=expected_etag)
    #     expected_full_local_path = FAKE.file_path()
    #     downloader = self.create_gcp_downloader_with_mocked_values()
    #     with patch.object(downloader, "_bucket_info") as mock_bucket_info, patch.object(
    #         downloader, "_get_local_file_path"
    #     ) as mock_get_local_path:
    #         mock_bucket_info.get_blob.return_value = mock_blob
    #         mock_get_local_path.return_value = expected_full_local_path
    #         results = downloader.download_file(key, stored_etag)
    #         mock_bucket_info.get_blob.assert_called_with(key)
    #     mock_blob.download_to_filename.assert_called_with(expected_full_local_path)
    #     mock_makedirs.assert_called()
    #     self.assertEqual(results, (expected_full_local_path, expected_etag))

    # def test_get_local_directory_path(self):
    #     """Assert expected local directory path construction."""
    #     customer_name = "Bilbo/Baggins"
    #     bucket_name = "Bag/End"
    #     data_dir = "/The/Shire"
    #     expected_directory_path = "/The/Shire/Bilbo_Baggins/gcp/Bag_End"
    #     downloader = self.create_gcp_downloader_with_mocked_values(
    #         customer_name=customer_name, bucket_name=bucket_name
    #     )
    #     with patch("masu.external.downloader.gcp.gcp_report_downloader.DATA_DIR", new=data_dir):
    #         actual_directory_path = downloader._get_local_directory_path()
    #     self.assertEqual(actual_directory_path, expected_directory_path)

    # def test_get_local_file_path(self):
    #     """Assert expected local file path construction."""
    #     directory_path = FAKE.file_path()
    #     key = "Samwise/Gamgee"
    #     expected_file_name = "Samwise_Gamgee"
    #     downloader = self.create_gcp_downloader_with_mock_gcp_storage()
    #     actual_local_file_path = downloader._get_local_file_path(directory_path, key)
    #     self.assertTrue(actual_local_file_path.startswith(directory_path))
    #     self.assertTrue(actual_local_file_path.endswith(expected_file_name))
    #     self.assertNotIn(key, actual_local_file_path)

    # def test_get_manifest_context_for_date_with_files(self):
    #     """Assert get_report_context_for_date returns a "report" dict if files are found."""
    #     start_date = datetime(2019, 9, 1)
    #     assembly_id = FAKE.uuid4()
    #     file_count = 10
    #     file_names = [FAKE.file_name() for _ in range(file_count)]
    #     manifest = {
    #         "assembly_id": assembly_id,
    #         "start_date": start_date,
    #         "compression": UNCOMPRESSED,
    #         "file_names": file_names,
    #     }
    #     manifest_id = FAKE.pyint()
    #     downloader = self.create_gcp_downloader_with_mock_gcp_storage()
    #     with patch.object(downloader, "_generate_monthly_pseudo_manifest") as mock_generate_manifest, patch.object(
    #         downloader, "_get_existing_manifest_db_id"
    #     ) as mock_get_manifest, patch.object(downloader, "_process_manifest_db_record") as mock_process:
    #         mock_generate_manifest.return_value = manifest
    #         mock_process.return_value = manifest_id

    #         result = downloader.get_manifest_context_for_date(start_date)
    #         mock_generate_manifest.assert_called_with(start_date)
    #         mock_get_manifest.assert_not_called()
    #         mock_process.assert_called_with(assembly_id, start_date, file_count)

    #     self.assertEqual(result.get("assembly_id"), assembly_id)
    #     self.assertEqual(result.get("compression"), UNCOMPRESSED)
    #     self.assertIsNotNone(result.get("files"))

    # def test_get_report_context_for_date_empty_if_already_processed(self):
    #     """Assert get_report_context_for_date creates returns {} if already processed."""
    #     start_date = Mock()
    #     downloader = self.create_gcp_downloader_with_mock_gcp_storage()
    #     with patch.object(downloader, "_generate_monthly_pseudo_manifest") as mock_generate_manifest:
    #         result = downloader.get_manifest_context_for_date(start_date)
    #         mock_generate_manifest.assert_called_with(start_date)
    #     self.assertEqual(result, {})
