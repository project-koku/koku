#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the report downloader base class."""
import os.path
from unittest.mock import patch

from django.db.utils import IntegrityError
from faker import Faker

from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from masu.external.downloader.report_downloader_base import ReportDownloaderError
from masu.test import MasuTestCase
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus


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
        self.cache_key = self.fake.word()
        self.downloader = ReportDownloaderBase(provider_uuid=self.aws_provider_uuid, cache_key=self.cache_key)
        self.billing_start = self.date_accessor.today_with_timezone("UTC").replace(day=1)
        self.manifest_dict = {
            "assembly_id": self.assembly_id,
            "billing_period_start_datetime": self.billing_start,
            "num_total_files": 2,
            "provider_uuid": self.aws_provider_uuid,
        }
        self.manifest = self.baker.make(
            CostUsageReportManifest,
            assembly_id=self.assembly_id,
            billing_period_start_datetime=self.billing_start,
            num_total_files=2,
            provider_id=self.aws_provider_uuid,
        )
        self.manifest_id = self.manifest.id
        for i in [1, 2]:
            self.baker.make(
                CostUsageReportStatus,
                report_name=f"{self.assembly_id}_file_{i}.csv.gz",
                last_completed_datetime=None,
                last_started_datetime=None,
                manifest_id=self.manifest_id,
            )

    def test_report_downloader_base_no_path(self):
        """Test report downloader download_path."""
        downloader = ReportDownloaderBase()
        self.assertIsInstance(downloader, ReportDownloaderBase)
        self.assertIsNotNone(downloader.download_path)
        self.assertTrue(os.path.exists(downloader.download_path))

    def test_report_downloader_base(self):
        """Test download path matches expected."""
        dl_path = f"/{self.fake.word().lower()}/{self.fake.word().lower()}/{self.fake.word().lower()}"
        downloader = ReportDownloaderBase(download_path=dl_path)
        self.assertEqual(downloader.download_path, dl_path)

    def test_get_existing_manifest_db_id(self):
        """Test that a manifest ID is returned."""
        manifest_id = self.downloader._get_existing_manifest_db_id(self.assembly_id)
        self.assertEqual(manifest_id, self.manifest_id)

    @patch("reporting_common.models.CostUsageReportManifest.objects")
    def test_process_manifest_db_record_race(self, mock_manifest_objects):
        """Test that the _process_manifest_db_record returns the correct manifest during a race for initial entry."""
        mock_manifest_objects.filter.return_value.first.side_effect = [None, self.manifest]
        mock_manifest_objects.get_or_create.side_effect = IntegrityError()
        manifest_id = self.downloader._process_manifest_db_record(
            self.assembly_id, self.billing_start, 2, DateAccessor().today()
        )
        self.assertEqual(manifest_id, self.manifest.id)

    @patch("reporting_common.models.CostUsageReportManifest.objects")
    def test_process_manifest_db_record_race_race(self, mock_manifest_objects):
        """Test that the _process_manifest_db_record raises IntegrityError."""
        mock_manifest_objects.filter.return_value.first.side_effect = [None, None]
        mock_manifest_objects.get_or_create.side_effect = IntegrityError()
        with self.assertRaises(IntegrityError):
            self.downloader._process_manifest_db_record(
                self.assembly_id, self.billing_start, 2, DateAccessor().today()
            )

    @patch("reporting_common.models.CostUsageReportManifest.objects")
    def test_process_manifest_db_record_race_race_no_provider(self, mock_manifest_objects):
        """Test that the _process_manifest_db_record raises IntegrityError."""
        mock_manifest_objects.filter.return_value.first.side_effect = [None, None]
        mock_manifest_objects.get_or_create.side_effect = IntegrityError()
        with self.assertRaises(ReportDownloaderError):
            self.downloader._provider_uuid = self.unkown_test_provider_uuid
            self.downloader._process_manifest_db_record(
                self.assembly_id, self.billing_start, 2, DateAccessor().today()
            )

    @patch("reporting_common.models.CostUsageReportManifest.objects")
    def test_process_manifest_db_record_race_no_provider(self, mock_manifest_objects):
        """Test that the _process_manifest_db_record returns the correct manifest during a race for initial entry."""
        mock_manifest_objects.filter.return_value.first.return_value = None
        mock_manifest_objects.get_or_create.side_effect = IntegrityError(
            """insert or update on table "reporting_awscostentrybill" violates foreign key constraint "reporting_awscostent_provider_id_a08725b3_fk_api_provi"
DETAIL:  Key (provider_id)=(fbe0593a-1b83-4182-b23e-08cd190ed939) is not present in table "api_provider".
"""  # noqa: E501
        )
        downloader = ReportDownloaderBase(provider_uuid=self.unkown_test_provider_uuid, cache_key=self.cache_key)
        with self.assertRaises(ReportDownloaderError):
            downloader._process_manifest_db_record(self.assembly_id, self.billing_start, 2, DateAccessor().today())

    def test_process_manifest_db_record_file_num_changed(self):
        """Test that the _process_manifest_db_record returns the correct manifest during a race for initial entry."""
        CostUsageReportStatus.objects.create(
            report_name="fake_report.csv",
            last_completed_datetime=self.billing_start,
            last_started_datetime=self.billing_start,
            etag="etag",
            manifest=self.manifest,
        )
        manifest_id = self.downloader._process_manifest_db_record(
            self.assembly_id, self.billing_start, 3, DateAccessor().today()
        )
        self.assertEqual(manifest_id, self.manifest.id)
        with ReportManifestDBAccessor() as manifest_accessor:
            result_manifest = manifest_accessor.get_manifest_by_id(manifest_id)
        expected_count = CostUsageReportStatus.objects.filter(manifest_id=self.manifest_id).count()
        self.assertEqual(result_manifest.num_total_files, expected_count)
