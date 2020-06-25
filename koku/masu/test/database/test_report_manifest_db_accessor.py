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
"""Test the ReportManifestDBAccessor."""
import copy

from dateutil.relativedelta import relativedelta
from faker import Faker
from model_bakery import baker
from tenant_schemas.utils import schema_context

from api.iam.test.iam_test_case import IamTestCase
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.test.database.helpers import ManifestCreationHelper
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus

FAKE = Faker()


class ReportManifestDBAccessorTest(IamTestCase):
    """Test cases for the ReportManifestDBAccessor."""

    def setUp(self):
        """Set up the test class."""
        super().setUp()
        self.schema = self.schema_name
        self.billing_start = DateAccessor().today_with_timezone("UTC").replace(day=1)
        self.manifest_dict = {
            "assembly_id": "1234",
            "billing_period_start_datetime": self.billing_start,
            "num_total_files": 2,
            "provider_uuid": self.provider_uuid,
        }
        self.manifest_accessor = ReportManifestDBAccessor()

    def tearDown(self):
        """Tear down the test class."""
        super().tearDown()
        with schema_context(self.schema):
            manifests = self.manifest_accessor._get_db_obj_query().all()
            for manifest in manifests:
                self.manifest_accessor.delete(manifest)

    def test_initializer(self):
        """Test the initializer."""
        accessor = ReportManifestDBAccessor()
        self.assertIsNotNone(accessor._table)

    def test_get_manifest(self):
        """Test that the right manifest is returned."""
        with schema_context(self.schema):
            added_manifest = self.manifest_accessor.add(**self.manifest_dict)

            assembly_id = self.manifest_dict.get("assembly_id")
            provider_uuid = self.manifest_dict.get("provider_uuid")
            manifest = self.manifest_accessor.get_manifest(assembly_id, provider_uuid)

        self.assertIsNotNone(manifest)
        self.assertEqual(added_manifest, manifest)
        self.assertEqual(manifest.assembly_id, assembly_id)
        self.assertEqual(manifest.provider_id, provider_uuid)
        self.assertEqual(manifest.num_total_files, self.manifest_dict.get("num_total_files"))

    def test_get_manifest_by_id(self):
        """Test that the right manifest is returned by id."""
        with schema_context(self.schema):
            added_manifest = self.manifest_accessor.add(**self.manifest_dict)
            manifest = self.manifest_accessor.get_manifest_by_id(added_manifest.id)
        self.assertIsNotNone(manifest)
        self.assertEqual(added_manifest, manifest)

    def test_mark_manifest_as_updated(self):
        """Test that the manifest is marked updated."""
        with schema_context(self.schema):
            manifest = self.manifest_accessor.add(**self.manifest_dict)
            now = DateAccessor().today_with_timezone("UTC")
            self.manifest_accessor.mark_manifest_as_updated(manifest)
            self.assertGreater(manifest.manifest_updated_datetime, now)

    def test_mark_manifest_as_updated_none_manifest(self):
        """Test that a none manifest doesn't update failure."""
        try:
            self.manifest_accessor.mark_manifest_as_updated(None)
        except Exception as err:
            self.fail(f"Test failed with error: {err}")

    def test_mark_manifest_as_completed_none_manifest(self):
        """Test that a none manifest doesn't complete failure."""
        try:
            self.manifest_accessor.mark_manifest_as_completed(None)
        except Exception as err:
            self.fail(f"Test failed with error: {err}")

    def test_get_manifest_list_for_provider_and_bill_date(self):
        """Test that all manifests are returned for a provider and bill."""
        bill_date = self.manifest_dict["billing_period_start_datetime"].date()
        manifest_dict = copy.deepcopy(self.manifest_dict)
        self.manifest_accessor.add(**manifest_dict)
        result = self.manifest_accessor.get_manifest_list_for_provider_and_bill_date(self.provider_uuid, bill_date)
        self.assertEqual(len(result), 1)

        manifest_dict["assembly_id"] = "2345"
        self.manifest_accessor.add(**manifest_dict)
        result = self.manifest_accessor.get_manifest_list_for_provider_and_bill_date(self.provider_uuid, bill_date)
        self.assertEqual(len(result), 2)

        manifest_dict["assembly_id"] = "3456"
        self.manifest_accessor.add(**manifest_dict)
        result = self.manifest_accessor.get_manifest_list_for_provider_and_bill_date(self.provider_uuid, bill_date)
        self.assertEqual(len(result), 3)

    def test_get_last_seen_manifest_ids(self):
        """Test that get_last_seen_manifest_ids returns the appropriate assembly_ids."""
        # test that the most recently seen manifests that haven't been processed are returned
        manifest_dict2 = {
            "assembly_id": "5678",
            "billing_period_start_datetime": self.billing_start,
            "num_total_files": 1,
            "provider_uuid": "00000000-0000-0000-0000-000000000002",
        }
        manifest = self.manifest_accessor.add(**self.manifest_dict)
        manifest2 = self.manifest_accessor.add(**manifest_dict2)
        assembly_ids = self.manifest_accessor.get_last_seen_manifest_ids(self.billing_start)
        self.assertEqual(assembly_ids, [manifest.assembly_id, manifest2.assembly_id])

        # test that when the manifest's files have been processed - it is no longer returned
        manifest2_helper = ManifestCreationHelper(
            manifest2.id, manifest_dict2.get("num_total_files"), manifest_dict2.get("assembly_id")
        )

        manifest2_helper.generate_test_report_files()
        manifest2_helper.process_all_files()

        assembly_ids = self.manifest_accessor.get_last_seen_manifest_ids(self.billing_start)
        self.assertEqual(assembly_ids, [manifest.assembly_id])

        # test that of two manifests with the same provider_ids - that only the most recently
        # seen is returned
        manifest_dict3 = {
            "assembly_id": "91011",
            "billing_period_start_datetime": self.billing_start,
            "num_total_files": 1,
            "provider_uuid": self.provider_uuid,
        }
        manifest3 = self.manifest_accessor.add(**manifest_dict3)
        assembly_ids = self.manifest_accessor.get_last_seen_manifest_ids(self.billing_start)
        self.assertEqual(assembly_ids, [manifest3.assembly_id])

        # test that manifests for a different billing month are not returned
        current_month = self.billing_start
        calculated_month = current_month + relativedelta(months=-2)
        manifest3.billing_period_start_datetime = calculated_month
        manifest3.save()
        assembly_ids = self.manifest_accessor.get_last_seen_manifest_ids(self.billing_start)
        self.assertEqual(assembly_ids, [manifest.assembly_id])

    def test_is_last_completed_datetime_null(self):
        """Test is last completed datetime is null."""
        manifest_id = 123456789
        self.assertTrue(ReportManifestDBAccessor().is_last_completed_datetime_null(manifest_id))
        baker.make(CostUsageReportManifest, id=manifest_id)
        baker.make(CostUsageReportStatus, manifest_id=manifest_id, last_completed_datetime=None)
        self.assertTrue(ReportManifestDBAccessor().is_last_completed_datetime_null(manifest_id))

        CostUsageReportStatus.objects.filter(manifest_id=manifest_id).update(last_completed_datetime=FAKE.date())

        self.assertFalse(ReportManifestDBAccessor().is_last_completed_datetime_null(manifest_id))
