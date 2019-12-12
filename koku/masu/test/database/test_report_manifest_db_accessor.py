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
import datetime

from tenant_schemas.utils import schema_context

from api.iam.test.iam_test_case import IamTestCase
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.external.date_accessor import DateAccessor


class ReportManifestDBAccessorTest(IamTestCase):
    """Test cases for the ReportManifestDBAccessor."""

    def setUp(self):
        """Set up the test class."""
        super().setUp()
        self.schema = self.schema_name
        billing_start = DateAccessor().today_with_timezone('UTC').replace(day=1)
        self.manifest_dict = {
            'assembly_id': '1234',
            'billing_period_start_datetime': billing_start,
            'num_total_files': 2,
            'provider_uuid': self.provider_uuid,
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

            assembly_id = self.manifest_dict.get('assembly_id')
            provider_uuid = self.manifest_dict.get('provider_uuid')
            manifest = self.manifest_accessor.get_manifest(assembly_id, provider_uuid)

        self.assertIsNotNone(manifest)
        self.assertEqual(added_manifest, manifest)
        self.assertEqual(manifest.assembly_id, assembly_id)
        self.assertEqual(manifest.provider_id, provider_uuid)
        self.assertEqual(manifest.num_total_files, self.manifest_dict.get('num_total_files'))

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
            now = DateAccessor().today_with_timezone('UTC')
            self.manifest_accessor.mark_manifest_as_updated(manifest)
            self.assertGreater(manifest.manifest_updated_datetime, now)

    def test_mark_manifest_as_completed(self):
        """Test that the manifest is marked updated."""
        manifest = self.manifest_accessor.add(**self.manifest_dict)
        now = DateAccessor().today_with_timezone('UTC')
        self.manifest_accessor.mark_manifest_as_completed(manifest)
        self.assertGreater(manifest.manifest_completed_datetime, now)

    def test_get_manifest_list_for_provider_and_bill_date(self):
        """Test that all manifests are returned for a provider and bill."""
        bill_date = self.manifest_dict['billing_period_start_datetime'].date()
        manifest_dict = copy.deepcopy(self.manifest_dict)
        self.manifest_accessor.add(**manifest_dict)
        result = self.manifest_accessor.get_manifest_list_for_provider_and_bill_date(
            self.provider_uuid, bill_date
        )
        self.assertEqual(len(result), 1)

        manifest_dict['assembly_id'] = '2345'
        self.manifest_accessor.add(**manifest_dict)
        result = self.manifest_accessor.get_manifest_list_for_provider_and_bill_date(
            self.provider_uuid, bill_date
        )
        self.assertEqual(len(result), 2)

        manifest_dict['assembly_id'] = '3456'
        self.manifest_accessor.add(**manifest_dict)
        result = self.manifest_accessor.get_manifest_list_for_provider_and_bill_date(
            self.provider_uuid, bill_date
        )
        self.assertEqual(len(result), 3)

    def test_get_last_report_completed_datetime(self):
        """Test that the last completed report datetime is returned."""
        manifest = self.manifest_accessor.add(**self.manifest_dict)
        earlier_time = DateAccessor().today_with_timezone('UTC')
        later_time = earlier_time + datetime.timedelta(hours=1)

        ReportStatsDBAccessor('earlier_report', manifest.id).update(last_completed_datetime=earlier_time)
        ReportStatsDBAccessor('later_report', manifest.id).update(last_completed_datetime=later_time)

        result = self.manifest_accessor.get_last_report_completed_datetime(manifest.id)

        self.assertEqual(result, later_time)
