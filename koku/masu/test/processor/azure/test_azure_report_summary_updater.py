#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AzureReportSummaryUpdater object."""
import calendar
import datetime
from unittest.mock import call
from unittest.mock import patch

from dateutil.rrule import DAILY
from dateutil.rrule import rrule
from tenant_schemas.utils import schema_context

from api.utils import DateHelper
from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.processor.azure.azure_report_summary_updater import AzureReportSummaryUpdater
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator
from reporting_common.models import CostUsageReportManifest


class AzureReportSummaryUpdaterTest(MasuTestCase):
    """Test Cases for the AzureReportSummaryUpdater object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()

        cls.accessor = AzureReportDBAccessor("acct10001")
        cls.report_schema = cls.accessor.report_schema
        cls.all_tables = list(AZURE_REPORT_TABLE_MAP.values())
        cls.creator = ReportObjectCreator(cls.schema)
        cls.date_accessor = DateHelper()
        cls.manifest_accessor = ReportManifestDBAccessor()

    def setUp(self):
        """Set up each test."""
        super().setUp()

        billing_start = self.date_accessor.this_month_start
        self.manifest_dict = {
            "assembly_id": "1234",
            "billing_period_start_datetime": billing_start,
            "num_total_files": 2,
            "provider_uuid": self.azure_provider_uuid,
        }

        self.today = DateAccessor().today
        # bill = self.creator.create_azure_cost_entry_bill(provider_uuid=self.azure_provider_uuid, bill_date=self.today)
        # product = self.creator.create_azure_cost_entry_product(provider_uuid=self.azure_provider_uuid)
        # meter = self.creator.create_azure_meter(provider_uuid=self.azure_provider_uuid)
        # self.creator.create_azure_cost_entry_line_item(bill, product, meter)
        self.manifest = CostUsageReportManifest.objects.filter(
            provider_id=self.azure_provider_uuid, billing_period_start_datetime=billing_start
        ).first()
        # self.manifest = self.manifest_accessor.add(**self.manifest_dict)

        # with ProviderDBAccessor(self.azure_test_provider_uuid) as provider_accessor:
        #     self.provider = provider_accessor.get_provider()

        self.updater = AzureReportSummaryUpdater(self.schema, self.azure_provider, self.manifest)

    @patch(
        "masu.processor.azure.azure_report_summary_updater.AzureReportDBAccessor.populate_line_item_daily_summary_table"
    )
    def test_azure_update_summary_tables_with_manifest(self, mock_summary):
        """Test that summary tables are properly run."""
        self.manifest.num_processed_files = self.manifest.num_total_files

        start_date = self.date_accessor.today
        end_date = start_date + datetime.timedelta(days=1)
        bill_date = start_date.replace(day=1).date()

        with AzureReportDBAccessor(self.schema) as accessor:
            bill = accessor.get_cost_entry_bills_by_date(bill_date)[0]
            bill.summary_data_creation_datetime = start_date
            bill.save()

        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")

        expected_start_date = start_date.date()
        expected_end_date = end_date.date()

        self.updater.update_daily_tables(start_date_str, end_date_str)
        mock_summary.assert_not_called()

        self.updater.update_summary_tables(start_date_str, end_date_str)
        mock_summary.assert_called_with(expected_start_date, expected_end_date, [str(bill.id)])

        with AzureReportDBAccessor(self.schema) as accessor:
            bill = accessor.get_cost_entry_bills_by_date(bill_date)[0]
            self.assertIsNotNone(bill.summary_data_creation_datetime)
            self.assertIsNotNone(bill.summary_data_updated_datetime)

    @patch(
        "masu.processor.azure.azure_report_summary_updater.AzureReportDBAccessor.populate_line_item_daily_summary_table"
    )
    def test_azure_update_summary_tables_new_bill(self, mock_summary):
        """Test that summary tables are run for a full month."""
        self.manifest.num_processed_files = self.manifest.num_total_files

        start_date = self.date_accessor.today
        end_date = start_date
        bill_date = start_date.replace(day=1).date()
        with schema_context(self.schema):
            bill = self.accessor.get_cost_entry_bills_by_date(bill_date)[0]
            bill.summary_data_creation_datetime = None
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
        dates.pop(0)
        expected_calls = []
        for date in dates:
            if expected_start_date > expected_end_date:
                break
            expected_calls.append(call(expected_start_date.date(), date.date(), [str(bill.id)]))
            expected_start_date = date + datetime.timedelta(days=1)

        self.updater.update_daily_tables(start_date_str, end_date_str)
        mock_summary.assert_not_called()

        self.updater.update_summary_tables(start_date_str, end_date_str)
        self.assertEqual(mock_summary.call_args_list, expected_calls)

        with AzureReportDBAccessor(self.schema) as accessor:
            bill = accessor.get_cost_entry_bills_by_date(bill_date)[0]
            self.assertIsNotNone(bill.summary_data_creation_datetime)
            self.assertIsNotNone(bill.summary_data_updated_datetime)
