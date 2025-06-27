#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ReportManifestDBAccessor."""
import copy
import uuid

from dateutil.relativedelta import relativedelta
from django.utils import timezone
from faker import Faker

from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.test import MasuTestCase
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus
from reporting_common.states import ManifestState
from reporting_common.states import ManifestStep

FAKE = Faker()


class ReportManifestDBAccessorTest(MasuTestCase):
    """Test cases for the ReportManifestDBAccessor."""

    def setUp(self):
        """Set up the test class."""
        super().setUp()
        self.billing_start = self.dh.this_month_start
        self.manifest_dict = {
            "assembly_id": uuid.uuid4(),
            "billing_period_start_datetime": self.billing_start,
            "num_total_files": 2,
            "provider_id": self.ocp_provider_uuid,
        }
        self.manifest_accessor = ReportManifestDBAccessor()
        self.manifest = self.baker.make("CostUsageReportManifest", **self.manifest_dict)

    def test_get_manifest(self):
        """Test that the right manifest is returned."""
        assembly_id = self.manifest_dict.get("assembly_id")
        manifest = self.manifest_accessor.get_manifest(assembly_id, self.ocp_provider_uuid)

        self.assertIsNotNone(manifest)
        self.assertEqual(self.manifest, manifest)
        self.assertEqual(manifest.assembly_id, str(assembly_id))
        self.assertEqual(manifest.provider, self.ocp_provider)
        self.assertEqual(manifest.num_total_files, self.manifest_dict.get("num_total_files"))

    def test_get_manifest_by_id(self):
        """Test that the right manifest is returned by id."""
        manifest = self.manifest_accessor.get_manifest_by_id(self.manifest.id)
        self.assertIsNotNone(manifest)
        self.assertEqual(self.manifest, manifest)

    def test_update_number_of_files_for_manifest(self):
        """Test that the number of files for manifest is updated."""
        before_count = CostUsageReportStatus.objects.filter(manifest_id=self.manifest.id).count()
        CostUsageReportStatus.objects.create(
            report_name="fake_report.csv",
            completed_datetime=self.billing_start,
            started_datetime=self.billing_start,
            etag="etag",
            manifest=self.manifest,
        )
        self.manifest_accessor.update_number_of_files_for_manifest(self.manifest)
        after_count = CostUsageReportStatus.objects.filter(manifest_id=self.manifest.id).count()
        updated_manifest = self.manifest_accessor.get_manifest_by_id(self.manifest.id)
        self.assertNotEqual(before_count, after_count)
        self.assertEqual(updated_manifest.num_total_files, after_count)

    def test_update_manifest_state(self):
        """Test updating the manifest state."""
        before_state = CostUsageReportManifest.objects.filter(id=self.manifest.id).first()
        self.manifest_accessor.update_manifest_state("testing", "start", self.manifest.id)
        after_state = CostUsageReportManifest.objects.filter(id=self.manifest.id).first()
        self.assertNotEqual(before_state.state, after_state.state)
        self.assertIn("testing", after_state.state)

    def test_update_manifest_state_end(self):
        """Test updating the manifest state."""
        before_state = CostUsageReportManifest.objects.filter(id=self.manifest.id).first()
        self.manifest_accessor.update_manifest_state(ManifestStep.DOWNLOAD, ManifestState.START, self.manifest.id)
        self.manifest_accessor.update_manifest_state(ManifestStep.DOWNLOAD, ManifestState.END, self.manifest.id)
        after_state = CostUsageReportManifest.objects.filter(id=self.manifest.id).first()
        self.assertNotEqual(before_state.state, after_state.state)
        self.assertIn("end", after_state.state.get("download"))
        self.assertIn("time_taken_seconds", after_state.state.get("download"))

    def test_mark_manifests_as_completed_none_manifest(self):
        """Test that a none manifest doesn't complete failure."""
        try:
            self.manifest_accessor.mark_manifests_as_completed(None)
        except Exception as err:
            self.fail(f"Test failed with error: {err}")

    def test_get_manifest_list_for_provider_and_bill_date(self):
        """Test that all manifests are returned for a provider and bill."""
        bill_date = self.manifest_dict["billing_period_start_datetime"].date()
        result = self.manifest_accessor.get_manifest_list_for_provider_and_bill_date(self.ocp_provider_uuid, bill_date)
        self.assertEqual(len(result), 2)

        manifest_dict = copy.deepcopy(self.manifest_dict)
        manifest_dict["assembly_id"] = "2345"
        self.baker.make("CostUsageReportManifest", **manifest_dict)
        result = self.manifest_accessor.get_manifest_list_for_provider_and_bill_date(self.ocp_provider_uuid, bill_date)
        self.assertEqual(len(result), 3)

        manifest_dict["assembly_id"] = "3456"
        self.baker.make("CostUsageReportManifest", **manifest_dict)
        result = self.manifest_accessor.get_manifest_list_for_provider_and_bill_date(self.ocp_provider_uuid, bill_date)
        self.assertEqual(len(result), 4)

    def test_get_last_seen_manifest_ids(self):
        """Test that get_last_seen_manifest_ids returns the appropriate assembly_ids."""
        # test that the most recently seen manifests that haven't been processed are returned
        manifest_dict2 = {
            "assembly_id": "5678",
            "billing_period_start_datetime": self.billing_start,
            "num_total_files": 1,
            "provider_id": self.aws_provider_uuid,
        }
        manifest2 = self.baker.make("CostUsageReportManifest", **manifest_dict2)
        assembly_ids = self.manifest_accessor.get_last_seen_manifest_ids(self.billing_start)
        self.assertCountEqual(assembly_ids, [str(self.manifest.assembly_id), manifest2.assembly_id])

        # test that when the manifest's files have been processed - it is no longer returned
        self.baker.make(
            "CostUsageReportStatus",
            _quantity=manifest_dict2.get("num_total_files"),
            manifest_id=manifest2.id,
            completed_datetime=timezone.now(),
        )

        assembly_ids = self.manifest_accessor.get_last_seen_manifest_ids(self.billing_start)
        self.assertEqual(assembly_ids, [str(self.manifest.assembly_id)])

        # test that of two manifests with the same provider_ids - that only the most recently
        # seen is returned
        manifest_dict3 = {
            "assembly_id": "91011",
            "billing_period_start_datetime": self.billing_start,
            "num_total_files": 1,
            "provider_id": self.gcp_provider_uuid,
        }
        manifest3 = self.baker.make("CostUsageReportManifest", **manifest_dict3)
        assembly_ids = self.manifest_accessor.get_last_seen_manifest_ids(self.billing_start)
        self.assertIn(manifest3.assembly_id, assembly_ids)

        # test that manifests for a different billing month are not returned
        current_month = self.billing_start
        calculated_month = current_month + relativedelta(months=-2)
        manifest3.billing_period_start_datetime = calculated_month
        manifest3.save()
        assembly_ids = self.manifest_accessor.get_last_seen_manifest_ids(self.billing_start)
        self.assertEqual(assembly_ids, [str(self.manifest.assembly_id)])

    def test_is_completed_datetime_null(self):
        """Test is last completed datetime is null."""
        manifest_id = 123456789
        self.assertTrue(ReportManifestDBAccessor().is_completed_datetime_null(manifest_id))
        self.baker.make(CostUsageReportManifest, id=manifest_id)
        self.baker.make(CostUsageReportStatus, manifest_id=manifest_id, completed_datetime=None)
        self.assertTrue(ReportManifestDBAccessor().is_completed_datetime_null(manifest_id))

        CostUsageReportStatus.objects.filter(manifest_id=manifest_id).update(completed_datetime=FAKE.date())

        self.assertFalse(ReportManifestDBAccessor().is_completed_datetime_null(manifest_id))

    def test_get_s3_csv_cleared(self):
        """Test that s3 CSV clear status is reported."""
        status = self.manifest_accessor.get_s3_csv_cleared(self.manifest)
        self.assertFalse(status)

        self.manifest_accessor.mark_s3_csv_cleared(self.manifest)

        status = self.manifest_accessor.get_s3_csv_cleared(self.manifest)
        self.assertTrue(status)

    def test_get_s3_parquet_cleared_no_manifest(self):
        """Test that s3 CSV clear status is reported."""
        status = self.manifest_accessor.get_s3_parquet_cleared(None)
        self.assertFalse(status)

    def test_get_s3_parquet_cleared_ocp_no_key(self):
        """Test that s3 CSV clear status is reported."""
        self.manifest_dict["cluster_id"] = "cluster_id"
        self.manifest_dict["assembly_id"] = uuid.uuid4()
        manifest = self.baker.make("CostUsageReportManifest", **self.manifest_dict)
        status = self.manifest_accessor.get_s3_parquet_cleared(manifest)
        self.assertFalse(status)

        self.manifest_accessor.mark_s3_parquet_cleared(manifest)

        self.assertDictEqual(manifest.s3_parquet_cleared_tracker, {})
        self.assertTrue(manifest.s3_parquet_cleared)

        status = self.manifest_accessor.get_s3_parquet_cleared(manifest)
        self.assertTrue(status)

    def test_get_s3_parquet_cleared_ocp_with_key(self):
        """Test that s3 CSV clear status is reported."""
        key = "my-made-up-report"
        self.manifest_dict["cluster_id"] = "cluster_id"
        self.manifest_dict["assembly_id"] = uuid.uuid4()
        manifest = self.baker.make("CostUsageReportManifest", **self.manifest_dict)
        status = self.manifest_accessor.get_s3_parquet_cleared(manifest, key)
        self.assertFalse(status)

        self.manifest_accessor.mark_s3_parquet_cleared(manifest, key)

        self.assertDictEqual(manifest.s3_parquet_cleared_tracker, {key: True})
        self.assertFalse(manifest.s3_parquet_cleared)

        status = self.manifest_accessor.get_s3_parquet_cleared(manifest, key)
        self.assertTrue(status)

    def test_mark_s3_parquet_cleared_no_manifest(self):
        """Test mark_s3_parquet_cleared without manifest does not error."""
        self.assertIsNone(self.manifest_accessor.mark_s3_parquet_cleared(None))

    def test_mark_s3_parquet_cleared(self):
        """Test mark_s3_parquet_cleared without manifest does not error."""
        self.manifest_accessor.mark_s3_parquet_cleared(self.manifest)
        self.assertTrue(self.manifest_accessor.get_s3_parquet_cleared(self.manifest))

    def test_set_and_get_manifest_daily_archive_start_date(self):
        """Test marking manifest daily archive start date."""
        start_date = self.dh.this_month_start.replace(year=2019, month=7).date()
        manifest_start = self.manifest_accessor.set_manifest_daily_start_date(self.manifest.id, start_date)
        self.assertEqual(manifest_start, start_date)

    def test_should_s3_parquet_be_cleared_no_manifest(self):
        """Test that is parquet s3 should be cleared for non-ocp manifest."""
        # no manifest returns False:
        self.assertFalse(self.manifest_accessor.should_s3_parquet_be_cleared(None))

    def test_should_s3_parquet_be_cleared_non_ocp(self):
        """Test that is parquet s3 should be cleared for non-ocp manifest."""
        # non-ocp manifest returns True:
        self.assertTrue(self.manifest_accessor.should_s3_parquet_be_cleared(self.manifest))

    def test_should_s3_parquet_be_cleared_ocp_not_daily(self):
        """Test that is parquet s3 should be cleared for ocp manifest, not daily."""
        # ocp manifest, not daily returns False:
        self.manifest_dict["cluster_id"] = "cluster_id"
        self.manifest_dict["assembly_id"] = uuid.uuid4()
        manifest = self.baker.make("CostUsageReportManifest", **self.manifest_dict)
        self.assertFalse(self.manifest_accessor.should_s3_parquet_be_cleared(manifest))

    def test_should_s3_parquet_be_cleared_ocp_is_daily(self):
        """Test that is parquet s3 should be cleared for ocp manifest, is daily."""
        # ocp manifest, daily files returns True:
        self.manifest_dict["cluster_id"] = "cluster_id"
        self.manifest_dict["assembly_id"] = uuid.uuid4()
        self.manifest_dict["operator_daily_reports"] = True
        manifest = self.baker.make("CostUsageReportManifest", **self.manifest_dict)
        self.assertTrue(self.manifest_accessor.should_s3_parquet_be_cleared(manifest))

    def test_bulk_delete_manifests(self):
        """Test bulk delete of manifests."""
        manifest_list = [self.manifest.id]
        for fake_assembly_id in ["12345", "123456"]:
            self.manifest_dict["assembly_id"] = fake_assembly_id
            manifest = self.baker.make("CostUsageReportManifest", **self.manifest_dict)
            manifest_list.append(manifest.id)
        self.manifest_accessor.bulk_delete_manifests(self.provider_uuid, manifest_list)
        current_manifests = self.manifest_accessor.get_manifest_list_for_provider_and_bill_date(
            self.provider_uuid, self.billing_start
        )
        current_manifests = [manifest.id for manifest in current_manifests]
        for deleted_manifest in manifest_list:
            self.assertNotIn(deleted_manifest, current_manifests)

    def test_bulk_delete_manifests_empty_list(self):
        """Test bulk delete with an empty manifest list."""
        manifest_list = []
        value = self.manifest_accessor.bulk_delete_manifests(self.provider_uuid, manifest_list)
        self.assertIsNone(value)
