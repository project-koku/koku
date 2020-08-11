"""Test the GCPReportDownloader class."""
import shutil
from datetime import datetime
from unittest.mock import Mock
from unittest.mock import patch
from uuid import uuid4

from faker import Faker
from rest_framework.exceptions import ValidationError

from masu.external import UNCOMPRESSED
from masu.external.downloader.gcp.gcp_report_downloader import DATA_DIR
from masu.external.downloader.gcp.gcp_report_downloader import GCPReportDownloader
from masu.external.downloader.gcp.gcp_report_downloader import GCPReportDownloaderError
from masu.external.downloader.gcp.gcp_report_downloader import GCPReportDownloaderNoFileError
from masu.test import MasuTestCase

FAKE = Faker()


class MockBlob(Mock):
    """Mock class to represent GCP file blobs."""

    def __init__(self, name=None, etag=None, *args, **kwargs):
        """Initialize the MockBlob."""
        super().__init__(*args, **kwargs)
        if name:
            self.name = name
        if etag:
            self.etag = etag


class GCPReportDownloaderTest(MasuTestCase):
    """Test Cases for the GCPReportDownloader object."""

    def tearDown(self):
        """Remove files and directories created during the test run."""
        super().tearDown()
        shutil.rmtree(DATA_DIR, ignore_errors=True)

    def create_gcp_downloader_with_mock_gcp_storage(
        self, customer_name=None, bucket_name=None, provider_uuid=None, report_prefix=None
    ):
        """
        Create a GCPReportDownloader instance that skips the initial GCP client/bucket check.

        This also results in Mock objects being set to instance variables that can be patched
        inside other test functions.

        Args:
            customer_name (str): optional customer name; will be randomly generated if None
            bucket_name (str): optional bucket name; will be randomly generated if None
            provider_uuid (uuid): optional provider UUID; will be randomly generated if None
            report_prefix (str): optional report prefix

        Returns:
            GCPReportDownloader instance with faked argument data and Mocks in
            self._storage_client and self._bucket_info.

        """
        if not customer_name:
            customer_name = FAKE.name()
        if not bucket_name:
            bucket_name = FAKE.slug()
        billing_source = {"bucket": bucket_name}
        if report_prefix:
            billing_source["report_prefix"] = report_prefix
        if not provider_uuid:
            provider_uuid = uuid4()
        with patch("masu.external.downloader.gcp.gcp_report_downloader.GCPProvider"), patch(
            "masu.external.downloader.gcp.gcp_report_downloader.storage"
        ):
            # mock_storage_client = mock_storage.Client.return_value
            # mock_storage_client.lookup_bucket.return_value = {}
            downloader = GCPReportDownloader(
                customer_name=customer_name, billing_source=billing_source, provider_uuid=provider_uuid
            )
        return downloader

    @patch("masu.external.downloader.gcp.gcp_report_downloader.GCPProvider")
    def test_init_unreachable_bucket_raises_error(self, mock_provider):
        """Assert GCPReportDownloader raises error when bucket is not reachable."""
        mock_provider.return_value.cost_usage_source_is_reachable.side_effect = ValidationError
        with self.assertRaises(GCPReportDownloaderError):
            GCPReportDownloader(FAKE.name(), {"bucket": FAKE.slug()})

    def test_init_reachable_bucket_is_okay(self):
        """Assert GCPReportDownloader initializes with expected values."""
        customer_name = FAKE.name()
        bucket_name = FAKE.slug()
        billing_source = {"bucket": bucket_name}
        with patch("masu.external.downloader.gcp.gcp_report_downloader.GCPProvider"), patch(
            "masu.external.downloader.gcp.gcp_report_downloader.storage"
        ) as mock_storage:
            downloader = GCPReportDownloader(customer_name, billing_source)
            mock_storage.Client.return_value.lookup_bucket.assert_called_with(bucket_name)
        self.assertEqual(downloader.customer_name, customer_name.replace(" ", "_"))
        self.assertEqual(downloader.bucket_name, bucket_name)

    def test_generate_monthly_pseudo_manifest(self):
        """Assert _generate_monthly_pseudo_manifest returns a manifest-like dict."""
        start_date = datetime(2019, 2, 1)
        expected_end_date = datetime(2019, 2, 28)
        fake_assembly_id = FAKE.slug()
        file_count = 10
        fake_file_names = [FAKE.file_name() for _ in range(file_count)]

        downloader = self.create_gcp_downloader_with_mock_gcp_storage()
        with patch.object(downloader, "_generate_assembly_id") as mock_generate_assembly_id, patch.object(
            downloader, "_get_relevant_file_names"
        ) as mock_get_names:
            mock_generate_assembly_id.return_value = fake_assembly_id
            mock_get_names.return_value = fake_file_names
            manifest = downloader._generate_monthly_pseudo_manifest(start_date)
            mock_generate_assembly_id.assert_called_with(start_date, expected_end_date, file_count)
        self.assertEqual(manifest["assembly_id"], fake_assembly_id)
        self.assertEqual(manifest["start_date"], start_date)
        self.assertEqual(manifest["end_date"], expected_end_date)
        self.assertListEqual(sorted(manifest["file_names"]), sorted(fake_file_names))

    def test_generate_assembly_id(self):
        """Assert appropriate generation of assembly ID."""
        start_date = datetime(2019, 2, 1)
        end_date = datetime(2019, 2, 28)
        provider_uuid = uuid4()
        file_count = 15
        expected_assembly_id = f"{provider_uuid}:2019-02-01:2019-02-28:15"

        downloader = self.create_gcp_downloader_with_mock_gcp_storage(provider_uuid=provider_uuid)
        assembly_id = downloader._generate_assembly_id(start_date, end_date, file_count)
        self.assertEqual(assembly_id, expected_assembly_id)

    def test_get_relevant_file_names_no_prefix(self):
        """
        Assert _get_relevant_file_names gets names and filters them by dates with no prefix.

        Note that the data here is specifically crafted to exercise boundary conditions.
        With the given dates, we expect only some of the files formatted with dates to
        be included in the results.
        """
        downloader = self.create_gcp_downloader_with_mock_gcp_storage()
        expected_relevant_names = ["2019-09-02.csv", "2019-09-03.csv"]
        irrelevant_names = [FAKE.file_path() for _ in range(10)] + [
            "2019-08-24.csv" "filthy-2019-08-25.csv",
            "sneaky-2019-09-01.tgz",
            "little-2019-09-02.xls",
            "hobbitses-2019-09-04.csv",
            "2019-09-05.csv",
            "whats-2019-08-31.csv",
            "2019-09-03/taters-2019-09-01.csv",
            "precious-2019-09-02.csv",
            "2019-09-25/2019-09-03.csv",
            "my-nicest-folder/2019-08-29.csv",
        ]
        all_found_names = sorted(expected_relevant_names + irrelevant_names)
        start_date = datetime(2019, 8, 28)  # chosen to exclude the older dates
        end_date = datetime(2019, 9, 3)  # chosen to exclude newer dates
        with patch.object(downloader, "_get_bucket_file_names") as mock_get_names:
            mock_get_names.return_value = all_found_names
            actual_names = downloader._get_relevant_file_names(start_date, end_date)
        self.assertListEqual(sorted(actual_names), sorted(expected_relevant_names))

    def test_get_relevant_file_names_prefix(self):
        """
        Assert _get_relevant_file_names gets names and filters them by dates with a prefix.

        Note that the data here is specifically crafted to exercise boundary conditions.
        With the given dates, we expect only some of the files formatted with dates to
        be included in the results.
        """
        downloader = self.create_gcp_downloader_with_mock_gcp_storage(report_prefix="precious")
        expected_relevant_names = ["precious-2019-08-28.csv", "precious-2019-09-01.csv", "precious-2019-09-02.csv"]
        irrelevant_names = [FAKE.file_path() for _ in range(10)] + [
            "2019-08-24.csv" "filthy-2019-08-25.csv",
            "sneaky-2019-09-01.tgz",
            "little-2019-09-02.xls",
            "hobbitses-2019-09-04.csv",
            "2019-09-02.csv",
            "2019-09-03",
            "2019-09-05.csv",
            "whats-2019-08-31.csv",
            "2019-09-03/taters-2019-09-01.csv",
            "2019-09-25/2019-09-03.csv",
            "my-nicest-folder/2019-08-29.csv",
            "very/precious-2019-09-02.csv",
        ]
        all_found_names = sorted(expected_relevant_names + irrelevant_names)
        start_date = datetime(2019, 8, 28)  # chosen to exclude the older dates
        end_date = datetime(2019, 9, 3)  # chosen to exclude newer dates
        with patch.object(downloader, "_get_bucket_file_names") as mock_get_names:
            mock_get_names.return_value = all_found_names
            actual_names = downloader._get_relevant_file_names(start_date, end_date)
        self.assertListEqual(sorted(actual_names), sorted(expected_relevant_names))

    def test_get_bucket_file_names(self):
        """Assert _get_bucket_file_names gets all blob names from the bucket."""
        expected_names = [FAKE.file_path() for _ in range(10)]  # arbitrary number of names
        mock_blobs = [MockBlob(name=name) for name in expected_names]

        downloader = self.create_gcp_downloader_with_mock_gcp_storage()
        with patch.object(downloader, "_bucket_info") as mock_bucket_info:
            mock_bucket_info.list_blobs.return_value = mock_blobs
            actual_names = downloader._get_bucket_file_names()
        self.assertListEqual(sorted(actual_names), sorted(expected_names))

    def test_get_local_file_for_report(self):
        """Assert that get_local_file_for_report is a simple pass-through."""
        downloader = self.create_gcp_downloader_with_mock_gcp_storage()
        report_name = FAKE.file_path()
        local_name = downloader.get_local_file_for_report(report_name)
        self.assertEqual(local_name, report_name)

    def test_download_file_raises_error_when_blob_not_found(self):
        """Assert download_file raises GCPReportDownloaderNoFileError when blob isn't found."""
        key = FAKE.file_path()
        downloader = self.create_gcp_downloader_with_mock_gcp_storage()
        with self.assertRaises(GCPReportDownloaderNoFileError), patch.object(
            downloader, "_bucket_info"
        ) as mock_bucket_info:
            mock_bucket_info.get_blob.return_value = None
            downloader.download_file(key)

    @patch("masu.external.downloader.gcp.gcp_report_downloader.os.makedirs")
    def test_download_file_without_etag(self, mock_makedirs):
        """Assert download_file downloads and returns local path with GCP's etag."""
        key = FAKE.file_path()
        expected_etag = FAKE.slug()
        mock_blob = MockBlob(etag=expected_etag)
        expected_full_local_path = FAKE.file_path()
        downloader = self.create_gcp_downloader_with_mock_gcp_storage()
        with patch.object(downloader, "_bucket_info") as mock_bucket_info, patch.object(
            downloader, "_get_local_file_path"
        ) as mock_get_local_path:
            mock_bucket_info.get_blob.return_value = mock_blob
            mock_get_local_path.return_value = expected_full_local_path
            results = downloader.download_file(key)
            mock_bucket_info.get_blob.assert_called_with(key)
        mock_blob.download_to_filename.assert_called_with(expected_full_local_path)
        mock_makedirs.assert_called()
        self.assertEqual(results, (expected_full_local_path, expected_etag))

    @patch("masu.external.downloader.gcp.gcp_report_downloader.os.makedirs")
    def test_download_file_with_mismatched_etag(self, mock_makedirs):
        """
        Assert download_file downloads and returns local path with GCP's etag.

        This is basically identical to test_download_file_without_etag's behavior,
        but this behavior may change in the future if we decide to introduce some
        kind of alternate flow or error handling when the remote blog's etag does
        not match our stored etag.
        """
        key = FAKE.file_path()
        stored_etag = FAKE.slug()
        expected_etag = FAKE.slug()
        self.assertNotEqual(stored_etag, expected_etag)
        mock_blob = MockBlob(etag=expected_etag)
        expected_full_local_path = FAKE.file_path()
        downloader = self.create_gcp_downloader_with_mock_gcp_storage()
        with patch.object(downloader, "_bucket_info") as mock_bucket_info, patch.object(
            downloader, "_get_local_file_path"
        ) as mock_get_local_path:
            mock_bucket_info.get_blob.return_value = mock_blob
            mock_get_local_path.return_value = expected_full_local_path
            results = downloader.download_file(key, stored_etag)
            mock_bucket_info.get_blob.assert_called_with(key)
        mock_blob.download_to_filename.assert_called_with(expected_full_local_path)
        mock_makedirs.assert_called()
        self.assertEqual(results, (expected_full_local_path, expected_etag))

    def test_get_local_directory_path(self):
        """Assert expected local directory path construction."""
        customer_name = "Bilbo/Baggins"
        bucket_name = "Bag/End"
        data_dir = "/The/Shire"
        expected_directory_path = "/The/Shire/Bilbo_Baggins/gcp/Bag_End"
        downloader = self.create_gcp_downloader_with_mock_gcp_storage(
            customer_name=customer_name, bucket_name=bucket_name
        )
        with patch("masu.external.downloader.gcp.gcp_report_downloader.DATA_DIR", new=data_dir):
            actual_directory_path = downloader._get_local_directory_path()
        self.assertEqual(actual_directory_path, expected_directory_path)

    def test_get_local_file_path(self):
        """Assert expected local file path construction."""
        directory_path = FAKE.file_path()
        key = "Samwise/Gamgee"
        expected_file_name = "Samwise_Gamgee"
        downloader = self.create_gcp_downloader_with_mock_gcp_storage()
        actual_local_file_path = downloader._get_local_file_path(directory_path, key)
        self.assertTrue(actual_local_file_path.startswith(directory_path))
        self.assertTrue(actual_local_file_path.endswith(expected_file_name))
        self.assertNotIn(key, actual_local_file_path)

    def test_get_manifest_context_for_date_with_files(self):
        """Assert get_report_context_for_date returns a "report" dict if files are found."""
        start_date = datetime(2019, 9, 1)
        assembly_id = FAKE.uuid4()
        file_count = 10
        file_names = [FAKE.file_name() for _ in range(file_count)]
        manifest = {
            "assembly_id": assembly_id,
            "start_date": start_date,
            "compression": UNCOMPRESSED,
            "file_names": file_names,
        }
        manifest_id = FAKE.pyint()
        downloader = self.create_gcp_downloader_with_mock_gcp_storage()
        with patch.object(downloader, "_generate_monthly_pseudo_manifest") as mock_generate_manifest, patch.object(
            downloader, "_get_existing_manifest_db_id"
        ) as mock_get_manifest, patch.object(downloader, "_process_manifest_db_record") as mock_process:
            mock_generate_manifest.return_value = manifest
            mock_process.return_value = manifest_id

            result = downloader.get_manifest_context_for_date(start_date)
            mock_generate_manifest.assert_called_with(start_date)
            mock_get_manifest.assert_not_called()
            mock_process.assert_called_with(assembly_id, start_date, file_count)

        self.assertEqual(result.get("assembly_id"), assembly_id)
        self.assertEqual(result.get("compression"), UNCOMPRESSED)
        self.assertIsNotNone(result.get("files"))

    def test_get_report_context_for_date_empty_if_already_processed(self):
        """Assert get_report_context_for_date creates returns {} if already processed."""
        start_date = Mock()
        downloader = self.create_gcp_downloader_with_mock_gcp_storage()
        with patch.object(downloader, "_generate_monthly_pseudo_manifest") as mock_generate_manifest:
            result = downloader.get_manifest_context_for_date(start_date)
            mock_generate_manifest.assert_called_with(start_date)
        self.assertEqual(result, {})
