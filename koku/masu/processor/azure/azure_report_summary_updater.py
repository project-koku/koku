#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Updates report summary tables in the database."""
import calendar
import datetime
import logging

from tenant_schemas.utils import schema_context

from koku.pg_partition import PartitionHandlerMixin
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.util.azure.common import get_bills_from_provider
from masu.util.common import date_range_pair
from reporting.provider.azure.models import UI_SUMMARY_TABLES

LOG = logging.getLogger(__name__)


class AzureReportSummaryUpdater(PartitionHandlerMixin):
    """Class to update Azure report summary data."""

    def __init__(self, schema, provider, manifest):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with

        """
        self._schema = schema
        self._provider = provider
        self._manifest = manifest
        self._date_accessor = DateAccessor()

    def _get_sql_inputs(self, start_date, end_date):
        """Get the required inputs for running summary SQL."""
        with AzureReportDBAccessor(self._schema) as accessor:
            # This is the normal processing route
            if self._manifest:
                # Override the bill date to correspond with the manifest
                bill_date = self._manifest.billing_period_start_datetime.date()
                bills = accessor.get_cost_entry_bills_query_by_provider(self._provider.uuid)
                bills = bills.filter(billing_period_start=bill_date).all()
                first_bill = bills.filter(billing_period_start=bill_date).first()
                do_month_update = False
                with schema_context(self._schema):
                    if first_bill:
                        do_month_update = self._determine_if_full_summary_update_needed(first_bill)
                if do_month_update:
                    last_day_of_month = calendar.monthrange(bill_date.year, bill_date.month)[1]
                    start_date = bill_date.strftime("%Y-%m-%d")
                    end_date = bill_date.replace(day=last_day_of_month)
                    end_date = end_date.strftime("%Y-%m-%d")
                    LOG.info("Overriding start and end date to process full month.")

        return start_date, end_date

    def update_daily_tables(self, start_date, end_date):
        """Populate the daily tables for reporting.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.

        Returns
            (str, str): A start date and end date.

        """
        LOG.info("update_daily_tables for: %s-%s", str(start_date), str(end_date))
        start_date, end_date = self._get_sql_inputs(start_date, end_date)

        return start_date, end_date

    def update_summary_tables(self, start_date, end_date):
        """Populate the summary tables for reporting.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.

        Returns
            (str, str) A start date and end date.

        """
        LOG.info("update_summary_tables for: %s-%s", str(start_date), str(end_date))
        start_date, end_date = self._get_sql_inputs(start_date, end_date)

        with schema_context(self._schema):
            self._handle_partitions(self._schema, UI_SUMMARY_TABLES, start_date, end_date)

        bills = get_bills_from_provider(
            self._provider.uuid,
            self._schema,
            datetime.datetime.strptime(start_date, "%Y-%m-%d"),
            datetime.datetime.strptime(end_date, "%Y-%m-%d"),
        )
        bill_ids = []
        with schema_context(self._schema):
            bill_ids = [str(bill.id) for bill in bills]

        with AzureReportDBAccessor(self._schema) as accessor:
            # Need these bills on the session to update dates after processing
            bills = accessor.bills_for_provider_uuid(self._provider.uuid, start_date)
            for start, end in date_range_pair(start_date, end_date):
                LOG.info(
                    "Updating Azure report summary tables: \n\tSchema: %s" "\n\tProvider: %s \n\tDates: %s - %s",
                    self._schema,
                    self._provider.uuid,
                    start,
                    end,
                )
                accessor.populate_line_item_daily_summary_table(start, end, bill_ids)
                accessor.populate_ui_summary_tables(start, end, self._provider.uuid)
            accessor.populate_tags_summary_table(bill_ids, start_date, end_date)
            for bill in bills:
                if bill.summary_data_creation_datetime is None:
                    bill.summary_data_creation_datetime = self._date_accessor.today_with_timezone("UTC")
                bill.summary_data_updated_datetime = self._date_accessor.today_with_timezone("UTC")
                bill.save()

        return start_date, end_date

    def _determine_if_full_summary_update_needed(self, bill):
        """Decide whether to update summary tables for full billing period."""
        summary_creation = bill.summary_data_creation_datetime

        is_done_processing = False
        with ReportManifestDBAccessor() as manifest_accesor:
            is_done_processing = manifest_accesor.manifest_ready_for_summary(self._manifest.id)

        is_new_bill = summary_creation is None

        # Do a full month update if we just finished processing a finalized
        # bill or we just finished processing a bill for the first time
        if is_done_processing and is_new_bill:
            return True

        return False
