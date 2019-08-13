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
"""Test the report downloader base class."""

import datetime
import os.path
from unittest.mock import patch

from faker import Faker

from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from masu.test import MasuTestCase


class ReportDownloaderBaseTest(MasuTestCase):
    """Test Cases for ReportDownloaderBase."""

    fake = Faker()
    patch_path = True

    @classmethod
    def setUpClass(cls):
        """Setup the test class."""
        super().setUpClass()
        cls.fake = Faker()
        cls.patch_path = True
        cls.date_accessor = DateAccessor()
        cls.assembly_id = cls.fake.pystr()
        cls.report_name = f'{cls.assembly_id}_file_1.csv.gz'

    def setUp(self):
        """Setup each test case."""
        super().setUp()
        self.downloader = ReportDownloaderBase(provider_id=self.aws_provider_id)
        billing_start = self.date_accessor.today_with_timezone('UTC').replace(day=1)
        self.manifest_dict = {
            'assembly_id': self.assembly_id,
            'billing_period_start_datetime': billing_start,
            'num_total_files': 2,
            'provider_id': self.aws_provider_id
        }
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.add(**self.manifest_dict)
            manifest.save()
            self.manifest_id = manifest.id

    def tearDown(self):
        """Tear down each test case."""
        super().tearDown()
        with ReportStatsDBAccessor(self.report_name, self.manifest_id) as file_accessor:
            files = file_accessor._get_db_obj_query().all()
            for file in files:
                file_accessor.delete(file)

        with ReportManifestDBAccessor() as manifest_accessor:
            manifests = manifest_accessor._get_db_obj_query().all()
            for manifest in manifests:
                manifest_accessor.delete(manifest)

    def test_report_downloader_base_no_path(self):
        downloader = ReportDownloaderBase()
        self.assertIsInstance(downloader, ReportDownloaderBase)
        self.assertIsNotNone(downloader.download_path)
        self.assertTrue(os.path.exists(downloader.download_path))

    def test_report_downloader_base(self):
        dl_path = '/{}/{}/{}'.format(
            self.fake.word().lower(), self.fake.word().lower(), self.fake.word().lower()
        )
        downloader = ReportDownloaderBase(download_path=dl_path)
        self.assertEqual(downloader.download_path, dl_path)

    def test_get_existing_manifest_db_id(self):
        """Test that a manifest ID is returned."""

        manifest_id = self.downloader._get_existing_manifest_db_id(self.assembly_id)
        self.assertEqual(manifest_id, self.manifest_id)

    def test_check_if_manifest_should_be_downloaded_new_manifest(self):
        """Test that a new manifest should be processed."""
        result = self.downloader.check_if_manifest_should_be_downloaded('1234')
        self.assertTrue(result)

    def test_check_if_manifest_should_be_downloaded_currently_processing_manifest(self):
        """Test that a manifest being processed should not be reprocessed."""
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest_by_id(self.manifest_id)
            manifest.num_processed_files = 1
            manifest.num_total_files = 2
            manifest.save()

        with ReportStatsDBAccessor(self.report_name, self.manifest_id) as file_accessor:
            file_accessor.log_last_started_datetime()
            file_accessor.log_last_completed_datetime()

        result = self.downloader.check_if_manifest_should_be_downloaded(self.assembly_id)
        self.assertFalse(result)

    def test_check_if_manifest_should_be_downloaded_error_processing_manifest(self):
        """Test that a manifest that did not succeessfully process should be reprocessed."""
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest_by_id(self.manifest_id)
            manifest.num_processed_files = 1
            manifest.num_total_files = 2
            manifest.save()

        with ReportStatsDBAccessor(self.report_name, self.manifest_id) as file_accessor:
            file_accessor.log_last_started_datetime()
            file_accessor.log_last_completed_datetime()
            completed_datetime = self.date_accessor.today_with_timezone('UTC') - datetime.timedelta(hours=1)
            file_accessor.update(last_completed_datetime=completed_datetime)
        result = self.downloader.check_if_manifest_should_be_downloaded(self.assembly_id)
        self.assertTrue(result)

    def test_check_if_manifest_should_be_downloaded_done_processing_manifest(self):
        """Test that a manifest that has finished processing is not reprocessed."""
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest_by_id(self.manifest_id)
            manifest.num_processed_files = 2
            manifest.num_total_files = 2
            manifest.save()

        result = self.downloader.check_if_manifest_should_be_downloaded(self.assembly_id)
        self.assertFalse(result)
