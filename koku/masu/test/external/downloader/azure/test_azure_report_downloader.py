#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AzureReportDownloader object."""
import json
import shutil
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import Mock
from unittest.mock import patch

from faker import Faker

from masu.config import Config
from masu.external import UNCOMPRESSED
from masu.external.date_accessor import DateAccessor
from masu.external.downloader.azure.azure_report_downloader import AzureReportDownloader
from masu.external.downloader.azure.azure_report_downloader import AzureReportDownloaderError
from masu.external.downloader.azure.azure_service import AzureCostReportNotFound
from masu.test import MasuTestCase
from masu.util import common as utils
from masu.util.azure.common import AzureBlobExtension


DATA_DIR = Config.TMP_DIR


class MockAzureService:
    """Mock an azure service."""

    def __init__(self):
        """Initialize a mocked azure service."""
        self.export_name = "costreport"
        self.container = "test_container"
        self.directory = "cost"
        self.test_date = datetime(2019, 8, 15)
        self.month_range = utils.month_date_range(self.test_date)
        self.report_path = f"{self.directory}/{self.export_name}/{self.month_range}"
        self.export_uuid = "9c308505-61d3-487c-a1bb-017956c9170a"
        self.export_file = f"{self.export_name}_{self.export_uuid}.csv"
        self.manifest_file = f"{self.export_name}_{self.export_uuid}.json"
        self.export_etag = "absdfwef"
        self.ingress_report = f"custom_ingress_report_{self.export_uuid}.csv"
        self.last_modified = DateAccessor().today()
        self.export_key = f"{self.report_path}/{self.export_file}"

        self.bad_test_date = datetime(2019, 7, 15)
        self.bad_month_range = utils.month_date_range(self.bad_test_date)
        self.bad_report_path = f"{self.directory}/{self.export_name}/{self.bad_month_range}"

        self.manifest_test_date = datetime(2020, 4, 2)
        self.manifest_month_range = utils.month_date_range(self.manifest_test_date)
        self.manifest_report_path = f"{self.directory}/{self.export_name}/{self.manifest_month_range}"

    def describe_cost_management_exports(self):
        """Describe cost management exports."""
        return [{"name": self.export_name, "container": self.container, "directory": self.directory}]

    def get_latest_cost_export_for_path(self, report_path, container_name):
        """Get exports for path."""

        class BadExport:
            name = self.export_name
            last_modified = self.last_modified

        class Export:
            name = self.export_file
            last_modified = self.last_modified

        if report_path == self.report_path:
            mock_export = Export()
        elif report_path == self.bad_report_path:
            mock_export = BadExport()
        else:
            message = f"No cost report found in container {container_name} for " f"path {report_path}."
            raise AzureCostReportNotFound(message)
        return mock_export

    def get_latest_manifest_for_path(self, report_path: str, container_name: str):
        if report_path != self.manifest_report_path:
            raise AzureCostReportNotFound

        class Manifest:
            name = self.manifest_file
            last_modified = self.manifest_test_date

        return Manifest()

    def get_file_for_key(self, key, container_name):
        """Get exports for key."""

        class ExportProperties:
            etag = self.export_etag
            last_modified = self.last_modified

        class Export:
            name = self.ingress_report
            last_modified = self.last_modified

        if key == self.ingress_report:
            mock_export = Export()
        elif key == self.export_key:
            mock_export = ExportProperties()
        else:
            message = f"No cost report for report name {key} found in container {container_name}."
            raise AzureCostReportNotFound(message)
        return mock_export

    def download_file(
        self, key, container_name, destination=None, suffix=AzureBlobExtension.csv.value, ingress_reports=None
    ):
        """Get exports."""
        file_path = destination
        file_contents = {
            AzureBlobExtension.json.value: Path(__file__).parent.joinpath("fixtures", "manifest.json").read_bytes(),
            AzureBlobExtension.csv.value: b"csvcontents",
        }
        if not destination:
            with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(file_contents[suffix])
                file_path = temp_file.name

        return file_path


