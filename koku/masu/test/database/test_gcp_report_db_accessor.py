#
# Copyright 2020 Red Hat, Inc.
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
"""Test the GCPReportDBAccessor utility object."""
from dateutil import relativedelta
from tenant_schemas.utils import schema_context

from api.utils import DateHelper
from masu.database import GCP_REPORT_TABLE_MAP
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.test import MasuTestCase
from reporting_common.models import CostUsageReportStatus


class GCPReportDBAccessorTest(MasuTestCase):
    """Test Cases for the ReportDBAccessor object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()

        cls.accessor = GCPReportDBAccessor(schema=cls.schema)
        cls.report_schema = cls.accessor.report_schema

        cls.all_tables = list(GCP_REPORT_TABLE_MAP.values())
        cls.foreign_key_tables = [
            GCP_REPORT_TABLE_MAP["bill"],
            GCP_REPORT_TABLE_MAP["product"],
            GCP_REPORT_TABLE_MAP["project"],
        ]
        cls.manifest_accessor = ReportManifestDBAccessor()

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()
        today = DateAccessor().today_with_timezone("UTC")
        billing_start = today.replace(day=1)

        self.manifest_dict = {
            "assembly_id": "1234",
            "billing_period_start_datetime": billing_start,
            "num_total_files": 2,
            "provider_id": self.aws_provider.uuid,
        }
        self.manifest = self.manifest_accessor.add(**self.manifest_dict)

    def test_get_gcp_scan_range_from_report_name_with_manifest(self):
        """Test that we can scan range given the manifest id."""
        dh = DateHelper()
        today_date = dh.today
        expected_start_date = "2020-11-01"
        expected_end_date = "2020-11-30"
        etag = "1234"
        invoice_month = "202011"
        CostUsageReportStatus.objects.create(
            report_name=f"{invoice_month}_{etag}_{expected_start_date}:{expected_end_date}.csv",
            last_completed_datetime=today_date,
            last_started_datetime=today_date,
            etag=etag,
            manifest=self.manifest,
        )
        scan_range = self.accessor.get_gcp_scan_range_from_report_name(manifest_id=self.manifest.id)
        self.assertEqual(str(expected_start_date), scan_range.get("start"))
        self.assertEqual(str(expected_end_date), scan_range.get("end"))

    def test_get_gcp_scan_range_from_report_name_with_report_name(self):
        """Test that we can scan range given the manifest id."""
        expected_start_date = "2020-11-01"
        expected_end_date = "2020-11-30"
        report_name = f"202011_1234_{expected_start_date}:{expected_end_date}.csv"
        scan_range = self.accessor.get_gcp_scan_range_from_report_name(report_name=report_name)
        self.assertEqual(str(expected_start_date), scan_range.get("start"))
        self.assertEqual(str(expected_end_date), scan_range.get("end"))

    def test_get_gcp_scan_range_from_report_name_with_value_error(self):
        """Test that we can scan range given the manifest id."""
        expected_start_date = "2020-11-01"
        expected_end_date = "2020-11-30"
        report_name = f"202011-1234-{expected_start_date}-{expected_end_date}.csv"
        scan_range = self.accessor.get_gcp_scan_range_from_report_name(report_name=report_name)
        self.assertIsNone(scan_range.get("start"))
        self.assertIsNone(scan_range.get("end"))

    def test_get_gcp_scan_range_from_report_name_with_manifest_no_report(self):
        """Test that we can scan range given the manifest id."""
        scan_range = self.accessor.get_gcp_scan_range_from_report_name(manifest_id=self.manifest.id)
        self.assertIsNone(scan_range.get("start"))
        self.assertIsNone(scan_range.get("end"))

    def test_get_bill_query_before_date(self):
        """Test that gets a query for cost entry bills before a date."""
        with schema_context(self.schema):
            table_name = GCP_REPORT_TABLE_MAP["bill"]
            query = self.accessor._get_db_obj_query(table_name)
            first_entry = query.first()

            # Verify that the result is returned for cutoff_date == billing_period_start
            cutoff_date = first_entry.billing_period_start
            cost_entries = self.accessor.get_bill_query_before_date(cutoff_date)
            self.assertEqual(cost_entries.count(), 1)
            self.assertEqual(cost_entries.first().billing_period_start, cutoff_date)

            # Verify that the result is returned for a date later than cutoff_date
            later_date = cutoff_date + relativedelta.relativedelta(months=+1)
            later_cutoff = later_date.replace(month=later_date.month, day=15)
            cost_entries = self.accessor.get_bill_query_before_date(later_cutoff)
            self.assertEqual(cost_entries.count(), 2)
            self.assertEqual(cost_entries.first().billing_period_start, cutoff_date)

            # Verify that no results are returned for a date earlier than cutoff_date
            earlier_date = cutoff_date + relativedelta.relativedelta(months=-1)
            earlier_cutoff = earlier_date.replace(month=earlier_date.month, day=15)
            cost_entries = self.accessor.get_bill_query_before_date(earlier_cutoff)
            self.assertEqual(cost_entries.count(), 0)
