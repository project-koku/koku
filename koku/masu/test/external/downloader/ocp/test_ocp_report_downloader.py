#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

"""Test the Report Downloader."""

import os
import os.path
import shutil
from shutil import copyfile
import tempfile

from faker import Faker

from datetime import datetime
from unittest.mock import patch
from masu.config import Config
from masu.external.date_accessor import DateAccessor
from masu.external.report_downloader import ReportDownloader
from masu.external.downloader.ocp.ocp_report_downloader import OCPReportDownloader
from masu.test import MasuTestCase

DATA_DIR = Config.TMP_DIR
REPORTS_DIR = Config.INSIGHTS_LOCAL_REPORT_DIR

FAKE = Faker()
CUSTOMER_NAME = FAKE.word()


class OCPReportDownloaderTest(MasuTestCase):
    """Test Cases for the OCP Report Downloader."""

    fake = Faker()

    def setUp(self):
        super().setUp()
        self.fake_customer_name = CUSTOMER_NAME
        self.fake_report_name = 'ocp-report'
        self.cluster_id = 'my-ocp-cluster-1'

        report_path = '{}/{}/{}'.format(
            REPORTS_DIR, self.cluster_id, '20180901-20181001'
        )
        os.makedirs(report_path, exist_ok=True)

        test_file_path = './koku/masu/test/data/ocp/e6b3701e-1e91-433b-b238-a31e49937558_February-2019-my-ocp-cluster-1.csv'
        self.test_file_path = os.path.join(
            report_path, os.path.basename(test_file_path)
        )
        shutil.copyfile(test_file_path, os.path.join(report_path, self.test_file_path))

        test_manifest_path = './koku/masu/test/data/ocp/manifest.json'
        self.test_manifest_path = os.path.join(
            report_path, os.path.basename(test_manifest_path)
        )
        shutil.copyfile(
            test_manifest_path, os.path.join(report_path, self.test_manifest_path)
        )

        self.report_downloader = ReportDownloader(
            self.fake_customer_name, self.cluster_id, None, 'OCP', self.ocp_provider_id
        )

        self.ocp_report_downloader = OCPReportDownloader(
            **{
                'customer_name': self.fake_customer_name,
                'auth_credential': self.cluster_id,
                'bucket': None,
                'provider_id': 1,
            }
        )

    def tearDown(self):
        super().tearDown()
        shutil.rmtree(REPORTS_DIR, ignore_errors=True)

    def test_download_bucket(self):
        """Test to verify that basic report downloading works."""
        test_report_date = datetime(year=2018, month=9, day=7)
        with patch.object(DateAccessor, 'today', return_value=test_report_date):
            self.report_downloader.download_report(test_report_date)
        expected_path = '{}/{}/{}'.format(
            Config.TMP_DIR, self.fake_customer_name, 'ocp'
        )
        self.assertTrue(os.path.isdir(expected_path))

    def test_download_bucket_no_csv_found(self):
        """Test to verify that basic report downloading with no .csv file in source directory."""
        reports = []
        test_report_date = datetime(year=2018, month=9, day=7)
        with patch.object(DateAccessor, 'today', return_value=test_report_date):
            os.remove(self.test_file_path)
            reports = self.report_downloader.download_report(test_report_date)
        self.assertEqual(reports, [])

    def test_download_bucket_non_csv_found(self):
        """Test to verify that basic report downloading with non .csv file in source directory."""
        reports = []
        test_report_date = datetime(year=2018, month=9, day=7)
        with patch.object(DateAccessor, 'today', return_value=test_report_date):
            # Remove .csv
            os.remove(self.test_file_path)

            # Create .txt file
            txt_file_path = '{}/{}'.format(
                os.path.dirname(self.test_file_path), 'report.txt'
            )
            open(txt_file_path, 'a').close()

            reports = self.report_downloader.download_report(test_report_date)
        self.assertEqual(reports, [])

    def test_download_bucket_source_directory_missing(self):
        """Test to verify that basic report downloading when source directory doesn't exist."""
        reports = []
        # Set current date to a day that is outside of the test file's date range.
        test_report_date = datetime(year=2018, month=10, day=7)
        with patch.object(DateAccessor, 'today', return_value=test_report_date):
            reports = self.report_downloader.download_report(test_report_date)
        self.assertEqual(reports, [])
