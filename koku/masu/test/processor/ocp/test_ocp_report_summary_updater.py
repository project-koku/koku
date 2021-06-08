#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCPReportProcessor."""
import calendar
import datetime
from unittest.mock import call
from unittest.mock import Mock
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from dateutil.rrule import DAILY
from dateutil.rrule import rrule
from tenant_schemas.utils import schema_context

from api.utils import DateHelper
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.processor.ocp.ocp_report_summary_updater import OCPReportSummaryUpdater
from masu.test import MasuTestCase
from masu.test.database.helpers import ManifestCreationHelper
from masu.test.database.helpers import ReportObjectCreator
from reporting_common.models import CostUsageReportManifest


class OCPReportSummaryUpdaterTest(MasuTestCase):
    """Test cases for the OCPReportSummaryUpdater class."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()

        cls.accessor = OCPReportDBAccessor(cls.schema)
        cls.report_schema = cls.accessor.report_schema
        cls.all_tables = list(OCP_REPORT_TABLE_MAP.values())
        cls.creator = ReportObjectCreator(cls.schema)
        cls.date_accessor = DateHelper()
        cls.manifest_accessor = ReportManifestDBAccessor()
        cls.dh = DateHelper()

    def setUp(self):
        """Set up each test."""
        super().setUp()

        self.provider = self.ocp_provider

        self.today = self.dh.today
        billing_start = datetime.datetime(year=self.today.year, month=self.today.month, day=self.today.day).replace(
            day=1
        )
        self.manifest_dict = {
            "assembly_id": "1234",
            "billing_period_start_datetime": billing_start,
            "num_total_files": 2,
            "num_processed_files": 1,
            "provider_uuid": self.ocp_provider_uuid,
        }

        self.cluster_id = self.ocp_cluster_id
        self.manifest = CostUsageReportManifest.objects.filter(
            provider_id=self.ocp_provider_uuid, billing_period_start_datetime=self.dh.this_month_start
        ).first()
        self.manifest.num_total_files = 2
        self.manifest.save()
        self.updater = OCPReportSummaryUpdater(self.schema, self.provider, self.manifest)

    @patch(
        "masu.processor.ocp.ocp_report_summary_updater.OCPReportDBAccessor.populate_node_label_line_item_daily_table"
    )
    @patch(
        "masu.processor.ocp.ocp_report_summary_updater."
        "OCPReportDBAccessor.populate_storage_line_item_daily_summary_table"
    )
    @patch(
        "masu.processor.ocp.ocp_report_summary_updater." "OCPReportDBAccessor.populate_storage_line_item_daily_table"
    )
    @patch(
        "masu.processor.ocp.ocp_report_summary_updater." "OCPReportDBAccessor.populate_line_item_daily_summary_table"
    )
    @patch("masu.processor.ocp.ocp_report_summary_updater." "OCPReportDBAccessor.populate_line_item_daily_table")
    def test_update_summary_tables_with_manifest(
        self, mock_daily, mock_sum, mock_storage_daily, mock_storage_summary, mock_node_daily
    ):
        """Test that summary tables are properly run."""
        self.manifest.num_processed_files = self.manifest.num_total_files
        self.manifest.save()

        start_date = self.dh.today
        end_date = start_date + datetime.timedelta(days=1)
        bill_date = start_date.replace(day=1).date()

        with schema_context(self.schema):
            period = self.accessor.get_usage_periods_by_date(bill_date)[0]
            period.summary_data_creation_datetime = start_date
            period.summary_data_updated_datetime = None
            period.save()

        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")

        self.assertIsNone(period.summary_data_updated_datetime)

        self.updater.update_daily_tables(start_date_str, end_date_str)
        mock_node_daily.assert_called_with(start_date.date(), end_date.date(), self.cluster_id)
        mock_daily.assert_called_with(start_date.date(), end_date.date(), self.cluster_id)
        mock_storage_daily.assert_called_with(start_date.date(), end_date.date(), self.cluster_id)
        mock_sum.assert_not_called()
        mock_storage_summary.assert_not_called()

        self.updater.update_summary_tables(start_date_str, end_date_str)
        mock_sum.assert_called_with(start_date.date(), end_date.date(), self.cluster_id)
        mock_storage_summary.assert_called_with(start_date.date(), end_date.date(), self.cluster_id)

        with OCPReportDBAccessor(self.schema) as accessor:
            period = accessor.get_usage_periods_by_date(bill_date).filter(provider_id=self.ocp_provider_uuid)[0]

            self.assertIsNotNone(period.summary_data_creation_datetime)
            self.assertIsNotNone(period.summary_data_updated_datetime)

    @patch(
        "masu.processor.ocp.ocp_report_summary_updater.OCPReportDBAccessor.populate_node_label_line_item_daily_table"
    )
    @patch(
        "masu.processor.ocp.ocp_report_summary_updater."
        "OCPReportDBAccessor.populate_storage_line_item_daily_summary_table"
    )
    @patch("masu.processor.ocp.ocp_report_summary_updater.OCPReportDBAccessor.populate_storage_line_item_daily_table")
    @patch("masu.processor.ocp.ocp_report_summary_updater.OCPReportDBAccessor.populate_line_item_daily_summary_table")
    @patch("masu.processor.ocp.ocp_report_summary_updater.OCPReportDBAccessor.populate_line_item_daily_table")
    def test_update_summary_tables_new_period(
        self, mock_daily, mock_sum, mock_storage_daily, mock_storage_summary, mock_node_daily
    ):
        """Test that summary tables are run for a full month."""
        self.manifest.num_processed_files = self.manifest.num_total_files
        self.manifest.save()

        start_date = self.dh.today
        end_date = start_date
        bill_date = start_date.replace(day=1).date()

        with schema_context(self.schema):
            period = self.accessor.get_usage_periods_by_date(bill_date).filter(provider_id=self.ocp_provider_uuid)[0]
            period.summary_data_creation_datetime = None
            period.summary_data_updated_datetime = None
            period.save()

        last_day_of_month = calendar.monthrange(bill_date.year, bill_date.month)[1]

        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")

        expected_start_date = start_date.replace(day=1)
        expected_end_date = end_date.replace(day=last_day_of_month)

        dates = list(rrule(freq=DAILY, dtstart=expected_start_date, until=expected_end_date, interval=5))
        if expected_end_date not in dates:
            dates.append(expected_end_date)
        # Remove the first date since it's the start date
        dates.pop(0)
        expected_calls = []
        for date in dates:
            if expected_start_date > expected_end_date:
                break
            expected_calls.append(call(expected_start_date.date(), date.date(), self.cluster_id))
            expected_start_date = date + datetime.timedelta(days=1)

        self.assertIsNone(period.summary_data_creation_datetime)
        self.assertIsNone(period.summary_data_updated_datetime)

        self.updater.update_daily_tables(start_date_str, end_date_str)
        self.assertEqual(mock_node_daily.call_args_list, expected_calls)
        self.assertEqual(mock_daily.call_args_list, expected_calls)
        self.assertEqual(mock_storage_daily.call_args_list, expected_calls)

        mock_sum.assert_not_called()
        mock_storage_summary.assert_not_called()

        self.updater.update_summary_tables(start_date_str, end_date_str)

        self.assertEqual(mock_sum.call_args_list, expected_calls)
        self.assertEqual(mock_storage_summary.call_args_list, expected_calls)

        with OCPReportDBAccessor(self.schema) as accessor:
            period = accessor.get_usage_periods_by_date(bill_date).filter(provider_id=self.ocp_provider_uuid)[0]
            self.assertIsNotNone(period.summary_data_creation_datetime)
            self.assertIsNotNone(period.summary_data_updated_datetime)

    @patch(
        "masu.processor.ocp.ocp_report_summary_updater.OCPReportDBAccessor.populate_node_label_line_item_daily_table"
    )
    @patch(
        "masu.processor.ocp.ocp_report_summary_updater."
        "OCPReportDBAccessor.populate_storage_line_item_daily_summary_table"
    )
    @patch("masu.processor.ocp.ocp_report_summary_updater.OCPReportDBAccessor.populate_storage_line_item_daily_table")
    @patch("masu.processor.ocp.ocp_report_summary_updater.OCPReportDBAccessor.populate_line_item_daily_summary_table")
    @patch("masu.processor.ocp.ocp_report_summary_updater.OCPReportDBAccessor.populate_line_item_daily_table")
    def test_update_summary_tables_new_period_last_month(
        self, mock_daily, mock_sum, mock_storage_daily, mock_storage_summary, mock_node_daily
    ):
        """Test that summary tables are run for the month of the manifest."""
        billing_start = self.dh.today.replace(day=1) + relativedelta(months=-1)
        manifest_dict = {
            "assembly_id": "1234",
            "billing_period_start_datetime": billing_start,
            "num_total_files": 2,
            "provider_uuid": self.ocp_provider_uuid,
        }

        self.manifest_accessor.delete(self.manifest)
        self.manifest = self.manifest_accessor.add(**manifest_dict)

        manifest_helper = ManifestCreationHelper(
            self.manifest.id, self.manifest.num_total_files, self.manifest.assembly_id
        )
        manifest_helper.generate_test_report_files()
        manifest_helper.process_all_files()
        self.manifest.save()

        self.updater = OCPReportSummaryUpdater(self.schema, self.provider, self.manifest)

        start_date = self.dh.today
        end_date = start_date + datetime.timedelta(days=1)
        bill_date = billing_start.date()

        with schema_context(self.schema):
            period = self.accessor.get_usage_periods_by_date(bill_date).filter(
                provider_id=self.ocp_provider_uuid, report_period_start=billing_start
            )[0]
            period.summary_data_creation_datetime = None
            period.summary_data_updated_datetime = None
            period.save()

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
            expected_calls.append(call(expected_start_date.date(), date.date(), self.cluster_id))
            expected_start_date = date + datetime.timedelta(days=1)

        self.assertIsNone(period.summary_data_creation_datetime)
        self.assertIsNone(period.summary_data_updated_datetime)

        self.updater.update_daily_tables(start_date_str, end_date_str)
        self.assertEqual(mock_node_daily.call_args_list, expected_calls)
        self.assertEqual(mock_daily.call_args_list, expected_calls)
        self.assertEqual(mock_storage_daily.call_args_list, expected_calls)

        mock_sum.assert_not_called()
        mock_storage_summary.assert_not_called()

        self.updater.update_summary_tables(start_date_str, end_date_str)
        self.assertEqual(mock_sum.call_args_list, expected_calls)
        self.assertEqual(mock_storage_summary.call_args_list, expected_calls)

        with OCPReportDBAccessor(self.schema) as accessor:
            period = accessor.get_usage_periods_by_date(bill_date)[0]
            self.assertIsNotNone(period.summary_data_creation_datetime)
            self.assertIsNotNone(period.summary_data_updated_datetime)

    @patch(
        "masu.processor.ocp.ocp_report_summary_updater.OCPReportDBAccessor.populate_node_label_line_item_daily_table"
    )
    @patch(
        "masu.processor.ocp.ocp_report_summary_updater."
        "OCPReportDBAccessor.populate_storage_line_item_daily_summary_table"
    )
    @patch("masu.processor.ocp.ocp_report_summary_updater.OCPReportDBAccessor.populate_storage_line_item_daily_table")
    @patch("masu.processor.ocp.ocp_report_summary_updater.OCPReportDBAccessor.populate_line_item_daily_summary_table")
    @patch("masu.processor.ocp.ocp_report_summary_updater.OCPReportDBAccessor.populate_line_item_daily_table")
    def test_update_summary_tables_existing_period_done_processing(
        self, mock_daily, mock_sum, mock_storage_daily, mock_storage_summary, mock_node_daily
    ):
        """Test that summary tables are not run for a full month."""
        start_date = self.dh.today
        end_date = start_date + datetime.timedelta(days=1)
        bill_date = start_date.replace(day=1).date()

        with schema_context(self.schema):
            period = self.accessor.get_usage_periods_by_date(bill_date)[0]
            period.summary_data_creation_datetime = start_date
            period.summary_data_updated_datetime = None
            period.save()

        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")

        self.assertIsNone(period.summary_data_updated_datetime)

        self.updater.update_daily_tables(start_date_str, end_date_str)
        mock_node_daily.assert_called_with(start_date.date(), end_date.date(), self.cluster_id)
        mock_daily.assert_called_with(start_date.date(), end_date.date(), self.cluster_id)
        mock_storage_daily.assert_called_with(start_date.date(), end_date.date(), self.cluster_id)
        mock_sum.assert_not_called()
        mock_storage_summary.assert_not_called()

        self.updater.update_summary_tables(start_date_str, end_date_str)
        mock_sum.assert_called_with(start_date.date(), end_date.date(), self.cluster_id)
        mock_storage_summary.assert_called_with(start_date.date(), end_date.date(), self.cluster_id)

        with OCPReportDBAccessor(self.schema) as accessor:
            period = accessor.get_usage_periods_by_date(bill_date).filter(provider_id=self.ocp_provider_uuid)[0]
            self.assertIsNotNone(period.summary_data_creation_datetime)
            self.assertIsNotNone(period.summary_data_updated_datetime)

    @patch(
        "masu.processor.ocp.ocp_report_summary_updater.OCPReportDBAccessor.populate_node_label_line_item_daily_table"
    )
    @patch(
        "masu.processor.ocp.ocp_report_summary_updater."
        "OCPReportDBAccessor.populate_storage_line_item_daily_summary_table"
    )
    @patch("masu.processor.ocp.ocp_report_summary_updater.OCPReportDBAccessor.populate_storage_line_item_daily_table")
    @patch("masu.processor.ocp.ocp_report_summary_updater.OCPReportDBAccessor.populate_line_item_daily_summary_table")
    @patch("masu.processor.ocp.ocp_report_summary_updater.OCPReportDBAccessor.populate_line_item_daily_table")
    def test_update_summary_tables_without_manifest(
        self, mock_daily, mock_sum, mock_storage_daily, mock_storage_summary, mock_node_daily
    ):
        """Test that summary tables are properly run without a manifest."""
        # Create an updater that doesn't have a manifest
        updater = OCPReportSummaryUpdater(self.schema, self.provider, None)
        start_date = DateAccessor().today_with_timezone("UTC")
        end_date = start_date + datetime.timedelta(days=1)
        bill_date = start_date.replace(day=1).date()

        with schema_context(self.schema):
            period = self.accessor.get_usage_periods_by_date(bill_date)[0]
            period.summary_data_updated_datetime = start_date
            period.save()

        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")

        updater.update_daily_tables(start_date_str, end_date_str)
        mock_node_daily.assert_called_with(start_date.date(), end_date.date(), self.cluster_id)
        mock_daily.assert_called_with(start_date.date(), end_date.date(), self.cluster_id)
        mock_storage_daily.assert_called_with(start_date.date(), end_date.date(), self.cluster_id)
        mock_sum.assert_not_called()
        mock_storage_summary.assert_not_called()

        updater.update_summary_tables(start_date_str, end_date_str)
        mock_sum.assert_called_with(start_date.date(), end_date.date(), self.cluster_id)
        mock_storage_summary.assert_called_with(start_date.date(), end_date.date(), self.cluster_id)

        with OCPReportDBAccessor(self.schema) as accessor:
            period = accessor.get_usage_periods_by_date(bill_date)[0]
            self.assertIsNotNone(period.summary_data_creation_datetime)
            self.assertGreater(period.summary_data_updated_datetime, self.today)

    @patch(
        "masu.processor.ocp.ocp_report_summary_updater.OCPReportDBAccessor.populate_node_label_line_item_daily_table"
    )
    @patch(
        "masu.processor.ocp.ocp_report_summary_updater."
        "OCPReportDBAccessor.populate_storage_line_item_daily_summary_table"
    )
    @patch("masu.processor.ocp.ocp_report_summary_updater.OCPReportDBAccessor.populate_storage_line_item_daily_table")
    @patch("masu.processor.ocp.ocp_report_summary_updater.OCPReportDBAccessor.get_usage_period_query_by_provider")
    @patch("masu.processor.ocp.ocp_report_summary_updater.OCPReportDBAccessor.populate_line_item_daily_summary_table")
    @patch("masu.processor.ocp.ocp_report_summary_updater.OCPReportDBAccessor.populate_line_item_daily_table")
    def test_update_summary_tables_no_period(
        self, mock_daily, mock_sum, mock_period, mock_storage_daily, mock_storage_summary, mock_node_daily
    ):
        """Test that summary tables are run for a full month when no report period is found."""
        self.manifest.num_processed_files = self.manifest.num_total_files
        self.manifest.save()

        start_date = self.dh.today
        end_date = start_date

        mock_period_filter_by = Mock()
        mock_period_filter_by.all.return_value = None
        mock_period.filter_by.return_value = mock_period_filter_by

        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")

        self.updater.update_daily_tables(start_date_str, end_date_str)
        mock_node_daily.assert_called()
        mock_daily.assert_called()
        mock_storage_daily.assert_called()
        mock_sum.assert_not_called()
        mock_storage_summary.assert_not_called()

        self.updater.update_summary_tables(start_date_str, end_date_str)
        mock_sum.assert_called()
        mock_storage_summary.assert_called()
