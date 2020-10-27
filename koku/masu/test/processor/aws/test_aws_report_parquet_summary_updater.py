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
"""Test the AWSReportParquetSummaryUpdater."""
from unittest.mock import patch

from tenant_schemas.utils import schema_context

from api.utils import DateHelper
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.processor.aws.aws_report_parquet_summary_updater import AWSReportParquetSummaryUpdater
from masu.test import MasuTestCase


class AWSReportParquetSummaryUpdaterTest(MasuTestCase):
    """Test cases for the AWSReportParquetSummaryUpdater."""

    def setUp(self):
        """Setup up shared variables."""
        super().setUp()
        self.dh = DateHelper()
        manifest_id = 1
        with ReportManifestDBAccessor() as manifest_accessor:
            self.manifest = manifest_accessor.get_manifest_by_id(manifest_id)
        self.updater = AWSReportParquetSummaryUpdater(self.schema_name, self.aws_provider, self.manifest)

    def test_get_sql_inputs(self):
        """Test that dates are returned."""
        start_str = self.dh.this_month_start.isoformat()
        end_str = self.dh.this_month_end.isoformat()
        start, end = self.updater._get_sql_inputs(start_str, end_str)
        self.assertEqual(start, self.dh.this_month_start.date())
        self.assertEqual(end, self.dh.this_month_end.date())

    def test_update_daily_tables(self):
        """Test that this is a placeholder method."""
        start_str = self.dh.this_month_start.isoformat()
        end_str = self.dh.this_month_end.isoformat()
        expected_start, expected_end = self.updater._get_sql_inputs(start_str, end_str)

        expected_log = (
            "INFO:masu.processor.aws.aws_report_parquet_summary_updater:"
            f"update_daily_tables for: {expected_start}-{expected_end}"
        )

        with self.assertLogs("masu.processor.aws.aws_report_parquet_summary_updater", level="INFO") as logger:
            start, end = self.updater.update_daily_tables(start_str, end_str)
            self.assertIn(expected_log, logger.output)
        self.assertEqual(start, expected_start)
        self.assertEqual(end, expected_end)

    @patch("masu.processor.aws.aws_report_parquet_summary_updater.AWSReportDBAccessor.populate_tags_summary_table")
    @patch(
        "masu.processor.aws.aws_report_parquet_summary_updater.AWSReportDBAccessor.populate_line_item_daily_summary_table_presto"  # noqa: E501
    )
    def test_update_daily_summary_tables(self, mock_presto, mock_tag_update):
        """Test that we run Presto summary."""
        start_str = self.dh.this_month_start.isoformat()
        end_str = self.dh.this_month_end.isoformat()
        start, end = self.updater._get_sql_inputs(start_str, end_str)

        with AWSReportDBAccessor(self.schema) as accessor:
            with schema_context(self.schema):
                bills = accessor.bills_for_provider_uuid(self.aws_provider.uuid, start)
                bill_ids = [str(bill.id) for bill in bills]
                current_bill_id = bills.first().id if bills else None

        with CostModelDBAccessor(self.schema, self.aws_provider.uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100

        start_return, end_return = self.updater.update_summary_tables(start, end)
        mock_presto.assert_called_with(start, end, self.aws_provider.uuid, current_bill_id, markup_value)
        mock_tag_update.assert_called_with(bill_ids)

        self.assertEqual(start_return, start)
        self.assertEqual(end_return, end)
