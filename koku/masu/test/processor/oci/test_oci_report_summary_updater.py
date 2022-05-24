#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCIReportSummaryUpdater."""
import datetime
from unittest.mock import patch

from tenant_schemas.utils import schema_context

from masu.database import OCI_CUR_TABLE_MAP
from masu.database.oci_report_db_accessor import OCIReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.processor.oci.oci_report_summary_updater import OCIReportSummaryUpdater
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator


class OCIReportSummaryUpdaterTest(MasuTestCase):
    """Test cases for the OCIReportSummaryUpdater class."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()

        cls.accessor = OCIReportDBAccessor(cls.schema)
        cls.report_schema = cls.accessor.report_schema
        cls.all_tables = list(OCI_CUR_TABLE_MAP.values())
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
            "provider_uuid": self.oci_provider_uuid,
        }

        self.today = DateAccessor().today_with_timezone("UTC")
        self.manifest = self.manifest_accessor.add(**self.manifest_dict)
        self.updater = OCIReportSummaryUpdater(self.schema, self.oci_provider, self.manifest)

    @patch("masu.processor.oci.oci_report_summary_updater.OCIReportDBAccessor.populate_line_item_daily_summary_table")
    @patch("masu.processor.oci.oci_report_summary_updater.OCIReportDBAccessor.populate_line_item_daily_table")
    def test_update_summary_tables_with_manifest(self, mock_daily, mock_summary):
        """Test that summary tables are properly run."""
        self.manifest.num_processed_files = self.manifest.num_total_files

        start_date = self.date_accessor.today_with_timezone("UTC")
        end_date = start_date + datetime.timedelta(days=1)
        bill_date = start_date.replace(day=1).date()

        with OCIReportDBAccessor(self.schema) as accessor:
            bill = accessor.get_cost_entry_bills_by_date(bill_date)[0]
            bill.summary_data_creation_datetime = start_date
            bill.save()

        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")

        expected_start_date = start_date.date()
        expected_end_date = end_date.date()

        self.updater.update_daily_tables(start_date_str, end_date_str)
        mock_daily.assert_called_with(expected_start_date, expected_end_date, [str(bill.id)])
        mock_summary.assert_not_called()

        self.updater.update_summary_tables(start_date_str, end_date_str)
        mock_summary.assert_called_with(expected_start_date, expected_end_date, [str(bill.id)])

        with OCIReportDBAccessor(self.schema) as accessor:
            bill = accessor.get_cost_entry_bills_by_date(bill_date)[0]
            self.assertIsNotNone(bill.summary_data_creation_datetime)
            self.assertIsNotNone(bill.summary_data_updated_datetime)

    @patch("masu.processor.oci.oci_report_summary_updater.OCIReportDBAccessor.populate_line_item_daily_summary_table")
    @patch("masu.processor.oci.oci_report_summary_updater.OCIReportDBAccessor.populate_line_item_daily_table")
    def test_update_summary_tables_without_manifest(self, mock_daily, mock_summary):
        """Test that summary tables are properly run without a manifest."""
        self.updater = OCIReportSummaryUpdater(self.schema, self.oci_provider, None)

        start_date = datetime.datetime(year=self.today.year, month=self.today.month, day=self.today.day)
        end_date = start_date + datetime.timedelta(days=1)
        bill_date = start_date.replace(day=1).date()

        with schema_context(self.schema):
            bill = self.accessor.get_cost_entry_bills_by_date(bill_date)[0]
            bill.summary_data_updated_datetime = start_date
            bill.save()

        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")

        expected_start_date = start_date.date()
        expected_end_date = end_date.date()
        self.updater.update_daily_tables(start_date_str, end_date_str)
        mock_daily.assert_called_with(expected_start_date, expected_end_date, [str(bill.id)])
        mock_summary.assert_not_called()

        self.updater.update_summary_tables(start_date_str, end_date_str)
        mock_summary.assert_called_with(expected_start_date, expected_end_date, [str(bill.id)])

        with OCIReportDBAccessor(self.schema) as accessor:
            bill = accessor.get_cost_entry_bills_by_date(bill_date)[0]
            self.assertIsNotNone(bill.summary_data_creation_datetime)
            self.assertGreater(bill.summary_data_updated_datetime, self.today)
