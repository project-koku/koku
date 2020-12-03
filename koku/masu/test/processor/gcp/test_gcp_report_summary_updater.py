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
"""Test GCPReportSummaryUpdater."""
import datetime
from unittest.mock import patch

from tenant_schemas.utils import schema_context

from api.utils import DateHelper
from masu.database import GCP_REPORT_TABLE_MAP
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.processor.gcp.gcp_report_summary_updater import GCPReportSummaryUpdater
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator
from reporting.provider.gcp.models import GCPCostEntryBill


class GCPReportSummaryUpdaterTest(MasuTestCase):
    """Test cases for the GCPReportSummaryUpdater class."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()

        cls.accessor = GCPReportDBAccessor(cls.schema)
        cls.report_schema = cls.accessor.report_schema
        cls.all_tables = list(GCP_REPORT_TABLE_MAP.values())
        cls.creator = ReportObjectCreator(cls.schema)
        cls.date_accessor = DateAccessor()
        cls.manifest_accessor = ReportManifestDBAccessor()

    def setUp(self):
        """Set up each test."""
        super().setUp()

        billing_start = self.date_accessor.today_with_timezone("UTC").replace(day=1)
        self.manifest_dict = {
            "assembly_id": "1234",
            "billing_period_start_datetime": billing_start,
            "num_total_files": 2,
            "provider_uuid": self.gcp_provider_uuid,
        }

        self.today = DateAccessor().today_with_timezone("UTC")
        self.manifest = self.manifest_accessor.add(**self.manifest_dict)
        self.updater = GCPReportSummaryUpdater(self.schema, self.gcp_provider, self.manifest)

    @patch("masu.processor.gcp.gcp_report_summary_updater.GCPReportDBAccessor.populate_line_item_daily_summary_table")
    @patch("masu.processor.gcp.gcp_report_summary_updater.GCPReportDBAccessor.populate_line_item_daily_table")
    def test_update_summary_tables_without_bill(self, mock_daily, mock_summary):
        """Test that summary tables are properly run."""
        self.manifest.num_processed_files = self.manifest.num_total_files

        start_date = self.date_accessor.today_with_timezone("UTC")
        end_date = start_date + datetime.timedelta(days=1)

        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")
        # TODO: Change these tests to use the bill created by nise.
        with schema_context(self.schema):
            GCPCostEntryBill.objects.create(
                provider=self.gcp_provider, billing_period_start=start_date, billing_period_end=end_date
            )
            bills = [str(bill.id) for bill in GCPCostEntryBill.objects.all()]

        expected_start_date = start_date.date()
        expected_end_date = end_date.date()

        self.updater.update_daily_tables(start_date_str, end_date_str)
        mock_daily.assert_called_with(expected_start_date, expected_end_date, bills)
        mock_summary.assert_not_called()

        self.updater.update_summary_tables(start_date_str, end_date_str)
        mock_summary.assert_called_with(expected_start_date, expected_end_date, bills)

        self.assertIsNotNone(self.updater._manifest)

    def test_determine_if_full_summary_update_needed_new_bill(self):
        """determine if update is needed for new bill."""
        self.manifest.num_processed_files = self.manifest.num_total_files

        start_date = self.date_accessor.today_with_timezone("UTC")
        end_date = start_date + datetime.timedelta(days=1)
        # TODO: Change these tests to use the bill created by nise.
        with schema_context(self.schema):
            bill = GCPCostEntryBill.objects.create(
                provider=self.gcp_provider, billing_period_start=start_date, billing_period_end=end_date
            )

        result = self.updater._determine_if_full_summary_update_needed(bill)
        self.assertFalse(result)

    @patch(
        "masu.processor.gcp.gcp_report_summary_updater.GCPReportSummaryUpdater._determine_if_full_summary_update_needed"
    )
    def test_get_sql_inputs_first_bill(self, mock_update):
        """Make sure end date is overwritten with first bill"""
        mock_update.return_value = True
        dh = DateHelper()
        month_start = dh.this_month_start
        end_date = dh.this_month_end
        with schema_context(self.schema):
            GCPCostEntryBill.objects.all().delete()
            GCPCostEntryBill.objects.create(
                provider=self.gcp_provider, billing_period_start=month_start, billing_period_end=end_date
            )
        manifest_dict = {
            "assembly_id": "12345",
            "billing_period_start_datetime": month_start,
            "num_total_files": 1,
            "provider_uuid": self.gcp_provider_uuid,
        }
        manifest = self.manifest_accessor.add(**manifest_dict)
        updater = GCPReportSummaryUpdater(self.schema, self.gcp_provider, manifest)
        _, result_end = updater._get_sql_inputs(month_start, month_start)
        self.assertEqual(end_date.strftime("%Y-%m-%d"), result_end)

    def test_get_sql_inputs_no_manifest(self):
        """Test if no manifest for codecov."""
        start_date = self.date_accessor.today_with_timezone("UTC")
        end_date = start_date + datetime.timedelta(days=1)
        updater = GCPReportSummaryUpdater(self.schema, self.gcp_provider, None)
        result_start, result_end = updater._get_sql_inputs(start_date, end_date)
        self.assertEqual(start_date, result_start)
        self.assertEqual(end_date, result_end)
