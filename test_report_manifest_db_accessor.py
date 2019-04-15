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

from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.external.date_accessor import DateAccessor
from tests import MasuTestCase

class ReportManifestDBAccessorTest(MasuTestCase):
    """Test cases for the ReportManifestDBAccessor."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        billing_start = DateAccessor().today_with_timezone('UTC').replace(day=1)
        cls.manifest_dict = {
            'assembly_id': '1234',
            'billing_period_start_datetime': billing_start,
            'num_total_files': 2,
            'provider_id': 1
        }
        cls.manifest_accessor = ReportManifestDBAccessor()

    @classmethod
    def tearDownClass(cls):
        """Tear down the test class."""
        manifests = cls.manifest_accessor._get_db_obj_query().all()
        for manifest in manifests:
            cls.manifest_accessor.delete(manifest)
        cls.manifest_accessor.commit()
        cls.manifest_accessor.close_session()

    def tearDown(self):
        manifests = self.manifest_accessor._get_db_obj_query().all()
        for manifest in manifests:
            self.manifest_accessor.delete(manifest)
        self.manifest_accessor.commit()

    def test_initializer(self):
        """Test the initializer."""
        accessor = ReportManifestDBAccessor()
        self.assertIsNotNone(accessor._session)

    def test_get_manifest(self):
        """Test that the right manifest is returned."""
        added_manifest = self.manifest_accessor.add(**self.manifest_dict)
        self.manifest_accessor.commit()

        assembly_id = self.manifest_dict.get('assembly_id')
        provider_id = self.manifest_dict.get('provider_id')
        manifest = self.manifest_accessor.get_manifest(assembly_id, provider_id)

        self.assertIsNotNone(manifest)
        self.assertEqual(added_manifest, manifest)
        self.assertEqual(manifest.assembly_id, assembly_id)
        self.assertEqual(manifest.provider_id, provider_id)
        self.assertEqual(
            manifest.num_total_files,
            self.manifest_dict.get('num_total_files')
        )

    def test_get_manifest_by_id(self):
        """Test that the right manifest is returned by id."""
        added_manifest = self.manifest_accessor.add(**self.manifest_dict)
        self.manifest_accessor.commit()
        manifest = self.manifest_accessor.get_manifest_by_id(added_manifest.id)
        self.assertIsNotNone(manifest)
        self.assertEqual(added_manifest, manifest)

    def test_mark_manifest_as_updated(self):
        """Test that the manifest is marked updated."""
        manifest = self.manifest_accessor.add(**self.manifest_dict)
        self.manifest_accessor.commit()
        now = DateAccessor().today_with_timezone('UTC')
        self.manifest_accessor.mark_manifest_as_updated(manifest)
        self.assertGreater(manifest.manifest_updated_datetime, now)
        self.manifest_accessor.commit()
