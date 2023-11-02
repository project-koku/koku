#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Report Downloader."""
import os.path
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from faker import Faker

from api.utils import DateHelper
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.downloader.ocp.ocp_report_downloader import create_daily_archives
from masu.external.downloader.ocp.ocp_report_downloader import divide_csv_daily
from masu.test import MasuTestCase
from reporting_common.models import CostUsageReportManifest

DATA_DIR = Config.TMP_DIR
REPORTS_DIR = Config.INSIGHTS_LOCAL_REPORT_DIR

FAKE = Faker()
CUSTOMER_NAME = FAKE.word()

FILE_PATH_ONE = Path("path/to/file_one")
FILE_PATH_TWO = Path("path/to/file_two")


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

        report_path = f"{REPORTS_DIR}/{self.cluster_id}/20180901-20181001"
        os.makedirs(report_path, exist_ok=True)

        self.test_filename = "e6b3701e-1e91-433b-b238-a31e49937558_February-2019-my-ocp-cluster-1.csv"
        test_file_path = f"./koku/masu/test/data/ocp/{self.test_filename}"
        self.test_file_path = os.path.join(report_path, os.path.basename(test_file_path))
        shutil.copyfile(test_file_path, os.path.join(report_path, self.test_file_path))

        test_storage_file_path = "./koku/masu/test/data/ocp/e6b3701e-1e91-433b-b238-a31e49937558_storage.csv"
        self.test_storage_file_path = os.path.join(report_path, os.path.basename(test_storage_file_path))
        shutil.copyfile(test_file_path, os.path.join(report_path, self.test_storage_file_path))

        test_manifest_path = "./koku/masu/test/data/ocp/manifest.json"
        self.test_manifest_path = os.path.join(report_path, os.path.basename(test_manifest_path))
        shutil.copyfile(test_manifest_path, os.path.join(report_path, self.test_manifest_path))

        self.ocp_manifest = CostUsageReportManifest.objects.filter(cluster_id__isnull=True).first()
        self.ocp_manifest_id = self.ocp_manifest.id

    def tearDown(self):
        """Remove created test data."""
        super().tearDown()
        shutil.rmtree(REPORTS_DIR, ignore_errors=True)

    def test_divide_csv_daily(self):
        """Test the divide_csv_daily method."""
        with tempfile.TemporaryDirectory() as td:
            filename = "storage_data.csv"
            file_path = Path(td, filename)
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
                    daily_files = divide_csv_daily(file_path, self.ocp_manifest_id)
                    self.assertNotEqual([], daily_files)
                    self.assertEqual(len(daily_files), 2)
                    gen_files = [
                        f"storage_usage.2020-01-01.{self.ocp_manifest_id}.0.csv",
                        f"storage_usage.2020-01-02.{self.ocp_manifest_id}.0.csv",
                    ]
                    expected_dates = [datetime.strptime(date[:10], "%Y-%m-%d") for date in dates]
                    expected = [
                        {"filepath": Path(td, gen_file), "date": expected_dates[i], "num_hours": 1}
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
            {"filepath": FILE_PATH_ONE, "date": datetime.fromisoformat("2020-01-01"), "num_hours": 1},
            {"filepath": FILE_PATH_TWO, "date": datetime.fromisoformat("2020-01-01"), "num_hours": 1},
        ]
        expected_filenames = [FILE_PATH_ONE, FILE_PATH_TWO]

        mock_divide.return_value = daily_files

        file_path = Path("path")
        result = create_daily_archives(1, "10001", self.ocp_provider_uuid, file_path, self.ocp_manifest_id, start_date)

        self.assertCountEqual(result.keys(), expected_filenames)

    @patch("masu.external.downloader.ocp.ocp_report_downloader.os")
    @patch("masu.external.downloader.ocp.ocp_report_downloader.copy_local_report_file_to_s3_bucket")
    def test_create_daily_archives_non_daily_operator_files(self, *args):
        """Test that this method returns a file list."""
        start_date = DateHelper().this_month_start

        file_path = Path("path")

        context = {"version": "1"}
        expected = [file_path]
        result = create_daily_archives(
            1, "10001", self.ocp_provider_uuid, file_path, self.ocp_manifest_id, start_date, context=context
        )
        self.assertCountEqual(result.keys(), expected)

    @patch("masu.external.downloader.ocp.ocp_report_downloader.os")
    @patch("masu.external.downloader.ocp.ocp_report_downloader.copy_local_report_file_to_s3_bucket")
    @patch("masu.external.downloader.ocp.ocp_report_downloader.divide_csv_daily")
    def test_create_daily_archives_daily_operator_files(self, mock_divide, *args):
        """Test that this method returns a file list."""
        self.ocp_manifest.operator_daily_reports = True
        self.ocp_manifest.save()

        start_date = DateHelper().this_month_start
        daily_files = [
            {"filepath": FILE_PATH_ONE, "date": datetime.fromisoformat("2020-01-01"), "num_hours": 23},
            {"filepath": FILE_PATH_TWO, "date": datetime.fromisoformat("2020-01-02"), "num_hours": 24},
        ]
        expected_filenames = [FILE_PATH_ONE, FILE_PATH_TWO]
        expected_result = {
            FILE_PATH_ONE: {"meta_reportdatestart": "2020-01-01", "meta_reportnumhours": "23"},
            FILE_PATH_TWO: {"meta_reportdatestart": "2020-01-02", "meta_reportnumhours": "24"},
        }

        mock_divide.return_value = daily_files

        file_path = Path("path")
        result = create_daily_archives(1, "10001", self.ocp_provider_uuid, file_path, self.ocp_manifest_id, start_date)

        self.assertCountEqual(result.keys(), expected_filenames)
        self.assertDictEqual(result, expected_result)

    @patch("masu.external.downloader.ocp.ocp_report_downloader.os")
    @patch("masu.external.downloader.ocp.ocp_report_downloader.copy_local_report_file_to_s3_bucket")
    @patch("masu.external.downloader.ocp.ocp_report_downloader.divide_csv_daily")
    def test_create_daily_archives_daily_operator_files_empty_file(self, mock_divide, *args):
        """Test that this method returns a file list."""
        self.ocp_manifest.operator_daily_reports = True
        self.ocp_manifest.save()

        start_date = DateHelper().this_month_start

        # simulate empty report file
        mock_divide.return_value = None

        file_path = Path("path")
        expected_result = {
            file_path: {"meta_reportdatestart": str(start_date.date()), "meta_reportnumhours": "0"},
        }
        result = create_daily_archives(1, "10001", self.ocp_provider_uuid, file_path, self.ocp_manifest_id, start_date)

        self.assertCountEqual(result.keys(), [file_path])
        self.assertDictEqual(result, expected_result)
