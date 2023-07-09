#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Report Downloader."""
import logging
import os.path
import shutil
import tempfile
from datetime import datetime
from unittest.mock import patch

import pandas as pd
from faker import Faker

from api.models import Provider
from api.utils import DateHelper
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.external.downloader.ocp.ocp_report_downloader import create_daily_archives
from masu.external.downloader.ocp.ocp_report_downloader import divide_csv_daily
from masu.external.downloader.ocp.ocp_report_downloader import OCPReportDownloader
from masu.external.report_downloader import ReportDownloader
from masu.test import MasuTestCase
from reporting_common.models import CostUsageReportManifest

DATA_DIR = Config.TMP_DIR
REPORTS_DIR = Config.INSIGHTS_LOCAL_REPORT_DIR

FAKE = Faker()
CUSTOMER_NAME = FAKE.word()


class OCPReportDownloaderTest(MasuTestCase):
    """Test Cases for the OCP Report Downloader."""

    fake = Faker()

    def setUp(self):
        """Set up each test."""
        super().setUp()
        self.fake_customer_name = CUSTOMER_NAME
        self.fake_report_name = "ocp-report"
        self.cluster_id = "my-ocp-cluster-1"
        self.credentials = {"cluster_id": self.cluster_id}

        report_path = "{}/{}/{}".format(REPORTS_DIR, self.cluster_id, "20180901-20181001")
        os.makedirs(report_path, exist_ok=True)

        test_file_path = (
            "./koku/masu/test/data/ocp/e6b3701e-1e91" "-433b-b238-a31e49937558_February-2019-my-ocp-cluster-1.csv"
        )
        self.test_file_path = os.path.join(report_path, os.path.basename(test_file_path))
        shutil.copyfile(test_file_path, os.path.join(report_path, self.test_file_path))

        test_storage_file_path = "./koku/masu/test/data/ocp/e6b3701e-1e91" "-433b-b238-a31e49937558_storage.csv"
        self.test_storage_file_path = os.path.join(report_path, os.path.basename(test_storage_file_path))
        shutil.copyfile(test_file_path, os.path.join(report_path, self.test_storage_file_path))

        test_manifest_path = "./koku/masu/test/data/ocp/manifest.json"
        self.test_manifest_path = os.path.join(report_path, os.path.basename(test_manifest_path))
        shutil.copyfile(test_manifest_path, os.path.join(report_path, self.test_manifest_path))

        self.report_downloader = ReportDownloader(
            customer_name=self.fake_customer_name,
            credentials=self.credentials,
            data_source={},
            provider_type=Provider.PROVIDER_OCP,
            provider_uuid=self.ocp_provider_uuid,
        )

        self.ocp_report_downloader = OCPReportDownloader(
            **{
                "customer_name": self.fake_customer_name,
                "credentials": self.credentials,
                "data_source": {},
                "provider_uuid": self.ocp_provider_uuid,
            }
        )
        self.ocp_manifest = CostUsageReportManifest.objects.filter(cluster_id__isnull=True).first()
        self.ocp_manifest_id = self.ocp_manifest.id

    def tearDown(self):
        """Remove created test data."""
        super().tearDown()
        shutil.rmtree(REPORTS_DIR, ignore_errors=True)

    @patch("masu.util.aws.common.copy_data_to_s3_bucket", return_value=None)
    def test_download_bucket(self, mock_copys3):
        """Test to verify that basic report downloading works."""
        test_report_date = datetime(year=2018, month=9, day=7)
        with patch.object(DateAccessor, "today", return_value=test_report_date):
            report_context = {
                "date": test_report_date.date(),
                "manifest_id": 1,
                "comporession": "GZIP",
                "current_file": self.test_file_path,
            }
            self.report_downloader.download_report(report_context)
        expected_path = "{}/{}/{}".format(Config.TMP_DIR, self.fake_customer_name, "ocp")
        self.assertTrue(os.path.isdir(expected_path))

    def test_download_bucket_no_csv_found(self):
        """Test to verify that basic report downloading with no .csv file in source directory."""
        test_report_date = datetime(year=2018, month=9, day=7)
        with patch.object(DateAccessor, "today", return_value=test_report_date):
            os.remove(self.test_file_path)
            os.remove(self.test_storage_file_path)
            with self.assertRaises(FileNotFoundError):
                report_context = {
                    "date": test_report_date.date(),
                    "manifest_id": 1,
                    "comporession": "GZIP",
                    "current_file": self.test_file_path,
                }
                self.report_downloader.download_report(report_context)

    def test_download_bucket_non_csv_found(self):
        """Test to verify that basic report downloading with non .csv file in source directory."""
        test_report_date = datetime(year=2018, month=9, day=7)
        with patch.object(DateAccessor, "today", return_value=test_report_date):
            # Remove .csv
            os.remove(self.test_file_path)
            os.remove(self.test_storage_file_path)

            # Create .txt file
            txt_file_path = "{}/{}".format(os.path.dirname(self.test_file_path), "report.txt")
            open(txt_file_path, "a").close()
            with self.assertRaises(FileNotFoundError):
                report_context = {
                    "date": test_report_date.date(),
                    "manifest_id": 1,
                    "comporession": "GZIP",
                    "current_file": self.test_file_path,
                }
                self.report_downloader.download_report(report_context)

    def test_remove_manifest_file(self):
        """Test that a manifest file is deleted after use."""
        test_report_date = datetime(year=2018, month=9, day=7)
        self.assertTrue(os.path.isfile(self.test_manifest_path))
        self.ocp_report_downloader._remove_manifest_file(test_report_date)
        self.assertFalse(os.path.isfile(self.test_manifest_path))

    def test_delete_manifest_file_warning(self):
        """Test that an INFO is logged when removing a manifest file that does not exist."""
        with self.assertLogs(
            logger="masu.external.downloader.ocp.ocp_report_downloader", level="INFO"
        ) as captured_logs:
            # Disable log suppression
            logging.disable(logging.NOTSET)
            self.ocp_report_downloader._remove_manifest_file(datetime.now())
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

    def test_divide_csv_daily(self):
        """Test the divide_csv_daily method."""

        with tempfile.TemporaryDirectory() as td:
            filename = "storage_data.csv"
            file_path = f"{td}/{filename}"
            with patch("masu.external.downloader.ocp.ocp_report_downloader.pd") as mock_pd:
                with patch(
                    "masu.external.downloader.ocp.ocp_report_downloader.utils.detect_type",
                    return_value=("storage_usage", None),
                ):
                    dates = ["2020-01-01 00:00:00 +UTC", "2020-01-02 00:00:00 +UTC"]
                    mock_report = {
                        "interval_start": dates,
                        "persistentvolumeclaim_labels": ["label1", "label2"],
                    }
                    df = pd.DataFrame(data=mock_report)
                    mock_pd.read_csv.return_value = df
                    manifest = ReportManifestDBAccessor().get_manifest_by_id(self.ocp_manifest_id)
                    daily_files = divide_csv_daily(file_path, manifest)
                    self.assertNotEqual([], daily_files)
                    self.assertEqual(len(daily_files), 2)
                    gen_files = ["storage_usage.2020-01-01_0.csv", "storage_usage.2020-01-02_0.csv"]
                    expected_dates = [datetime.strptime(date[:10], "%Y-%m-%d") for date in dates]
                    expected = [
                        {"filename": gen_file, "filepath": f"{td}/{gen_file}", "date": expected_dates[i]}
                        for i, gen_file in enumerate(gen_files)
                    ]
                    for expected_item in expected:
                        self.assertIn(expected_item, daily_files)

    def test_divide_csv_daily_failure(self):
        """Test the divide_csv_daily method throw error on reading CSV."""

        with tempfile.TemporaryDirectory() as td:
            filename = "storage_data.csv"
            file_path = f"{td}/{filename}"
            errorMsg = "CParserError: Error tokenizing data. C error: Expected 53 fields in line 1605634, saw 54"
            with patch("masu.external.downloader.ocp.ocp_report_downloader.pd") as mock_pd:
                with patch(
                    "masu.external.downloader.ocp.ocp_report_downloader.utils.detect_type",
                    return_value=("storage_usage", None),
                ):
                    mock_pd.read_csv.side_effect = Exception(errorMsg)
                    with patch("masu.external.downloader.ocp.ocp_report_downloader.LOG.error") as mock_debug:
                        with self.assertRaises(Exception):
                            manifest = ReportManifestDBAccessor().get_manifest_by_id(self.ocp_manifest_id)
                            divide_csv_daily(file_path, manifest)
                        mock_debug.assert_called_once_with(f"File {file_path} could not be parsed. Reason: {errorMsg}")

    @patch("masu.external.downloader.ocp.ocp_report_downloader.OCPReportDownloader._remove_manifest_file")
    @patch("masu.external.downloader.ocp.ocp_report_downloader.utils.get_report_details")
    def test_get_manifest_context_for_date(self, mock_manifest, mock_delete):
        """Test that the manifest is read."""
        current_month = DateAccessor().today().replace(day=1, second=1, microsecond=1)

        assembly_id = "1234"
        compression = "PLAIN"
        report_keys = ["file1", "file2"]
        version = "5678"
        mock_manifest.return_value = {
            "uuid": assembly_id,
            "Compression": compression,
            "reportKeys": report_keys,
            "date": current_month,
            "files": report_keys,
            "version": version,
        }
        result = self.ocp_report_downloader.get_manifest_context_for_date(current_month)
        self.assertEqual(result.get("assembly_id"), assembly_id)
        self.assertEqual(result.get("compression"), compression)
        self.assertIsNotNone(result.get("files"))

        manifest_id = result.get("manifest_id")
        manifest = ReportManifestDBAccessor().get_manifest_by_id(manifest_id)
        self.assertEqual(manifest.operator_version, version)

    @patch("masu.external.downloader.ocp.ocp_report_downloader.OCPReportDownloader._remove_manifest_file")
    @patch("masu.external.downloader.ocp.ocp_report_downloader.utils.get_report_details")
    def test_get_manifest_context_new_info(self, mock_manifest, mock_delete):
        """Test that the manifest is read."""
        current_month = DateAccessor().today().replace(day=1, second=1, microsecond=1)

        assembly_id = "1234"
        compression = "PLAIN"
        report_keys = ["file1", "file2"]
        version = "5678"
        mock_manifest.return_value = {
            "uuid": assembly_id,
            "Compression": compression,
            "reportKeys": report_keys,
            "date": current_month,
            "files": report_keys,
            "version": version,
            "certified": False,
            "cluster_id": "4e009161-4f40-42c8-877c-3e59f6baea3d",
            "cr_status": {
                "clusterID": "4e009161-4f40-42c8-877c-3e59f6baea3d",
                "clusterVersion": "stable-4.6",
                "api_url": "https://cloud.redhat.com",
                "authentication": {"type": "token"},
                "packaging": {"max_reports_to_store": 30, "max_size_MB": 100},
                "upload": {"ingress_path": "/api/ingress/v1/upload", "upload": False},
                "operator_commit": "a09a5b21e55ce4a07fe31aa560650b538ec6de7c",
                "prometheus": {"error": "fake error"},
                "reports": {"report_month": "07", "last_hour_queried": "2021-07-28 11:00:00 - 2021-07-28 11:59:59"},
                "source": {"sources_path": "/api/sources/v1.0/", "name": "INSERT-SOURCE-NAME"},
            },
        }
        result = self.ocp_report_downloader.get_manifest_context_for_date(current_month)
        self.assertEqual(result.get("assembly_id"), assembly_id)
        self.assertEqual(result.get("compression"), compression)
        self.assertIsNotNone(result.get("files"))

        manifest_id = result.get("manifest_id")
        manifest = ReportManifestDBAccessor().get_manifest_by_id(manifest_id)
        expected_errors = {"prometheus_error": "fake error"}
        self.assertEqual(manifest.operator_version, version)
        self.assertEqual(manifest.operator_certified, False)
        self.assertEqual(manifest.operator_airgapped, True)
        self.assertEqual(manifest.cluster_channel, "stable-4.6")
        self.assertEqual(manifest.cluster_id, "4e009161-4f40-42c8-877c-3e59f6baea3d")
        self.assertEqual(manifest.operator_errors, expected_errors)

    @patch("masu.external.downloader.ocp.ocp_report_downloader.os")
    @patch("masu.external.downloader.ocp.ocp_report_downloader.copy_local_report_file_to_s3_bucket")
    @patch("masu.external.downloader.ocp.ocp_report_downloader.divide_csv_daily")
    def test_create_daily_archives_very_old_operator(self, mock_divide, *args):
        """Test that this method returns a file list."""
        # modify the manifest to remove the operator version to test really old operators:
        self.ocp_manifest.operator_version = None
        self.ocp_manifest.save()

        start_date = DateHelper().this_month_start
        daily_files = [
            {"filename": "file_one", "filepath": "path/to/file_one", "date": datetime.fromisoformat("2020-01-01")},
            {"filename": "file_two", "filepath": "path/to/file_two", "date": datetime.fromisoformat("2020-01-01")},
        ]
        expected_filenames = ["path/to/file_one", "path/to/file_two"]

        mock_divide.return_value = daily_files

        file_name = "file"
        file_path = "path"
        result = create_daily_archives(
            1, "10001", self.ocp_provider_uuid, file_name, file_path, self.ocp_manifest_id, start_date
        )

        self.assertEqual(result, expected_filenames)

    @patch("masu.external.downloader.ocp.ocp_report_downloader.os")
    @patch("masu.external.downloader.ocp.ocp_report_downloader.copy_local_report_file_to_s3_bucket")
    def test_create_daily_archives_non_daily_operator_files(self, *args):
        """Test that this method returns a file list."""
        start_date = DateHelper().this_month_start

        file_path = "path"

        context = {"version": "1"}
        expected = [file_path]
        result = create_daily_archives(
            1, "10001", self.ocp_provider_uuid, "file", "path", self.ocp_manifest_id, start_date, context=context
        )
        self.assertEqual(result, expected)

    @patch("masu.external.downloader.ocp.ocp_report_downloader.os")
    @patch("masu.external.downloader.ocp.ocp_report_downloader.copy_local_report_file_to_s3_bucket")
    @patch("masu.external.downloader.ocp.ocp_report_downloader.divide_csv_daily")
    def test_create_daily_archives_daily_operator_files(self, mock_divide, *args):
        """Test that this method returns a file list."""
        self.ocp_manifest.operator_daily_reports = True
        self.ocp_manifest.save()

        start_date = DateHelper().this_month_start
        daily_files = [
            {"filename": "file_one", "filepath": "path/to/file_one", "date": datetime.fromisoformat("2020-01-01")},
            {"filename": "file_two", "filepath": "path/to/file_two", "date": datetime.fromisoformat("2020-01-01")},
        ]
        expected_filenames = ["path/to/file_one", "path/to/file_two"]

        mock_divide.return_value = daily_files

        file_name = "file"
        file_path = "path"
        result = create_daily_archives(
            1, "10001", self.ocp_provider_uuid, file_name, file_path, self.ocp_manifest_id, start_date
        )

        self.assertEqual(result, expected_filenames)
