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
from unittest.mock import Mock
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
        """Set up the test class."""
        super().setUpClass()
        cls.fake = Faker()
        cls.patch_path = True
        cls.date_accessor = DateAccessor()
        cls.assembly_id = cls.fake.pystr()
        cls.report_name = f"{cls.assembly_id}_file_1.csv.gz"

    def setUp(self):
        """Set up each test case."""
        super().setUp()
        self.mock_task = Mock(request=Mock(id=str(self.fake.uuid4()), return_value={}))
        self.downloader = ReportDownloaderBase(task=self.mock_task, provider_uuid=self.aws_provider_uuid)
        billing_start = self.date_accessor.today_with_timezone("UTC").replace(day=1)
        self.task_id = str(self.fake.uuid4())
        self.manifest_dict = {
            "assembly_id": self.assembly_id,
            "billing_period_start_datetime": billing_start,
            "num_total_files": 2,
            "provider_uuid": self.aws_provider_uuid,
            "task": self.task_id,
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

    @patch("masu.external.downloader.report_downloader_base.app")
    def test_report_downloader_base_no_path(self, _):
        """Test report downloader download_path."""
        downloader = ReportDownloaderBase(self.mock_task)
        self.assertIsInstance(downloader, ReportDownloaderBase)
        self.assertIsNotNone(downloader.download_path)
        self.assertTrue(os.path.exists(downloader.download_path))

    @patch("masu.external.downloader.report_downloader_base.app")
    def test_report_downloader_base(self, _):
        """Test download path matches expected."""
        dl_path = "/{}/{}/{}".format(self.fake.word().lower(), self.fake.word().lower(), self.fake.word().lower())
        downloader = ReportDownloaderBase(self.mock_task, download_path=dl_path)
        self.assertEqual(downloader.download_path, dl_path)

    @patch("masu.external.downloader.report_downloader_base.app")
    def test_get_existing_manifest_db_id(self, _):
        """Test that a manifest ID is returned."""
        manifest_id = self.downloader._get_existing_manifest_db_id(self.assembly_id)
        self.assertEqual(manifest_id, self.manifest_id)

    @patch("masu.external.downloader.report_downloader_base.app")
    def test_check_if_manifest_should_be_downloaded_new_manifest(self, _):
        """Test that a new manifest should be processed."""
        result = self.downloader.check_if_manifest_should_be_downloaded("1234")
        self.assertTrue(result)

    @patch("masu.external.downloader.report_downloader_base.app")
    def test_check_if_manifest_should_be_downloaded_currently_processing_manifest(self, _):
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

    @patch("masu.external.downloader.report_downloader_base.app")
    def test_check_if_manifest_should_be_downloaded_error_processing_manifest(self, _):
        """Test that a manifest that did not succeessfully process should be reprocessed."""
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest_by_id(self.manifest_id)
            manifest.num_processed_files = 1
            manifest.num_total_files = 2
            manifest.save()

        with ReportStatsDBAccessor(self.report_name, self.manifest_id) as file_accessor:
            file_accessor.log_last_started_datetime()
            file_accessor.log_last_completed_datetime()
            completed_datetime = self.date_accessor.today_with_timezone("UTC") - datetime.timedelta(hours=1)
            file_accessor.update(last_completed_datetime=completed_datetime)
        result = self.downloader.check_if_manifest_should_be_downloaded(self.assembly_id)
        self.assertTrue(result)

    @patch("masu.external.downloader.report_downloader_base.app")
    def test_check_if_manifest_should_be_downloaded_done_processing_manifest(self, _):
        """Test that a manifest that has finished processing is not reprocessed."""
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest_by_id(self.manifest_id)
            manifest.num_processed_files = 2
            manifest.num_total_files = 2
            manifest.save()

        result = self.downloader.check_if_manifest_should_be_downloaded(self.assembly_id)
        self.assertFalse(result)

    @patch("masu.external.downloader.report_downloader_base.app")
    def test_check_task_queues_false(self, mock_celery):
        """Test that check_task_queues() returns false when task_id is absent."""
        # app.control.inspect()
        mock_celery.control = Mock(
            inspect=Mock(
                return_value=Mock(
                    active=Mock(return_value={}), reserved=Mock(return_value={}), scheduled=Mock(return_value={})
                )
            )
        )
        result = self.downloader.check_task_queues(self.manifest_id)
        self.assertFalse(result)

    @patch("masu.external.downloader.report_downloader_base.app")
    def test_check_task_queues_true(self, mock_celery):
        """Test that check_task_queues() returns true when task_id is found."""
        # app.control.inspect()
        active = Mock(return_value={self.fake.word(): [{"id": self.task_id}]})
        mock_celery.control = Mock(
            inspect=Mock(
                return_value=Mock(active=active, reserved=Mock(return_value={}), scheduled=Mock(return_value={}))
            )
        )
        result = self.downloader.check_task_queues(self.task_id)
        self.assertTrue(result)

    @patch("masu.external.downloader.report_downloader_base.app")
    def test_check_if_manifest_should_be_downloaded_error_no_complete_date(self, _):
        """Test that a manifest that did not succeessfully process should be reprocessed."""
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest_by_id(self.manifest_id)
            manifest.num_processed_files = 1
            manifest.num_total_files = 2
            manifest.save()

        with ReportStatsDBAccessor(self.report_name, self.manifest_id) as file_accessor:
            file_accessor.log_last_started_datetime()
        result = self.downloader.check_if_manifest_should_be_downloaded(self.assembly_id)
        self.assertTrue(result)