class AzureReportDownloaderTest(MasuTestCase):
    """Test Cases for the AzureReportDownloader object."""

    fake = Faker()

    @patch("masu.external.downloader.azure.azure_report_downloader.AzureService")
    def setUp(self, mock_service):
        """Set up each test."""
        mock_service.return_value = MockAzureService()

        super().setUp()
        self.mock_data = MockAzureService()
        self.customer_name = "Azure Customer"
        self.ingress_reports = [f"{self.mock_data.container}/{self.mock_data.ingress_report}"]
        self.azure_credentials = self.azure_provider.authentication.credentials
        self.azure_data_source = self.azure_provider.billing_source.data_source
        self.storage_only_data_source = {
            "resource_group": "group-test",
            "storage_account": "account-test",
            "storage_only": True,
        }

        self.downloader = AzureReportDownloader(
            customer_name=self.customer_name,
            credentials=self.azure_credentials,
            data_source=self.azure_data_source,
            provider_uuid=self.azure_provider_uuid,
        )
        self.ingress_downloader = AzureReportDownloader(
            customer_name=self.customer_name,
            credentials=self.azure_credentials,
            data_source=self.azure_data_source,
            provider_uuid=self.azure_provider_uuid,
            ingress_reports=self.ingress_reports,
        )
        self.storage_only_downloader = AzureReportDownloader(
            customer_name=self.customer_name,
            credentials=self.azure_credentials,
            data_source=self.storage_only_data_source,
            provider_uuid=self.azure_provider_uuid,
            ingress_reports=None,
        )

    def tearDown(self):
        """Remove created test data."""
        super().tearDown()
        shutil.rmtree(DATA_DIR, ignore_errors=True)

    @patch("masu.external.downloader.azure.azure_report_downloader.AzureService", return_value=MockAzureService())
    def test_get_azure_client(self, _):
        """Test to verify Azure downloader is initialized."""
        client = self.downloader._get_azure_client(self.azure_credentials, self.azure_data_source)
        self.assertIsNotNone(client)

    def test_get_report_path(self):
        """Test that report path is built correctly."""
        self.assertEqual(self.downloader.directory, self.mock_data.directory)
        self.assertEqual(self.downloader.export_name, self.mock_data.export_name)

        self.assertEqual(self.downloader._get_report_path(self.mock_data.test_date), self.mock_data.report_path)

    def test_get_local_file_for_report(self):
        """Test to get the local file path for a report."""
        expected_local_file = self.mock_data.export_file
        local_file = self.downloader.get_local_file_for_report(self.mock_data.export_key)
        self.assertEqual(expected_local_file, local_file)

    @patch("masu.external.downloader.azure.azure_report_downloader.LOG")
    def test_storage_only_initial_ingest_skip(self, mock_log):
        """Test that Azure storage only without ingress report skips inital ingest."""
        report_dict = self.storage_only_downloader.get_manifest_context_for_date(self.mock_data.test_date)
        self.assertEqual(report_dict, {})
        call_arg = mock_log.info.call_args.args[0]
        self.assertTrue("Skipping ingest as source is storage_only and requires ingress reports" in call_arg)

    def test_get_ingress_manifest(self):
        """Test that Azure ingress manifest is created."""
        expected_start, expected_end = self.mock_data.month_range.split("-")
        manifest, _ = self.ingress_downloader._get_manifest(self.mock_data.test_date)

        self.assertEqual(manifest.get("reportKeys"), [self.mock_data.ingress_report])
        self.assertEqual(manifest.get("Compression"), "PLAIN")
        self.assertEqual(manifest.get("billingPeriod").get("start"), expected_start)
        self.assertEqual(manifest.get("billingPeriod").get("end"), expected_end)

    @patch("masu.external.downloader.azure.azure_report_downloader.LOG")
    def test_get_ingress_report_error(self, mock_log):
        """Test that Azure get_bob errors correctly."""
        self.ingress_downloader.tracing_id = "1111-2222-4444-5555"
        self.ingress_downloader._azure_client.get_file_for_key = Mock(side_effect=AzureCostReportNotFound("Oops!"))
        manifest, last_modified = self.ingress_downloader._get_manifest(self.mock_data.test_date)
        self.assertEqual(manifest, {})
        self.assertEqual(last_modified, None)
        call_arg = mock_log.info.call_args.args[0]
        self.assertEqual(call_arg.get("tracing_id"), self.ingress_downloader.tracing_id)
        self.assertTrue("Unable to find report." in call_arg.get("message"))

    def test_get_manifest(self):
        """Test that Azure manifest is created."""
        expected_start, expected_end = self.mock_data.month_range.split("-")

        manifest, _ = self.downloader._get_manifest(self.mock_data.test_date)

        self.assertEqual(manifest.get("assemblyId"), self.mock_data.export_uuid)
        self.assertEqual(manifest.get("reportKeys"), [self.mock_data.export_file])
        self.assertEqual(manifest.get("Compression"), "PLAIN")
        self.assertEqual(manifest.get("billingPeriod").get("start"), expected_start)
        self.assertEqual(manifest.get("billingPeriod").get("end"), expected_end)

    def test_get_manifest_unexpected_report_name(self):
        """Test that error is thrown when getting manifest with an unexpected report name."""
        with self.assertRaises(AzureReportDownloaderError):
            self.downloader._get_manifest(self.mock_data.bad_test_date)

    @patch("masu.external.downloader.azure.azure_report_downloader.AzureService", new_callable=MockAzureService)
    def test_get_manifest_json_manifest(self, mock_azure_service):
        self.downloader._get_manifest(self.mock_data.manifest_test_date)

    @patch.object(MockAzureService, "download_file", side_effect=AzureReportDownloaderError)
    @patch("masu.external.downloader.azure.azure_report_downloader.AzureService", new_callable=MockAzureService)
    def test_get_manifest_json_manifest_not_found(self, mock_azure_service, mock_download_file):
        result = self.downloader._get_manifest(self.mock_data.manifest_test_date)

        self.assertEqual(result, ({}, None))

    def test_get_manifest_bad_json(self):
        with patch(
            "masu.external.downloader.azure.azure_report_downloader.json.load",
            side_effect=json.JSONDecodeError("Raised intentionally", "doc", 42),
        ):
            with self.assertRaisesRegex(AzureReportDownloaderError, "Raised intentionally"):
                self.downloader._get_manifest(self.mock_data.manifest_test_date)

    @patch("masu.external.downloader.azure.azure_report_downloader.LOG")
    def test_get_manifest_report_not_found(self, log_mock):
        """Test that Azure report is throwing an exception if the report was not found."""
        self.downloader.tracing_id = "1111-2222-4444-5555"
        self.downloader._azure_client.get_latest_cost_export_for_path = Mock(
            side_effect=AzureCostReportNotFound("Oops!")
        )
        manifest, last_modified = self.downloader._get_manifest(self.mock_data.test_date)
        self.assertEqual(manifest, {})
        self.assertEqual(last_modified, None)
        call_arg = log_mock.info.call_args.args[0]
        self.assertEqual(call_arg.get("tracing_id"), self.downloader.tracing_id)
        self.assertTrue("Unable to find manifest" in call_arg.get("message"))

    def test_remove_manifest_file_error(self):
        with (
            patch(
                "masu.external.downloader.azure.azure_report_downloader.os.unlink", side_effect=OSError
            ) as unlink_mock,
            patch(
                "masu.external.downloader.azure.azure_report_downloader.LOG.info",
                side_effect=AttributeError("Raised intentionally"),
            ) as log_mock,
        ):
            with self.assertRaisesRegex(AttributeError, "Raised intentionally"):
                self.downloader._remove_manifest_file("/not/a/file")

        unlink_mock.assert_called_once_with("/not/a/file")
        self.assertTrue("Could not delete manifest file" in log_mock.call_args[0][0]["message"])

    def test_download_file(self):
        """Test that Azure report is downloaded."""
        expected_full_path = "{}/{}/azure/{}/{}".format(
            Config.TMP_DIR, self.customer_name.replace(" ", "_"), self.mock_data.container, self.mock_data.export_file
        )
        full_file_path, etag, _, __, ___ = self.downloader.download_file(self.mock_data.export_key)
        self.assertEqual(full_file_path, expected_full_path)
        self.assertEqual(etag, self.mock_data.export_etag)

    def test_download_missing_file(self):
        """Test that Azure report is not downloaded for incorrect key."""
        key = "badkey"

        with self.assertRaises(AzureReportDownloaderError):
            self.downloader.download_file(key)

    def test_download_ingress_report_file(self):
        """Test that Azure ingress report is downloaded."""
        expected_full_path = "{}/{}/azure/{}".format(
            Config.TMP_DIR, self.customer_name.replace(" ", "_"), self.ingress_reports[0]
        )
        full_file_path, etag, _, __, ___ = self.ingress_downloader.download_file(self.ingress_reports[0])
        self.assertEqual(full_file_path, expected_full_path)

    @patch("masu.external.downloader.azure.azure_report_downloader.AzureReportDownloader")
    def test_download_file_matching_etag(self, mock_download_cost_method):
        """Test that Azure report is not downloaded with matching etag."""
        expected_full_path = "{}/{}/azure/{}/{}".format(
            Config.TMP_DIR, self.customer_name.replace(" ", "_"), self.mock_data.container, self.mock_data.export_file
        )
        full_file_path, etag, _, __, ___ = self.downloader.download_file(
            self.mock_data.export_key, self.mock_data.export_etag
        )
        self.assertEqual(full_file_path, expected_full_path)
        self.assertEqual(etag, self.mock_data.export_etag)
        mock_download_cost_method._azure_client.download_cost_export.assert_not_called()

    @patch("masu.external.downloader.azure.azure_report_downloader.AzureReportDownloader")
    @patch("masu.external.downloader.azure.azure_report_downloader.AzureService", return_value=MockAzureService())
    def test_init_with_demo_account(self, mock_download_cost_method, _):
        """Test init with the demo account."""
        account_id = "123456"
        report_name = self.fake.word()
        client_id = self.azure_credentials.get("client_id")
        demo_accounts = {
            account_id: {
                client_id: {
                    "report_name": report_name,
                    "report_prefix": self.fake.word(),
                    "container_name": self.fake.word(),
                }
            }
        }
        with self.settings(DEMO_ACCOUNTS=demo_accounts):
            AzureReportDownloader(
                customer_name=f"acct{account_id}",
                credentials=self.azure_credentials,
                data_source=self.azure_data_source,
                provider_uuid=self.azure_provider_uuid,
            )
            mock_download_cost_method._azure_client.download_cost_export.assert_not_called()

    @patch("masu.external.downloader.azure.azure_report_downloader.AzureReportDownloader._get_manifest")
    def test_get_manifest_context_for_date(self, mock_manifest):
        """Test that the manifest is read."""

        current_month = DateAccessor().today().replace(day=1, second=1, microsecond=1)

        start_str = current_month.strftime(self.downloader.manifest_date_format)
        assembly_id = "1234"
        compression = UNCOMPRESSED
        report_keys = ["file1", "file2"]
        mock_manifest.return_value = (
            {
                "assemblyId": assembly_id,
                "Compression": compression,
                "reportKeys": report_keys,
                "billingPeriod": {"start": start_str},
            },
            DateAccessor().today(),
        )
        result = self.downloader.get_manifest_context_for_date(current_month)
        self.assertEqual(result.get("assembly_id"), assembly_id)
        self.assertEqual(result.get("compression"), compression)
        self.assertIsNotNone(result.get("files"))
