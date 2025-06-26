#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AzureReportDownloader object."""
import json
import os.path
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import Mock
from unittest.mock import patch

from azure.core.exceptions import HttpResponseError
from faker import Faker

from api.utils import DateHelper
from masu.config import Config
from masu.external import UNCOMPRESSED
from masu.external.downloader.azure.azure_report_downloader import AzureReportDownloader
from masu.external.downloader.azure.azure_report_downloader import AzureReportDownloaderError
from masu.external.downloader.azure.azure_report_downloader import create_daily_archives
from masu.external.downloader.azure.azure_report_downloader import get_processing_date
from masu.external.downloader.azure.azure_service import AzureCostReportNotFound
from masu.test import MasuTestCase
from masu.util import common as utils
from masu.util.azure.common import AzureBlobExtension
from reporting_common.models import CostUsageReportManifest

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
        self.export_file = f"{self.export_name}_{self.export_uuid}.csv.gz"
        self.manifest_file = f"{self.export_name}_{self.export_uuid}.json"
        self.export_etag = "absdfwef"
        self.ingress_report = f"custom_ingress_report_{self.export_uuid}.csv.gz"
        self.last_modified = DateHelper().now
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

    def get_latest_cost_export_for_path(self, report_path, container_name, compression=None):
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
            message = f"No cost report found in container {container_name} for path {report_path}."
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
            size = 123456

        class Export:
            name = self.ingress_report
            last_modified = self.last_modified
            size = 123456

        if key == self.ingress_report:
            mock_export = Export()
        elif key == self.export_key:
            mock_export = ExportProperties()
        else:
            message = f"No cost report for report name {key} found in container {container_name}."
            raise AzureCostReportNotFound(message)
        return mock_export

    def download_file(
        self,
        key,
        container_name,
        destination=None,
        suffix=AzureBlobExtension.csv.value,
        ingress_reports=None,
        offset=None,
        length=None,
        compression=None,
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

        if offset is not None and length is not None:
            return file_contents[suffix][offset : offset + length]

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
        self.azure_manifest = CostUsageReportManifest.objects.filter(provider_id=self.azure_provider_uuid).first()
        self.azure_manifest_id = self.azure_manifest.id

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
        self.assertEqual(manifest.get("Compression"), None)
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
        self.assertEqual(manifest.get("Compression"), None)
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

    @patch("masu.external.downloader.azure.azure_report_downloader.create_daily_archives")
    @patch("masu.external.downloader.azure.azure_report_downloader.open")
    def test_download_file(self, mock_open, mock_daily_archives):
        """Test that Azure report is downloaded."""
        mock_daily_archives.return_value = [["file_one", "file_two"], {"start": "", "end": ""}]

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

    @patch("masu.external.downloader.azure.azure_report_downloader.AzureService")
    def test_download_ingress_report_file(self, mock_azure_service):
        """Test the download file method for Azure ingress report."""
        customer_name = self.customer_name
        file_key = self.ingress_reports[0].split(f"{self.mock_data.container}/", 1)[1]

        expected_full_path = "{}/{}/azure/{}/{}".format(
            Config.TMP_DIR, customer_name.replace(" ", "_"), self.mock_data.container, file_key
        )

        downloader = AzureReportDownloader(
            customer_name,
            self.azure_credentials,
            self.storage_only_data_source,
            ingress_reports=self.ingress_reports,
        )

        with patch("masu.external.downloader.azure.azure_report_downloader.open"):
            with patch(
                "masu.external.downloader.azure.azure_report_downloader.create_daily_archives",
                return_value=[["file_one", "file_two"], {"start": "", "end": ""}],
            ):
                full_file_path, etag, _, __, ___ = downloader.download_file(file_key)
                self.assertEqual(full_file_path, expected_full_path)

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

        current_month = self.dh.this_month_start

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
            self.dh.now,
        )
        result = self.downloader.get_manifest_context_for_date(current_month)
        self.assertEqual(result.get("assembly_id"), assembly_id)
        self.assertEqual(result.get("compression"), compression)
        self.assertIsNotNone(result.get("files"))

    @patch("masu.external.downloader.azure.azure_report_downloader.copy_local_report_file_to_s3_bucket")
    def test_create_daily_archives_alt_columns(self, mock_copy):
        """Test that we correctly create daily archive files with alt columns."""
        file = "azure_version_2"
        file_name = f"{file}.csv"
        file_path = f"./koku/masu/test/data/azure/{file_name}"
        manifest_id = self.azure_manifest_id
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, file_name)
        shutil.copy2(file_path, temp_path)
        expected_daily_files = [
            f"{temp_dir}/2020-09-01_manifestid-{manifest_id}_basefile-{file}_batch-0.csv",
            f"{temp_dir}/2020-09-10_manifestid-{manifest_id}_basefile-{file}_batch-0.csv",
            f"{temp_dir}/2020-09-11_manifestid-{manifest_id}_basefile-{file}_batch-0.csv",
            f"{temp_dir}/2020-09-22_manifestid-{manifest_id}_basefile-{file}_batch-0.csv",
        ]
        start_date = self.dh.this_month_start.replace(year=2020, month=9)
        with patch(
            "masu.database.report_manifest_db_accessor.ReportManifestDBAccessor.set_manifest_daily_start_date",
            return_value=start_date,
        ):
            daily_file_names, date_range = create_daily_archives(
                "trace_id", "account", self.azure_provider_uuid, temp_path, file, manifest_id, start_date, None
            )
            expected_date_range = {"start": "2020-09-01", "end": "2020-09-22", "invoice_month": None}
            mock_copy.assert_called()
            self.assertEqual(date_range, expected_date_range)
            self.assertIsInstance(daily_file_names, list)
            self.assertEqual(sorted(daily_file_names), sorted(expected_daily_files))
            for daily_file in expected_daily_files:
                self.assertTrue(os.path.exists(daily_file))
                os.remove(daily_file)
            os.remove(temp_path)

    @patch("masu.external.downloader.azure.azure_report_downloader.copy_local_report_file_to_s3_bucket")
    def test_create_daily_archives(self, mock_copy):
        """Test that we correctly create daily archive files."""
        file = "costreport_a243c6f2-199f-4074-9a2c-40e671cf1584"
        file_name = f"{file}.csv"
        file_path = f"./koku/masu/test/data/azure/{file_name}"
        manifest_id = self.azure_manifest_id
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, file_name)
        shutil.copy2(file_path, temp_path)
        start_date = self.dh.this_month_start.replace(year=2019, month=7)
        with patch(
            "masu.database.report_manifest_db_accessor.ReportManifestDBAccessor.set_manifest_daily_start_date",
            return_value=start_date,
        ):
            create_daily_archives(
                "trace_id", "account", self.azure_provider_uuid, temp_path, file, manifest_id, start_date, None
            )
            mock_copy.assert_not_called()

    @patch("masu.external.downloader.azure.azure_report_downloader.copy_local_report_file_to_s3_bucket")
    def test_create_daily_archives_check_leading_zeros(self, mock_copy):
        """Check that the leading zeros are kept when downloading."""
        file = "costreport_a243c6f2-199f-4074-9a2c-40e671cf1584"
        file_name = f"{file}.csv"
        manifest_id = self.azure_manifest_id
        file_path = f"./koku/masu/test/data/azure/{file_name}"
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, file_name)
        shutil.copy2(file_path, temp_path)
        start_date = self.dh.this_month_start.replace(year=2023, month=6)

        with patch(
            "masu.database.report_manifest_db_accessor.ReportManifestDBAccessor.set_manifest_daily_start_date",
            return_value=start_date,
        ):
            daily_file_names, date_range = create_daily_archives(
                "trace_id", "account", self.aws_provider_uuid, temp_path, file_name, manifest_id, start_date, None
            )

        for daily_file in daily_file_names:
            with open(daily_file) as file:
                csv = file.readlines()

            self.assertIn("0039de71-ca37-4a17-a104-17665a50e7fc", csv[1].split(","))
            self.assertIn("0fc067a1-65d2-46da-b24b-7a9cbe2c69bd", csv[1].split(","))
            os.remove(daily_file)

        os.remove(temp_path)

    @patch("masu.external.downloader.azure.azure_report_downloader.copy_local_report_file_to_s3_bucket")
    def test_create_daily_archives_dates_out_of_range(self, mock_copy):
        """Test that we correctly create daily archive files."""
        file = "costreport_a243c6f2-199f-4074-9a2c-40e671cf1584"
        file_name = f"{file}.csv"
        file_path = f"./koku/masu/test/data/azure/{file_name}"
        manifest_id = self.azure_manifest_id
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, file_name)
        shutil.copy2(file_path, temp_path)
        expected_daily_files = []
        start_date = self.dh.this_month_start.replace(year=2020, month=7)
        daily_file_names, date_range = create_daily_archives(
            "trace_id", "account", self.azure_provider_uuid, temp_path, file, manifest_id, start_date, None
        )
        expected_date_range = {}
        self.assertEqual(date_range, expected_date_range)
        self.assertIsInstance(daily_file_names, list)
        self.assertEqual(daily_file_names, expected_daily_files)

    def test_create_daily_archives_empty_frames(self):
        """Test that we correctly create daily archive files."""
        file = "empty_frame"
        file_name = f"{file}.csv"
        file_path = f"./koku/masu/test/data/azure/{file_name}"
        manifest_id = self.azure_manifest_id
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, file_name)
        shutil.copy2(file_path, temp_path)
        expected_daily_files = []
        start_date = self.dh.this_month_start.replace(year=2020, month=7)
        daily_file_names, date_range = create_daily_archives(
            "trace_id", "account", self.azure_provider_uuid, temp_path, file, manifest_id, start_date, None
        )
        expected_date_range = {}
        self.assertEqual(date_range, expected_date_range)
        self.assertIsInstance(daily_file_names, list)
        self.assertEqual(sorted(daily_file_names), sorted(expected_daily_files))

    @patch(
        "masu.database.report_manifest_db_accessor.ReportManifestDBAccessor.get_manifest_daily_start_date",
        return_value=None,
    )
    @patch("masu.external.downloader.azure.azure_report_downloader.get_or_clear_daily_s3_by_date")
    @patch("masu.database.report_manifest_db_accessor.ReportManifestDBAccessor.set_manifest_daily_start_date")
    def test_get_processing_date(self, mock_set_start, mock_daily_start, mock_manifest_start):
        """Test getting dataframe with date for processing."""
        file_name = "costreport_a243c6f2-199f-4074-9a2c-40e671cf1584.csv"
        file_path = f"./koku/masu/test/data/azure/{file_name}"
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, file_name)
        shutil.copy2(file_path, temp_path)
        start_date = self.dh.this_month_start.replace(year=2123, month=12)
        end_date = self.dh.this_month_start.replace(year=2123, month=12, day=2)
        expected_date = self.dh.this_month_start.replace(year=2123, month=12, day=1)
        mock_daily_start.return_value = expected_date
        with patch(
            "masu.external.downloader.azure.azure_report_downloader.check_provider_setup_complete", return_Value=True
        ):
            process_date = get_processing_date(
                temp_path, 1, self.azure_provider_uuid, start_date, end_date, None, "tracing_id"
            )
            mock_daily_start.assert_called()
            self.assertEqual(process_date, expected_date)
            os.remove(temp_path)

    @patch("masu.util.aws.common.get_s3_resource")
    def test_get_processing_date_alt_columns(self, mock_resource):
        """Test getting dataframe with date for processing."""
        file_name = "camel_azure_version_2.csv"
        file_path = f"./koku/masu/test/data/azure/{file_name}"
        context = {"account": self.schema_name, "provider_type": self.azure_provider.type}
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, file_name)
        shutil.copy2(file_path, temp_path)
        start_date = self.dh.this_month_start.replace(year=2023, month=9)
        end_date = self.dh.this_month_start.replace(year=2023, month=9, day=2)
        expected_date = self.dh.this_month_start.replace(year=2023, month=9, day=1).date()
        with patch(
            "masu.external.downloader.azure.azure_report_downloader.check_provider_setup_complete", return_Value=True
        ):
            with patch("masu.util.aws.common.get_or_clear_daily_s3_by_date", return_value=expected_date):
                with patch(
                    "masu.database.report_manifest_db_accessor.ReportManifestDBAccessor.get_manifest_daily_start_date",
                    return_value=expected_date,
                ):
                    process_date = get_processing_date(
                        temp_path, 1, self.azure_provider_uuid, start_date, end_date, context, "tracing_id"
                    )
                    self.assertEqual(process_date, expected_date)
                    os.remove(temp_path)

    @patch("masu.external.downloader.azure.azure_report_downloader.AzureService")
    def test_download_file_raise_downloader_err(self, mock_azure_service):
        """Test download_file fails with HttpResponseError when there is an unexpected error."""
        fake_azure_client = Mock()
        fake_response = HttpResponseError("Unexpected error")
        fake_azure_client.get_file_for_key.side_effect = fake_response

        downloader = AzureReportDownloader("fake_customer", {}, {"storage_account": "fake_account"})
        downloader._azure_client = fake_azure_client

        with self.assertRaises(HttpResponseError) as context:
            downloader.download_file("problematic_file.csv")

        self.assertIn("Unexpected error", str(context.exception))

    @patch("masu.external.downloader.azure.azure_service.AzureClientFactory")
    @patch("masu.external.downloader.azure.azure_service.AzureService.get_file_for_key")
    @patch("masu.external.downloader.azure.azure_report_downloader.utils.get_local_file_name")
    @patch("masu.external.downloader.azure.azure_service.AzureService.download_file")
    @patch("masu.external.downloader.azure.azure_report_downloader.AzureReportDownloader._get_exports_data_directory")
    @patch("masu.external.downloader.azure.azure_report_downloader.create_daily_archives")
    def test_download_file_success(
        self,
        mock_create_daily_archives,
        mock_get_exports_data_directory,
        mock_download_file,
        mock_get_local_file_name,
        mock_get_file_for_key,
        mock_client_factory,
    ):
        """Tests if the file download is successful when there is enough disk space."""
        mock_get_exports_data_directory.return_value = "/fake_path"
        mock_get_local_file_name.return_value = "fake_local_file.csv"
        mock_get_file_for_key.return_value = Mock(etag="fake_etag", last_modified="2024-09-27")
        mock_create_daily_archives.return_value = (["fake_file.csv"], {"start": "2024-09-01", "end": "2024-09-27"})

        service = AzureReportDownloader(
            customer_name="fake_customer", credentials={}, data_source={"storage_account": "fake_storage_account"}
        )

        full_file_path, etag, file_creation_date, file_names, date_range = service.download_file("fake_key")

        self.assertEqual(full_file_path, "/fake_path/fake_local_file.csv")
        self.assertEqual(etag, "fake_etag")
        self.assertEqual(file_creation_date, "2024-09-27")

        mock_download_file.assert_called_once_with(
            "fake_key",
            service.container_name,
            destination="/fake_path/fake_local_file.csv",
            ingress_reports=service.ingress_reports,
            suffix=None,
        )

    @patch("masu.external.downloader.azure.azure_service.AzureClientFactory")
    @patch("masu.external.downloader.azure.azure_service.AzureService.get_file_for_key")
    def test_download_file_blob_not_found(self, mock_get_file_for_key, mock_client_factory):
        """Tests if an exception is raised when the blob is not found."""
        mock_get_file_for_key.side_effect = AzureCostReportNotFound("Blob not found")

        mock_client_factory.return_value = Mock()

        service = AzureReportDownloader(
            customer_name="fake_customer", credentials={}, data_source={"storage_account": "fake_storage_account"}
        )

        with self.assertRaises(AzureReportDownloaderError) as context:
            service.download_file("fake_key")

        self.assertIn("Error when downloading Azure report for key", str(context.exception))
