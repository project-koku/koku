#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Updates gcp report summary tables in the database."""
import datetime
import logging

from tenant_schemas.utils import schema_context

from koku.pg_partition import PartitionHandlerMixin
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.util.common import date_range_pair
from masu.util.gcp.common import get_bills_from_provider
from reporting.provider.gcp.models import UI_SUMMARY_TABLES

LOG = logging.getLogger(__name__)


class GCPReportSummaryUpdater(PartitionHandlerMixin):
    """Class to update GCP report summary data."""

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
        with GCPReportDBAccessor(self._schema) as accessor:
            # This is the normal processing route
            if self._manifest:
                report_range = accessor.get_gcp_scan_range_from_report_name(manifest_id=self._manifest.id)
                start_date = report_range.get("start", start_date)
                end_date = report_range.get("end", end_date)

        return start_date, end_date

    def update_daily_tables(self, start_date, end_date):
        """Populate the daily tables for reporting.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.

        Returns
            (str, str): A start date and end date.

        """
        start_date, end_date = self._get_sql_inputs(start_date, end_date)
        bills = get_bills_from_provider(
            self._provider.uuid,
            self._schema,
            datetime.datetime.strptime(start_date, "%Y-%m-%d"),
            datetime.datetime.strptime(end_date, "%Y-%m-%d"),
        )
        bill_ids = []
        with schema_context(self._schema):
            bill_ids = [str(bill.id) for bill in bills]

        with GCPReportDBAccessor(self._schema) as accessor:
            for start, end in date_range_pair(start_date, end_date):
                LOG.info(
                    "Updating GCP report daily tables for \n\tSchema: %s"
                    "\n\tProvider: %s \n\tDates: %s - %s\n\tBills: %s",
                    self._schema,
                    self._provider.uuid,
                    start,
                    end,
                    str(bill_ids),
                )
                accessor.populate_line_item_daily_table(start, end, bill_ids)

        return start_date, end_date

    def update_summary_tables(self, start_date, end_date):
        """Populate the summary tables for reporting.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.

        Returns
            (str, str) A start date and end date.

        """
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

        with GCPReportDBAccessor(self._schema) as accessor:
            # Need these bills on the session to update dates after processing
            bills = accessor.bills_for_provider_uuid(self._provider.uuid, start_date)
            for start, end in date_range_pair(start_date, end_date):
                LOG.info(
                    "Updating GCP report summary tables: \n\tSchema: %s"
                    "\n\tProvider: %s \n\tDates: %s - %s\n\tBills: %s",
                    self._schema,
                    self._provider.uuid,
                    start,
                    end,
                    str(bill_ids),
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
