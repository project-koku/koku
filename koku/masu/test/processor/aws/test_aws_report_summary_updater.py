#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AWSReportSummaryUpdater."""
import calendar
import datetime
from unittest.mock import call
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from dateutil.rrule import DAILY
from dateutil.rrule import rrule
from tenant_schemas.utils import schema_context

from masu.database import AWS_CUR_TABLE_MAP
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.processor.aws.aws_report_summary_updater import AWSReportSummaryUpdater
from masu.test import MasuTestCase
from masu.test.database.helpers import ManifestCreationHelper
from masu.test.database.helpers import ReportObjectCreator


class AWSReportSummaryUpdaterTest(MasuTestCase):
    """Test cases for the AWSReportSummaryUpdater class."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()

        cls.accessor = AWSReportDBAccessor(cls.schema)
        cls.report_schema = cls.accessor.report_schema
        cls.all_tables = list(AWS_CUR_TABLE_MAP.values())
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
            "provider_uuid": self.aws_provider_uuid,
        }

        self.today = DateAccessor().today_with_timezone("UTC")
        self.manifest = self.manifest_accessor.add(**self.manifest_dict)
        self.updater = AWSReportSummaryUpdater(self.schema, self.aws_provider, self.manifest)

    @patch("masu.processor.aws.aws_report_summary_updater.AWSReportDBAccessor.populate_line_item_daily_summary_table")
    @patch("masu.processor.aws.aws_report_summary_updater.AWSReportDBAccessor.populate_line_item_daily_table")
    def test_update_summary_tables_with_manifest(self, mock_daily, mock_summary):
        """Test that summary tables are properly run."""
        self.manifest.num_processed_files = self.manifest.num_total_files

        start_date = self.date_accessor.today_with_timezone("UTC")
        end_date = start_date + datetime.timedelta(days=1)
        bill_date = start_date.replace(day=1).date()

        with AWSReportDBAccessor(self.schema) as accessor:
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

        with AWSReportDBAccessor(self.schema) as accessor:
            bill = accessor.get_cost_entry_bills_by_date(bill_date)[0]
            self.assertIsNotNone(bill.summary_data_creation_datetime)
            self.assertIsNotNone(bill.summary_data_updated_datetime)

    @patch("masu.processor.aws.aws_report_summary_updater.AWSReportDBAccessor.populate_line_item_daily_summary_table")
    @patch("masu.processor.aws.aws_report_summary_updater.AWSReportDBAccessor.populate_line_item_daily_table")
    def test_update_summary_tables_new_bill(self, mock_daily, mock_summary):
        """Test that summary tables are run for a full month."""
        manifest_helper = ManifestCreationHelper(
            self.manifest.id, self.manifest.num_total_files, self.manifest.assembly_id
        )
        manifest_helper.generate_test_report_files()
        manifest_helper.process_all_files()

        start_date = self.date_accessor.today_with_timezone("UTC")
        end_date = start_date
        bill_date = start_date.replace(day=1).date()
        with schema_context(self.schema):
            bill = self.accessor.get_cost_entry_bills_by_date(bill_date)[0]
            bill.summary_data_creation_datetime = None
            bill.summary_data_updated_datetime = None
            bill.derived_cost_datetime = None
            bill.save()

        last_day_of_month = calendar.monthrange(bill_date.year, bill_date.month)[1]

        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")

        expected_start_date = start_date.replace(day=1)
        expected_end_date = end_date.replace(day=last_day_of_month)

        dates = list(rrule(freq=DAILY, dtstart=expected_start_date, until=expected_end_date, interval=5))
        if expected_end_date not in dates:
            dates.append(expected_end_date)
        # Remove the first date since it's the start date
        expected_start_date = dates.pop(0)
        expected_calls = []
        for date in dates:
            if expected_start_date > expected_end_date:
                break
            expected_calls.append(call(expected_start_date.date(), date.date(), [str(bill.id)]))
            expected_start_date = date + datetime.timedelta(days=1)

        self.updater.update_daily_tables(start_date_str, end_date_str)
        self.assertEqual(mock_daily.call_args_list, expected_calls)
        mock_summary.assert_not_called()

        self.updater.update_summary_tables(start_date_str, end_date_str)
        self.assertEqual(mock_summary.call_args_list, expected_calls)

        with AWSReportDBAccessor(self.schema) as accessor:
            bill = accessor.get_cost_entry_bills_by_date(bill_date)[0]
            self.assertIsNotNone(bill.summary_data_creation_datetime)
            self.assertIsNotNone(bill.summary_data_updated_datetime)

    @patch("masu.processor.aws.aws_report_summary_updater.AWSReportDBAccessor.populate_line_item_daily_summary_table")
    @patch("masu.processor.aws.aws_report_summary_updater.AWSReportDBAccessor.populate_line_item_daily_table")
    def test_update_summary_tables_new_bill_last_month(self, mock_daily, mock_summary):
        """Test that summary tables are run for the month of the manifest."""
        billing_start = self.date_accessor.today_with_timezone("UTC").replace(day=1) + relativedelta(months=-1)
        manifest_dict = {
            "assembly_id": "1234",
            "billing_period_start_datetime": billing_start,
            "num_total_files": 2,
            "provider_uuid": self.aws_provider_uuid,
        }
        self.manifest_accessor.delete(self.manifest)

        self.manifest = self.manifest_accessor.add(**manifest_dict)

        manifest_helper = ManifestCreationHelper(
            self.manifest.id, self.manifest.num_total_files, self.manifest.assembly_id
        )
        manifest_helper.generate_test_report_files()
        manifest_helper.process_all_files()

        self.updater = AWSReportSummaryUpdater(self.schema, self.aws_provider, self.manifest)

        start_date = self.date_accessor.today_with_timezone("UTC")
        end_date = start_date + datetime.timedelta(days=1)
        bill_date = billing_start.date()
        with schema_context(self.schema):
            bills = self.accessor.get_cost_entry_bills_by_date(bill_date)
            for bill in bills:
                bill.summary_data_creation_datetime = None
                bill.save()
            bill_ids = sorted([str(bill.id) for bill in bills], reverse=True)

        last_day_of_month = calendar.monthrange(bill_date.year, bill_date.month)[1]

        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")

        expected_start_date = billing_start
        expected_end_date = billing_start.replace(day=last_day_of_month)

        dates = list(rrule(freq=DAILY, dtstart=expected_start_date, until=expected_end_date, interval=5))
        if expected_end_date not in dates:
            dates.append(expected_end_date)
        # Remove the first date since it's the start date
        expected_start_date = dates.pop(0)
        expected_calls = []
        for date in dates:
            if expected_start_date > expected_end_date:
                break
            expected_calls.append(call(expected_start_date.date(), date.date(), bill_ids))
            expected_start_date = date + datetime.timedelta(days=1)

        self.updater.update_daily_tables(start_date_str, end_date_str)
        self.assertEqual(mock_daily.call_args_list, expected_calls)
        mock_summary.assert_not_called()

        self.updater.update_summary_tables(start_date_str, end_date_str)
        self.assertEqual(mock_summary.call_args_list, expected_calls)

        with AWSReportDBAccessor(self.schema) as accessor:
            bill = accessor.get_cost_entry_bills_by_date(bill_date)[0]
            self.assertIsNotNone(bill.summary_data_creation_datetime)
            self.assertIsNotNone(bill.summary_data_updated_datetime)

    def test_update_summary_tables_new_bill_not_done_processing(self):
        """Test that summary tables are not run for a full month."""
        start_date = self.date_accessor.today_with_timezone("UTC")
        end_date = start_date + datetime.timedelta(days=1)
        bill_date = start_date.replace(day=1).date()

        with schema_context(self.schema):
            bill = self.accessor.get_cost_entry_bills_by_date(bill_date)[0]

        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")

        self.updater.update_daily_tables(start_date_str, end_date_str)

        self.updater.update_summary_tables(start_date_str, end_date_str)

        with AWSReportDBAccessor(self.schema) as accessor:
            bill = accessor.get_cost_entry_bills_by_date(bill_date)[0]
            self.assertIsNotNone(bill.summary_data_creation_datetime)
            self.assertIsNotNone(bill.summary_data_updated_datetime)

    @patch("masu.processor.aws.aws_report_summary_updater.AWSReportDBAccessor.populate_line_item_daily_summary_table")
    @patch("masu.processor.aws.aws_report_summary_updater.AWSReportDBAccessor.populate_line_item_daily_table")
    def test_update_summary_tables_finalized_bill(self, mock_daily, mock_summary):
        """Test that summary tables are run for a full month."""
        manifest_helper = ManifestCreationHelper(
            self.manifest.id, self.manifest.num_total_files, self.manifest.assembly_id
        )
        manifest_helper.generate_test_report_files()
        manifest_helper.process_all_files()

        start_date = self.date_accessor.today_with_timezone("UTC")
        end_date = start_date
        bill_date = start_date.replace(day=1).date()

        with schema_context(self.schema):
            bill = self.accessor.get_cost_entry_bills_by_date(bill_date)[0]
            bill.finalized_datetime = start_date
            bill.save()

        last_day_of_month = calendar.monthrange(bill_date.year, bill_date.month)[1]

        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")

        expected_start_date = start_date.replace(day=1)
        expected_end_date = end_date.replace(day=last_day_of_month)

        dates = list(rrule(freq=DAILY, dtstart=expected_start_date, until=expected_end_date, interval=5))
        if expected_end_date not in dates:
            dates.append(expected_end_date)
        # Remove the first date since it's the start date
        expected_start_date = dates.pop(0)
        expected_calls = []
        for date in dates:
            if expected_start_date > expected_end_date:
                break
            expected_calls.append(call(expected_start_date.date(), date.date(), [str(bill.id)]))
            expected_start_date = date + datetime.timedelta(days=1)

        self.updater.update_daily_tables(start_date_str, end_date_str)
        self.assertEqual(mock_daily.call_args_list, expected_calls)
        mock_summary.assert_not_called()

        self.updater.update_summary_tables(start_date_str, end_date_str)
        self.assertEqual(mock_summary.call_args_list, expected_calls)

        with AWSReportDBAccessor(self.schema) as accessor:
            bill = accessor.get_cost_entry_bills_by_date(bill_date)[0]
            self.assertIsNotNone(bill.summary_data_creation_datetime)
            self.assertIsNotNone(bill.summary_data_updated_datetime)

    def test_update_summary_tables_finalized_bill_not_done_proc(self):
        """Test that summary tables are run for a full month."""
        start_date = self.date_accessor.today_with_timezone("UTC")
        end_date = start_date + datetime.timedelta(days=1)
        bill_date = start_date.replace(day=1).date()
        with schema_context(self.schema):
            bill = self.accessor.get_cost_entry_bills_by_date(bill_date)[0]
            bill.finalized_datetime = start_date
            bill.save()

        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")

        self.updater.update_daily_tables(start_date_str, end_date_str)
        self.updater.update_summary_tables(start_date_str, end_date_str)

        with AWSReportDBAccessor(self.schema) as accessor:
            bill = accessor.get_cost_entry_bills_by_date(bill_date)[0]
            self.assertIsNotNone(bill.summary_data_creation_datetime)
            self.assertIsNotNone(bill.summary_data_updated_datetime)

    @patch("masu.processor.aws.aws_report_summary_updater.AWSReportDBAccessor.populate_line_item_daily_summary_table")
    @patch("masu.processor.aws.aws_report_summary_updater.AWSReportDBAccessor.populate_line_item_daily_table")
    def test_update_summary_tables_without_manifest(self, mock_daily, mock_summary):
        """Test that summary tables are properly run without a manifest."""
        self.updater = AWSReportSummaryUpdater(self.schema, self.aws_provider, None)

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

        with AWSReportDBAccessor(self.schema) as accessor:
            bill = accessor.get_cost_entry_bills_by_date(bill_date)[0]
            self.assertIsNotNone(bill.summary_data_creation_datetime)
            self.assertGreater(bill.summary_data_updated_datetime, self.today)
